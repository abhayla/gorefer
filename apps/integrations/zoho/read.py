"""Zoho READ enrichment adapter behind the doc-08 contract (M9, Part A).

READ-ONLY. This adapter NEVER writes to Zoho and NEVER sets conversion/account status
internally — status still comes only through the webhook ingest path (guardrail #2).
It enriches the Referral Profile top band + Referred-People tab by matching a referrer
to their Zoho Contact by ClientId (doc-08 B4).

`ENABLE_ZOHO_READ` gates real calls, INDEPENDENTLY of `ENABLE_ZOHO_WRITE` (DF-9 is
superseded — WRITE now goes ON for PIFS via Model 2 upsert-by-mobile; Abhay+DA
2026-07-15. The two flags move separately):
  - false (default, CI/demo): LogOnlyZohoReadAdapter returns SEEDED FIXTURES, no live
    call — the whole Referral Profile works offline.
  - true (creds present): LiveZohoReadAdapter issues real Contacts/Leads searches.
    Refuses to construct without ZOHO_* config (fail loud, never silently live).

doc-08 B4 field-name note: `ClientId` (Contacts) vs `Client_Id` (Referrers) — the
adapter normalizes both. Missing values come back as None so the view renders the
config "— not on file —" marker.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from apps.config.cascade import resolve
from apps.integrations.zoho.client import ZohoHttpClient

logger = logging.getLogger("gorefer.zoho.read")

# --- T-126 (W3): audience sync + send-queue counts config keys -------------------
# Cascade keys, resolved with an in-code default (CLAUDE.md §6d/§6e — behaviour is
# config, not a literal), same lightweight pattern as `zoho.reconcile`'s cascade
# keys: no seed_program row required, `resolve(key, default=...)` covers a fresh DB.

# Grouping rule for `fetch_send_queue_counts` (decision ⑭): any WA_Send_Queue
# `Template_Name` starting with one of these prefixes counts as the "referral"
# (Zerodha/GoRefer) stream; everything else (legacy other-broker broadcasts like
# `angel_one_*`, `stay_connected_*`) is "other" — still counted, never dropped,
# because every stream burns the same WhatsApp number's quality rating.
SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_KEY = "zoho_send_queue_referral_template_prefixes"
SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_DEFAULT = ["gr_", "gorefer_"]

# Pagination safety caps (mirrors `zoho.reconcile.fetch_opened_contacts`'s 20-page
# hard stop): processing only the first page would look like success while quietly
# dropping rows.
_REFERRERS_PAGE_SIZE = 200
_REFERRERS_MAX_PAGES = 100  # 20,000 referrers — far beyond any real audience
_SEND_QUEUE_PAGE_SIZE = 200
_SEND_QUEUE_MAX_PAGES = 20  # 4,000 rows/day — far beyond any real daily send volume

_UNKNOWN_STATUS_BUCKET = "OTHER"

# Known WA_Send_Queue statuses observed live (T-126 intake, 2026-08-13/14). Any
# Queue_Status outside this set rolls into `_UNKNOWN_STATUS_BUCKET` — never kept
# as its own raw key, never dropped.
_KNOWN_QUEUE_STATUSES = frozenset({
    "SENT", "FAILED", "PENDING", "SUPPRESSED_CAPPED", "SUPPRESSED_INVALID",
})

# The Zoho Contact fields pulled for the Referral Profile top band (DA M9 Part A).
# Kept as data (not scattered literals) so adding a field is config, not code surgery.
CONTACT_ENRICHMENT_FIELDS = (
    "Full_Name",
    # On-file channels (Q-M-OTP-2): the login OTP recipient resolver reads Mobile/
    # Phone (never a user-typed number, ADR-035 Path A) and the OAuth auto-bind
    # (ADR-027) matches on Email/Mobile. Profile chips do NOT render these — they
    # stay on the erasable side of the PII boundary.
    "Mobile",
    "Phone",
    "Email",
    "Mailing_City",
    "Mailing_State",
    "Mailing_Country",
    "Profession",
    "Account_Status",
    "Account_Opened_On",  # TRUE open date — analytics use this (ADR-017)
    "Is_Active_Investor",
    "IsReferrer",
    "Partner_Id",
    "Referral_Bonus",
    "Referral_Bonus_Amount",
    "Email_Opt_Out",
    "WhatsApp_Opt_Out",
    "Do_not_contact",
)

# Zoho Leads fields backing the Referred-People tab, matched on Referrer_Client_Id
# (the same field GoRefer's WRITE leg stamps — adapter.build_lead_record).
REFERRED_PERSON_FIELDS = (
    "Full_Name",
    "City",
    "Profession",
    "Partner_Id",
    "Account_Status",
    "Account_Opened_On",  # TRUE open date (ADR-017) — never the sync date
    "Referral_Bonus",
)

# One referrer's people are shown on a single tab; 200 is Zoho's per_page ceiling and
# far beyond any real referrer's count. Pagination would be premature here.
REFERRED_PEOPLE_PAGE_SIZE = 200


@dataclass
class ZohoContact:
    """Normalized Zoho Contact enrichment for one referrer (matched by ClientId).

    All fields optional — a missing Zoho value is None, rendered as "— not on file —".
    """

    client_id: str
    full_name: str | None = None
    # On-file channels (Q-M-OTP-2 / ADR-027). PII — never rendered on the profile.
    mobile: str | None = None
    phone: str | None = None
    email: str | None = None
    mailing_city: str | None = None
    mailing_state: str | None = None
    mailing_country: str | None = None
    profession: str | None = None
    account_status: str | None = None
    account_opened_on: str | None = None
    is_active_investor: bool | None = None
    is_referrer: bool | None = None
    partner_id: str | None = None
    referral_bonus: str | None = None
    referral_bonus_amount: str | None = None
    email_opt_out: bool | None = None
    whatsapp_opt_out: bool | None = None
    do_not_contact: bool | None = None
    matched: bool = False  # True when Zoho had a Contact for this ClientId


@dataclass
class ZohoReferredPerson:
    """One person referred by this ClientId (from Zoho Leads + Contacts)."""

    name: str | None = None
    city: str | None = None
    profession: str | None = None
    partner: str | None = None
    account_status: str | None = None
    opened_on: str | None = None
    reward: str | None = None


@dataclass
class ReferredPeople:
    referrer_client_id: str
    people: list = field(default_factory=list)  # list[ZohoReferredPerson]


@dataclass
class ZohoReferrerRow:
    """One row of the audience-sync source (decision ⑫) — one Zoho `Referrers`
    record, normalized. `SyncedReferrer` (apps.campaigns.models) is filled from
    these by the T-126 sync task; this dataclass carries no GoRefer-side state.

    `language` is always "" today: the live `Referrers` module (Zoho module API
    name `Referrers`, `CustomModule3`) carries no language field (verified via
    Zoho CRM `getFields` at build time) — decision ⑮'s "Zoho language field, EN
    fallback" therefore always falls back to English until Zoho adds one. Blank
    stays blank here; the EN fallback itself lives in the campaign layer
    (`MessagingCampaign.template_for`), not in this adapter.
    """

    client_id: str
    mobile: str  # raw as returned by Zoho — normalize at the call site
    name: str = ""
    language: str = ""
    record_created_at: datetime | None = None


@dataclass
class ReferrerAudience:
    rows: list = field(default_factory=list)  # list[ZohoReferrerRow]
    truncated: bool = False  # hit the pagination cap — caller must not infer "complete"


@dataclass
class SendQueueCounts:
    """Per-status counts for one IST business date, grouped referral-vs-other
    (decision ⑭). Every status Zoho returns is counted somewhere — an unrecognized
    status rolls into the `OTHER` bucket within its group, never dropped.
    """

    date_ist: str
    referral: dict = field(default_factory=dict)  # status -> count
    other: dict = field(default_factory=dict)  # status -> count
    truncated: bool = False


def _norm_contact(client_id: str, raw: dict) -> ZohoContact:
    """Map a raw Zoho record (Contacts/Referrers) to a normalized ZohoContact.

    Handles the ClientId/Client_Id field-name inconsistency (doc-08 B4). A blank Zoho
    value is treated as None so the view shows "— not on file —" rather than an empty.
    """

    def g(*keys):
        for k in keys:
            v = raw.get(k)
            if v not in (None, ""):
                return v
        return None

    return ZohoContact(
        client_id=client_id,
        full_name=g("Full_Name"),
        mobile=g("Mobile"),
        phone=g("Phone"),
        email=g("Email"),
        mailing_city=g("Mailing_City"),
        mailing_state=g("Mailing_State"),
        mailing_country=g("Mailing_Country"),
        profession=g("Profession"),
        account_status=g("Account_Status"),
        account_opened_on=g("Account_Opened_On"),
        is_active_investor=g("Is_Active_Investor"),
        is_referrer=g("IsReferrer"),
        partner_id=g("Partner_Id"),
        referral_bonus=g("Referral_Bonus"),
        referral_bonus_amount=g("Referral_Bonus_Amount"),
        email_opt_out=g("Email_Opt_Out"),
        whatsapp_opt_out=g("WhatsApp_Opt_Out"),
        do_not_contact=g("Do_not_contact"),
        matched=True,
    )


def _norm_referred_person(raw: dict) -> ZohoReferredPerson:
    """Map a raw Zoho Lead row to a ZohoReferredPerson (blank -> None)."""

    def g(*keys):
        for k in keys:
            v = raw.get(k)
            if v not in (None, ""):
                return v
        return None

    return ZohoReferredPerson(
        name=g("Full_Name"),
        city=g("City"),
        profession=g("Profession"),
        partner=g("Partner_Id"),
        account_status=g("Account_Status"),
        opened_on=g("Account_Opened_On"),
        # Eligibility wording only. Reward AMOUNTS live solely in the Zerodha Console
        # (Gap 4/7) — GoRefer never reads, computes, or stores an amount.
        reward=g("Referral_Bonus"),
    )


class LogOnlyZohoReadAdapter:
    """Demo/dev adapter: returns SEEDED FIXTURES, no live call. Works offline.

    Fixtures live in a small in-memory map keyed by ClientId so the Referral Profile
    renders a realistic top band + Referred-People tab in demo mode. An unknown
    ClientId returns an unmatched ZohoContact (everything "— not on file —").
    """

    def fetch_contact_by_client_id(self, *, client_id: str) -> ZohoContact:
        raw = _DEMO_CONTACTS.get(client_id)
        if raw is None:
            logger.info("[demo] Zoho read: no fixture Contact for ClientId=%s", client_id)
            return ZohoContact(client_id=client_id, matched=False)
        logger.info("[demo] Zoho read: fixture Contact for ClientId=%s", client_id)
        return _norm_contact(client_id, raw)

    def fetch_referred_people(self, *, referrer_client_id: str) -> ReferredPeople:
        rows = _DEMO_REFERRED.get(referrer_client_id, [])
        people = [ZohoReferredPerson(**r) for r in rows]
        logger.info(
            "[demo] Zoho read: %d fixture referred person(s) for ClientId=%s",
            len(people), referrer_client_id,
        )
        return ReferredPeople(referrer_client_id=referrer_client_id, people=people)

    def fetch_referrer_audience(self) -> ReferrerAudience:
        rows = [ZohoReferrerRow(**r) for r in _DEMO_REFERRER_AUDIENCE]
        logger.info("[demo] Zoho read: %d fixture referrer audience row(s)", len(rows))
        return ReferrerAudience(rows=rows, truncated=False)

    def fetch_send_queue_counts(self, *, date_ist: date) -> SendQueueCounts:
        prefixes = tuple(_referral_template_prefixes())
        referral, other = Counter(), Counter()
        for row in _DEMO_SEND_QUEUE_ROWS:
            bucket = referral if row["Template_Name"].startswith(prefixes) else other
            bucket[row["Queue_Status"]] += 1
        logger.info(
            "[demo] Zoho read: fixture send-queue counts for %s: referral=%s other=%s",
            date_ist, dict(referral), dict(other),
        )
        return SendQueueCounts(
            date_ist=date_ist.isoformat(), referral=dict(referral), other=dict(other),
        )


def _referral_template_prefixes() -> list:
    return list(
        resolve(
            SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_KEY,
            default=SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_DEFAULT,
        )
    )


class LiveZohoReadAdapter:
    """Live read adapter. Refuses without ZOHO_* read config.

    READ-ONLY by construction: it only ever issues GETs against Contacts/Leads search.
    It never writes and never sets conversion/account status internally — status still
    arrives solely through the webhook ingest path (guardrail #2). What it returns is
    *enrichment* (who the referrer is, their Zoho-held account facts), which the
    profile view renders as clearly Zoho-sourced.
    """

    def __init__(self, http: ZohoHttpClient | None = None):
        # Constructing the shared client reads + validates ZOHO_* creds, so this
        # adapter still refuses to exist without them (fail loud, never silently live).
        self.http = http or ZohoHttpClient()

    def fetch_contact_by_client_id(self, *, client_id: str) -> ZohoContact:
        """Find the referrer's Zoho Contact by ClientId and return enrichment.

        doc-08 B4: Contacts stores the field as `ClientId` (the `Referrers` module
        uses `Client_Id`). We search Contacts on `ClientId`; `_norm_contact` already
        tolerates either spelling on the way back.

        A no-match is a NORMAL outcome (an open-ended referrer need not be a PIFS
        contact), not an error: Zoho answers 204/empty and we return an unmatched
        ZohoContact so the view renders "— not on file —" rather than breaking.
        """
        if not client_id:
            return ZohoContact(client_id=client_id, matched=False)

        resp = self.http.get(
            "/crm/v8/Contacts/search",
            params={
                "criteria": f"(ClientId:equals:{client_id})",
                "fields": ",".join(CONTACT_ENRICHMENT_FIELDS),
                "per_page": 1,
            },
        )
        rows = resp.get("data") or []
        if not rows:
            logger.info("Zoho read: no Contact for ClientId=%s", client_id)
            return ZohoContact(client_id=client_id, matched=False)
        logger.info("Zoho read: matched Contact for ClientId=%s", client_id)
        return _norm_contact(client_id, rows[0])

    def fetch_referred_people(self, *, referrer_client_id: str) -> ReferredPeople:
        """People this referrer introduced — the Referred-People tab.

        Sourced from Zoho Leads carrying `Referrer_Client_Id` (the field GoRefer's
        own WRITE leg stamps, and the field Ashok's manual leads carry). Leads that
        converted hold the account facts, so one search answers the whole tab.

        Deliberately Leads-only: a converted person also exists as a Contact, but
        joining both modules here would double-count the same person under two
        shapes. Conversion truth for the journey still comes from the webhook —
        this is display enrichment, not attribution.
        """
        if not referrer_client_id:
            return ReferredPeople(referrer_client_id=referrer_client_id, people=[])

        resp = self.http.get(
            "/crm/v8/Leads/search",
            params={
                "criteria": f"(Referrer_Client_Id:equals:{referrer_client_id})",
                "fields": ",".join(REFERRED_PERSON_FIELDS),
                "per_page": REFERRED_PEOPLE_PAGE_SIZE,
            },
        )
        rows = resp.get("data") or []
        people = [_norm_referred_person(r) for r in rows]
        logger.info(
            "Zoho read: %d referred person(s) for ClientId=%s", len(people), referrer_client_id
        )
        return ReferredPeople(referrer_client_id=referrer_client_id, people=people)

    def fetch_referrer_audience(self) -> ReferrerAudience:
        """The full referrer audience — decision ⑫'s Zoho-synced referrer list.

        Sourced from the `Referrers` custom module (Zoho module API name `Referrers`,
        internal id `CustomModule3`) via the plain record-LIST endpoint (no `criteria`
        — a `/search` call requires one, and the sync wants every row, not a filtered
        subset). Same reasoning as `zoho.reconcile.fetch_opened_contacts`: NOT COQL —
        the live refresh token has no COQL scope (`/crm/v8/coql` returns
        `OAUTH_SCOPE_MISMATCH`); the list/search endpoints need no new permission.

        Field map -> `ZohoReferrerRow`: `Client_Id`, `Mobile`, `Name` (the module's
        primary field), `Created_Time` (the drip anchor, decision ⑪). No `language`
        field exists on this module (verified via `getFields`) — every row comes back
        with `language=""`, so decision ⑮'s mapping always falls back to English until
        Zoho adds one.

        Paginated with a hard stop (`_REFERRERS_MAX_PAGES`); hitting the cap sets
        `truncated=True` so the sync task can refuse to deactivate "missing" rows off
        a partial picture.
        """
        rows: list[ZohoReferrerRow] = []
        page = 1
        truncated = False
        while page <= _REFERRERS_MAX_PAGES:
            resp = self.http.get(
                "/crm/v8/Referrers",
                params={
                    "fields": "Client_Id,Mobile,Name,Created_Time",
                    "per_page": _REFERRERS_PAGE_SIZE,
                    "page": page,
                    "sort_by": "Created_Time",
                    "sort_order": "asc",
                },
            )
            batch = (resp or {}).get("data") or []
            for raw in batch:
                client_id = (raw.get("Client_Id") or "").strip()
                if not client_id:
                    continue  # a referrer row with no id cannot be messaged or matched
                created = raw.get("Created_Time")
                rows.append(
                    ZohoReferrerRow(
                        client_id=client_id,
                        mobile=(raw.get("Mobile") or "").strip(),
                        name=(raw.get("Name") or "").strip(),
                        language="",  # no Language field on this module today
                        record_created_at=_parse_zoho_datetime(created),
                    )
                )
            info = (resp or {}).get("info") or {}
            if not batch or not info.get("more_records"):
                break
            page += 1
        else:
            truncated = True
            logger.warning(
                "Zoho read: fetch_referrer_audience hit the %d-page cap — result is PARTIAL",
                _REFERRERS_MAX_PAGES,
            )
        logger.info(
            "Zoho read: %d referrer audience row(s) fetched (truncated=%s)", len(rows), truncated
        )
        return ReferrerAudience(rows=rows, truncated=truncated)

    def fetch_send_queue_counts(self, *, date_ist: date) -> SendQueueCounts:
        """Per-status WA_Send_Queue counts for one IST business date, grouped
        referral-vs-other (decision ⑭) — the digest's future messaging block (W4).

        Sourced from the `WA_Send_Queue` custom module (`CustomModule5`) via
        `/search` on `Business_Date` (a plain date field). Same NOT-COQL reasoning
        as `fetch_referrer_audience`. Every row is counted: the grouping-rule config
        key `SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_KEY` decides which `Template_Name`
        prefixes count as "referral"; anything else (e.g. `angel_one_*`,
        `stay_connected_*` legacy other-broker broadcasts) is "other" — never
        dropped, since every stream burns the same phone number's quality rating.
        An unrecognized `Queue_Status` value rolls into the `OTHER` status bucket
        within its group.
        """
        prefixes = tuple(_referral_template_prefixes())
        referral, other = Counter(), Counter()
        page = 1
        truncated = False
        while page <= _SEND_QUEUE_MAX_PAGES:
            resp = self.http.get(
                "/crm/v8/WA_Send_Queue/search",
                params={
                    "criteria": f"(Business_Date:equals:{date_ist.isoformat()})",
                    "fields": "Queue_Status,Template_Name",
                    "per_page": _SEND_QUEUE_PAGE_SIZE,
                    "page": page,
                },
            )
            batch = (resp or {}).get("data") or []
            for raw in batch:
                status = (raw.get("Queue_Status") or "").strip()
                if status not in _KNOWN_QUEUE_STATUSES:
                    status = _UNKNOWN_STATUS_BUCKET
                template = (raw.get("Template_Name") or "").strip()
                bucket = referral if template.startswith(prefixes) else other
                bucket[status] += 1
            info = (resp or {}).get("info") or {}
            if not batch or not info.get("more_records"):
                break
            page += 1
        else:
            truncated = True
            logger.warning(
                "Zoho read: fetch_send_queue_counts(%s) hit the %d-page cap — counts are PARTIAL",
                date_ist, _SEND_QUEUE_MAX_PAGES,
            )
        logger.info(
            "Zoho read: send-queue counts for %s: referral=%s other=%s (truncated=%s)",
            date_ist, dict(referral), dict(other), truncated,
        )
        return SendQueueCounts(
            date_ist=date_ist.isoformat(), referral=dict(referral), other=dict(other),
            truncated=truncated,
        )


def _parse_zoho_datetime(raw: str | None):
    """Parse a Zoho ISO-8601 datetime (`2026-07-26T20:55:16+05:30`) or return None."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Zoho read: unparseable Created_Time %r", raw)
        return None


def get_zoho_read_adapter():
    """Select the read adapter from the EFFECTIVE flag (admin override -> env default).

    Demo default (flag off) is the fixture-backed LogOnly adapter. Resolved rather than
    raw env so the Settings checkbox actually governs enrichment.
    """
    from apps.config.integration_flags import ENABLE_ZOHO_READ, resolve_flag

    if resolve_flag(ENABLE_ZOHO_READ):
        return LiveZohoReadAdapter()
    return LogOnlyZohoReadAdapter()


# --- Demo fixtures ---------------------------------------------------------------
# Keyed by ClientId; mirror the shape of real Zoho Contact fields (incl. the
# Client_Id/ClientId inconsistency is irrelevant here since we key the dict directly).
# These power the Referral Profile in demo mode with Zoho flags OFF.
_DEMO_CONTACTS = {
    "RJ4521": {
        "Full_Name": "Rajesh Joshi",
        "Mobile": "9876504321",
        "Email": "rajesh.joshi.demo@example.com",
        "Mailing_City": "Pune",
        "Mailing_State": "MH",
        "Mailing_Country": "India",
        "Profession": "Salaried — IT",
        "Account_Status": "Active",
        "Account_Opened_On": "2019-03-12",
        "Is_Active_Investor": True,
        "IsReferrer": True,
        "Partner_Id": "ZMPHZC",
        "Referral_Bonus": "Eligible",
        "Referral_Bonus_Amount": "",  # amounts live only in the Zerodha Console
        "Email_Opt_Out": False,
        "WhatsApp_Opt_Out": False,
        "Do_not_contact": False,
    },
    "DA1707": {
        "Full_Name": "Amit Deshpande",
        "Mobile": "9876504322",
        "Email": "amit.deshpande.demo@example.com",
        "Mailing_City": "Mumbai",
        "Mailing_State": "MH",
        "Mailing_Country": "India",
        "Profession": "Self-employed",
        "Account_Status": "Active",
        "Account_Opened_On": "2020-08-01",
        "Is_Active_Investor": True,
        "IsReferrer": True,
        "Partner_Id": "ZMPHZC",
    },
}

_DEMO_REFERRED = {
    "RJ4521": [
        {"name": "Sunil Kamble", "city": "Mumbai", "profession": "Salaried — Banking",
         "partner": "Zerodha", "account_status": "Account opened", "opened_on": "2026-06-15",
         "reward": "Eligible"},
        {"name": "Anita Rao", "city": "Delhi", "profession": "Self-employed",
         "partner": "Zerodha", "account_status": "Lead — in KYC", "opened_on": None, "reward": None},
        {"name": None, "city": "Mumbai", "profession": None, "partner": "Zerodha",
         "account_status": "Lead captured", "opened_on": None, "reward": None},
    ],
}

# T-126 (W3) fixtures — mirror the LIVE Referrers/WA_Send_Queue shapes captured at
# intake (2026-08-13/14): Client_Id like RJ4521/CS4475/OX8218, no language field, a
# nullable Mobile; queue rows show real statuses (SENT/FAILED/PENDING/
# SUPPRESSED_CAPPED/SUPPRESSED_INVALID) plus one deliberately unrecognized value to
# exercise the OTHER bucket, and both a "gr_"-prefixed referral template and a
# legacy other-broker template to exercise the referral/other split.
_DEMO_REFERRER_AUDIENCE = [
    {
        "client_id": "RJ4521", "mobile": "9876504321", "name": "Rajesh Joshi",
        "language": "", "record_created_at": datetime(2026, 3, 12, 10, 0, 0),
    },
    {
        "client_id": "DA1707", "mobile": "9876504322", "name": "Amit Deshpande",
        "language": "", "record_created_at": datetime(2026, 6, 1, 9, 30, 0),
    },
    {
        # A real-shape edge case: Mobile blank on the Zoho side (seen live on
        # FWW808/XJ9068) — the sync must still upsert the row, just unmessageable.
        "client_id": "FWW808", "mobile": "", "name": "FWW808",
        "language": "", "record_created_at": datetime(2026, 7, 26, 20, 55, 16),
    },
]

_DEMO_SEND_QUEUE_ROWS = [
    {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "SENT"},
    {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "SENT"},
    {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "FAILED"},
    {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "PENDING"},
    {"Template_Name": "gorefer_referrer_prospect_pending_en_2026_07_26_v5",
     "Queue_Status": "SUPPRESSED_CAPPED"},
    {"Template_Name": "gr_platform_gorefer_login_otp_en_2026_07_21", "Queue_Status": "SUPPRESSED_INVALID"},
    {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "QUEUED_UNKNOWN"},
    {"Template_Name": "angel_one_referral_broadcast_en", "Queue_Status": "SENT"},
    {"Template_Name": "angel_one_referral_broadcast_en", "Queue_Status": "FAILED"},
    {"Template_Name": "stay_connected_monthly_update_en", "Queue_Status": "SENT"},
]
