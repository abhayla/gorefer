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

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from apps.common.phone import to_zoho_mobile
from gorefer.flags import flags

logger = logging.getLogger("gorefer.zoho")

# The Zoho Leads field that carries GoRefer's journey-reference (#10). Kept as one
# named constant so the CRM field API-name is not scattered across the module.
GOREFER_REFERENCE_FIELD = "GoRefer_Reference"

# Server-side dedup key. Zoho decides create-vs-update on this field (Model 2).
DUPLICATE_CHECK_FIELDS = ["Mobile"]


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


class LiveZohoAdapter:
    """Real Zoho adapter. Reads secrets from env/secret store (never inline).

    Refuses to construct without ZOHO_* credentials so a flag flip with missing
    config fails LOUDLY at startup instead of silently degrading.
    """

    TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"

    def __init__(self):
        self.client_id = os.environ.get("ZOHO_CLIENT_ID", "")
        self.client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN", "")
        # .in data centre (org passiveincomesolutions) — overridable per environment.
        self.api_base = os.environ.get("ZOHO_API_BASE", "https://www.zohoapis.in")
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise RuntimeError("ZOHO_* credentials not configured — cannot run live.")

    # --- HTTP plumbing (stdlib only — no new dependency for one adapter) ---------

    def _post(self, url: str, *, data: bytes, headers: dict) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # surface Zoho's error body, not a bare 4xx
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Zoho HTTP {exc.code}: {detail}") from exc
        return json.loads(body) if body else {}

    def _access_token(self) -> str:
        payload = urllib.parse.urlencode({
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }).encode()
        data = self._post(
            self.TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Zoho token refresh returned no access_token: {data}")
        return token

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

        body = json.dumps({
            "data": [record],
            "duplicate_check_fields": DUPLICATE_CHECK_FIELDS,
        }).encode()
        resp = self._post(
            f"{self.api_base}/crm/v8/Leads/upsert",
            data=body,
            headers={
                "Authorization": f"Zoho-oauthtoken {self._access_token()}",
                "Content-Type": "application/json",
            },
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
        raise NotImplementedError("Live Zoho history fetch is wired during sandbox verification.")


def get_zoho_adapter():
    if flags.ENABLE_ZOHO_WRITE:
        return LiveZohoAdapter()
    return LogOnlyZohoAdapter()
