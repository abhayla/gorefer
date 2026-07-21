"""Zoho adapter behind the doc-08 contract (M6 + Model 2 upsert).

upsert_lead(): write the Lead to Zoho on capture-first submit as an idempotent
UPSERT keyed on the normalized mobile, stamping a GoRefer journey-reference on the
Zoho lead (#10) for best-effort opener→journey linking.
fetch_referrer_history(): lazy per-referrer history pull on first appearance (#9).

Model 2 (DA decision 2026-07-15, supersedes DF-9): GoRefer writes to Zoho, but
NEVER blind-creates. The write goes through Zoho's `upsertRecords` with
`duplicate_check_fields=["Mobile"]` so dedup is decided SERVER-SIDE by Zoho:
  - a Lead with that Mobile exists -> Zoho UPDATEs it (we stamp the journey-ref
    + any newly captured fields);
  - else Zoho CREATEs it (stamped with the journey-ref).
Server-side dedup is preferred over a hand-rolled search-then-create because the
latter races: two concurrent submits can both read "not found" and both create.

ENABLE_ZOHO_WRITE gates real calls:
  - false (default): LogOnlyZohoAdapter logs the intended call + returns a fake
    zoho_lead_id, so the flow works offline. Conversions are exercised via fixtures
    fed through the SAME webhook ingest path (never an internal fabrication).
  - true: LiveZohoAdapter reads ZOHO_* config and refuses to construct without it
    (fail loud, never silently live) — same pattern as LiveZohoReadAdapter.

Guardrail #2: this adapter NEVER sets account/conversion status internally — status
comes back ONLY through the webhook ingest path.

DPDP: the payload carries PII (name/mobile/email) to Zoho, which is the lead's
purpose-limited destination. PII never enters the immutable event log.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from apps.common.phone import to_zoho_mobile
from apps.integrations.zoho.client import ZohoHttpClient

logger = logging.getLogger("gorefer.zoho")

# The Zoho Leads field that carries GoRefer's journey-reference (#10). Kept as one
# named constant so the CRM field API-name is not scattered across the module.
GOREFER_REFERENCE_FIELD = "GoRefer_Reference"

# Server-side dedup key. Zoho decides create-vs-update on this field (Model 2).
DUPLICATE_CHECK_FIELDS = ["Mobile"]

# Referrer Contact upsert (M13 Path B): dedup on ClientId — a verified referrer is
# keyed by their Zerodha client id in Contacts (doc-08 B4), NOT by mobile (a family
# member could share a mobile; the client id is the identity, ADR-016/ADR-035).
CONTACT_DUPLICATE_CHECK_FIELDS = ["ClientId"]

# Zoho Leads fields pulled for the lazy per-referrer history fetch (#9, DF-4).
# Account_Opened_On is the TRUE open date (ADR-017) — analytics must never key off
# the import/sync date, or a backfill stacks all history onto day 1.
HISTORY_FIELDS = (
    "Full_Name",
    "Mobile",
    "City",
    "Account_Status",
    "Account_Opened_On",
    "Referrer_Client_Id",
    GOREFER_REFERENCE_FIELD,
)

HISTORY_PAGE_SIZE = 200


@dataclass
class LeadWriteResult:
    zoho_lead_id: str
    gorefer_reference: str
    # "insert" | "update" — what Zoho actually did. Lets the caller/tests prove that
    # a repeat submit UPDATED rather than double-created.
    action: str = "insert"


@dataclass
class ReferrerHistory:
    referrer_client_id: str
    conversions: list = field(default_factory=list)  # list of conversion dicts (Zoho-shaped)


@dataclass
class ContactWriteResult:
    zoho_contact_id: str
    action: str = "insert"  # "insert" | "update" — what Zoho actually did


def gorefer_reference_for(referral) -> str:
    """The reference stamped on the Zoho lead + echoed back on conversion (#10)."""
    return f"GR-{referral.pk}" if referral is not None else ""


def build_lead_record(*, payload: dict, gorefer_reference: str) -> dict:
    """Map a GoRefer capture payload to a Zoho Leads record.

    Mobile is written in Zoho's stored format — BARE 10-digit, no country code (DA
    correction 2026-07-15, verified against live Leads). It is DERIVED from the one
    canonical normalizer via `to_zoho_mobile`, so the dedup key GoRefer sends is
    byte-identical to what Zoho already holds. Writing the internal 91-prefixed form
    here would make `duplicate_check_fields=[Mobile]` miss the existing record and
    silently twin the lead.

    A malformed mobile yields "" — the caller refuses the write rather than sending
    a padded/garbage dedup key.
    """
    mobile = to_zoho_mobile(payload.get("mobile"))
    record = {
        "Last_Name": payload.get("name") or "(GoRefer lead)",  # Zoho requires Last_Name
        "Mobile": mobile,
        "Phone": mobile,
        "Lead_Source": "GoRefer",
    }
    if payload.get("email"):
        record["Email"] = payload["email"]
    if payload.get("city"):
        record["City"] = payload["city"]
    if payload.get("referred_by"):
        record["Referrer_Client_Id"] = payload["referred_by"]
    # Referrer_Mobile takes the SAME bare-10-digit treatment as Mobile — it is matched
    # against the same Zoho-stored format (DA correction #4).
    if payload.get("referrer_mobile"):
        record["Referrer_Mobile"] = to_zoho_mobile(payload["referrer_mobile"])
    if gorefer_reference:
        record[GOREFER_REFERENCE_FIELD] = gorefer_reference
    return record


def build_referrer_contact_record(*, client_id: str, name: str, mobile: str, email: str = "") -> dict:
    """Map an approved Path-B referrer (M13) to a Zoho Contacts record.

    Same field conventions as the READ leg (doc-08 B4: Contacts stores `ClientId`)
    and the Leads WRITE leg (Mobile in Zoho's bare 10-digit stored format via
    `to_zoho_mobile`). `Last_Name` is required by Zoho — the verified registered
    name from the evidence review fills it (never a placeholder that could look
    like a real person GoRefer invented).
    """
    record = {
        "Last_Name": name or f"(GoRefer referrer {client_id})",
        "ClientId": client_id,
        "Mobile": to_zoho_mobile(mobile),
        "Phone": to_zoho_mobile(mobile),
        "IsReferrer": True,
        "Lead_Source": "GoRefer",
    }
    if email:
        record["Email"] = email
    return record


class LogOnlyZohoAdapter:
    """Demo/dev adapter: logs the intended Zoho write, returns a fake lead id.

    Mirrors the live upsert's contract (including `action`) so the demo path and the
    live path are exercised through the same code above the adapter seam.
    """

    def upsert_lead(self, *, payload: dict, gorefer_reference: str) -> LeadWriteResult:
        record = build_lead_record(payload=payload, gorefer_reference=gorefer_reference)
        logger.info(
            "[demo] Zoho upsert_lead suppressed: ref=%s dedup_on=%s record=%s",
            gorefer_reference, DUPLICATE_CHECK_FIELDS, record,
        )
        # Deterministic fake id keyed on the Zoho-format (bare 10-digit) mobile, so a
        # repeat submit in demo resolves to the same id — the offline analogue of
        # Zoho's server-side dedup.
        fake_id = f"demo-zoho-{record['Mobile'] or 'x'}"
        return LeadWriteResult(
            zoho_lead_id=fake_id, gorefer_reference=gorefer_reference, action="insert"
        )

    def fetch_referrer_history(self, *, referrer_client_id: str) -> ReferrerHistory:
        logger.info("[demo] Zoho fetch_referrer_history suppressed: %s", referrer_client_id)
        return ReferrerHistory(referrer_client_id=referrer_client_id, conversions=[])

    def upsert_referrer_contact(
        self, *, client_id: str, name: str, mobile: str, email: str = ""
    ) -> ContactWriteResult:
        record = build_referrer_contact_record(
            client_id=client_id, name=name, mobile=mobile, email=email
        )
        logger.info(
            "[demo] Zoho upsert_referrer_contact suppressed: dedup_on=%s record=%s",
            CONTACT_DUPLICATE_CHECK_FIELDS, record,
        )
        return ContactWriteResult(zoho_contact_id=f"demo-zoho-contact-{client_id}", action="insert")


class LiveZohoAdapter:
    """Real Zoho adapter. Reads secrets from env/secret store (never inline).

    Refuses to construct without ZOHO_* credentials so a flag flip with missing
    config fails LOUDLY at startup instead of silently degrading.
    """

    def __init__(self, http: ZohoHttpClient | None = None):
        # Constructing the client reads (and validates) ZOHO_* creds — so this adapter
        # still refuses to exist without them. Shared with the live READ adapter.
        self.http = http or ZohoHttpClient()

    # --- Contract ----------------------------------------------------------------

    def upsert_lead(self, *, payload: dict, gorefer_reference: str) -> LeadWriteResult:
        """Idempotent upsert keyed on Mobile (Model 2). Zoho decides insert vs update."""
        record = build_lead_record(payload=payload, gorefer_reference=gorefer_reference)
        if not record["Mobile"]:
            # No usable dedup key (malformed / <10 digits) => an upsert degrades to a
            # blind create. Refuse; the lead stays captured locally for later repair.
            raise RuntimeError(
                "Zoho upsert refused: no bare 10-digit mobile to dedup on (malformed)."
            )

        # Contract confirmed live by the DA against the PIFS org (2026-07-16):
        # POST /crm/v8/Leads/upsert with duplicate_check_fields:["Mobile"] →
        # first call action=insert; identical re-call action=update, same record id.
        resp = self.http.post_json(
            "/crm/v8/Leads/upsert",
            body={"data": [record], "duplicate_check_fields": DUPLICATE_CHECK_FIELDS},
        )
        rows = resp.get("data") or []
        if not rows:
            raise RuntimeError(f"Zoho upsert returned no data: {resp}")
        row = rows[0]
        if row.get("code") not in ("SUCCESS",):
            raise RuntimeError(f"Zoho upsert failed: {row}")
        details = row.get("details") or {}
        # action is "insert" on create, "update" when Zoho matched an existing Mobile.
        action = (row.get("action") or details.get("action") or "insert").lower()
        logger.info(
            "Zoho upsert_lead %s: ref=%s id=%s", action, gorefer_reference, details.get("id")
        )
        return LeadWriteResult(
            zoho_lead_id=str(details.get("id") or ""),
            gorefer_reference=gorefer_reference,
            action=action,
        )

    def fetch_referrer_history(self, *, referrer_client_id: str) -> ReferrerHistory:
        """Lazy per-referrer history pull on first appearance (#9, DF-4).

        DF-4 records the decision: the PRIMARY mechanism is this lazy per-referrer
        fetch — each referrer's past conversions load when they first become active in
        GoRefer — with the all-time bulk backfill deliberately deferred. This is that
        lazy path.

        Reads Zoho Leads credited to this referrer that Zoho marks as opened, keyed on
        the same `Referrer_Client_Id` the WRITE leg stamps. Returns raw Zoho-shaped
        rows; the ingest layer decides what becomes a Conversion — this adapter never
        writes status itself (guardrail #2), and the true open date (ADR-017) rides
        along as `Account_Opened_On` so history lands in its REAL period, not today.
        """
        if not referrer_client_id:
            return ReferrerHistory(referrer_client_id=referrer_client_id, conversions=[])

        resp = self.http.get(
            "/crm/v8/Leads/search",
            params={
                "criteria": f"(Referrer_Client_Id:equals:{referrer_client_id})",
                "fields": ",".join(HISTORY_FIELDS),
                "per_page": HISTORY_PAGE_SIZE,
            },
        )
        rows = resp.get("data") or []
        logger.info(
            "Zoho fetch_referrer_history: %d row(s) for ClientId=%s", len(rows), referrer_client_id
        )
        return ReferrerHistory(referrer_client_id=referrer_client_id, conversions=rows)

    def upsert_referrer_contact(
        self, *, client_id: str, name: str, mobile: str, email: str = ""
    ) -> ContactWriteResult:
        """Idempotent Contacts upsert keyed on ClientId (M13 Path B approval).

        ADR-035: an approved evidence-verified referrer is upserted into Zoho so
        their NEXT login resolves an on-file channel (Path A). Server-side dedup on
        ClientId (same race-safety rationale as the Leads upsert). This writes
        identity/channel fields ONLY — never account/conversion status (guardrail #2).
        """
        record = build_referrer_contact_record(
            client_id=client_id, name=name, mobile=mobile, email=email
        )
        if not record["ClientId"]:
            raise RuntimeError("Zoho contact upsert refused: no client_id to dedup on.")

        resp = self.http.post_json(
            "/crm/v8/Contacts/upsert",
            body={"data": [record], "duplicate_check_fields": CONTACT_DUPLICATE_CHECK_FIELDS},
        )
        rows = resp.get("data") or []
        if not rows:
            raise RuntimeError(f"Zoho contact upsert returned no data: {resp}")
        row = rows[0]
        if row.get("code") not in ("SUCCESS",):
            raise RuntimeError(f"Zoho contact upsert failed: {row}")
        details = row.get("details") or {}
        action = (row.get("action") or details.get("action") or "insert").lower()
        logger.info(
            "Zoho upsert_referrer_contact %s: ClientId=%s id=%s",
            action, client_id, details.get("id"),
        )
        return ContactWriteResult(zoho_contact_id=str(details.get("id") or ""), action=action)


def get_zoho_adapter():
    """Select the write adapter from the EFFECTIVE flag (admin override -> env default).

    Not `flags.ENABLE_ZOHO_WRITE` directly: the Settings checkbox owns this now, and a
    raw-env read would make the checkbox a lie.
    """
    from apps.config.integration_flags import ENABLE_ZOHO_WRITE, resolve_flag

    if resolve_flag(ENABLE_ZOHO_WRITE):
        return LiveZohoAdapter()
    return LogOnlyZohoAdapter()
