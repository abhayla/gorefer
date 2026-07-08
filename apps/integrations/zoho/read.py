"""Zoho READ enrichment adapter behind the doc-08 contract (M9, Part A).

READ-ONLY. This adapter NEVER writes to Zoho and NEVER sets conversion/account status
internally — status still comes only through the webhook ingest path (guardrail #2).
It enriches the Referral Profile top band + Referred-People tab by matching a referrer
to their Zoho Contact by ClientId (doc-08 B4).

`ENABLE_ZOHO_READ` gates real calls (independent of ZOHO_WRITE, which stays OFF for
PIFS — Ashok enters Zoho leads manually, DF-9):
  - false (default, CI/demo): LogOnlyZohoReadAdapter returns SEEDED FIXTURES, no live
    call — the whole Referral Profile works offline.
  - true (creds present): LiveZohoReadAdapter reads ZOHO_* config; real HTTP wiring
    lands with Zoho sandbox verification. Refuses to run without config.

doc-08 B4 field-name note: `ClientId` (Contacts) vs `Client_Id` (Referrers) — the
adapter normalizes both. Missing values come back as None so the view renders the
config "— not on file —" marker.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from gorefer.flags import FeatureFlags

logger = logging.getLogger("gorefer.zoho.read")

# The Zoho Contact fields pulled for the Referral Profile top band (DA M9 Part A).
# Kept as data (not scattered literals) so adding a field is config, not code surgery.
CONTACT_ENRICHMENT_FIELDS = (
    "Full_Name",
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


@dataclass
class ZohoContact:
    """Normalized Zoho Contact enrichment for one referrer (matched by ClientId).

    All fields optional — a missing Zoho value is None, rendered as "— not on file —".
    """

    client_id: str
    full_name: str | None = None
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


class LiveZohoReadAdapter:  # pragma: no cover - exercised only with ENABLE_ZOHO_READ=true
    """Live read adapter. Refuses without ZOHO_* read config; HTTP wiring lands with
    Zoho sandbox verification. Reads only — never writes, never sets status."""

    def __init__(self):
        self.client_id = os.environ.get("ZOHO_CLIENT_ID", "")
        self.client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN", "")
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise RuntimeError("ZOHO_* read credentials not configured — cannot run live.")

    def fetch_contact_by_client_id(self, *, client_id: str) -> ZohoContact:
        raise NotImplementedError("Live Zoho READ is wired during sandbox verification.")

    def fetch_referred_people(self, *, referrer_client_id: str) -> ReferredPeople:
        raise NotImplementedError("Live Zoho READ is wired during sandbox verification.")


def get_zoho_read_adapter():
    """Select the read adapter. Re-reads env so a test/flag toggle is honoured; demo
    default (flag off) is the fixture-backed LogOnly adapter."""
    if FeatureFlags.from_env().ENABLE_ZOHO_READ:
        return LiveZohoReadAdapter()
    return LogOnlyZohoReadAdapter()


# --- Demo fixtures ---------------------------------------------------------------
# Keyed by ClientId; mirror the shape of real Zoho Contact fields (incl. the
# Client_Id/ClientId inconsistency is irrelevant here since we key the dict directly).
# These power the Referral Profile in demo mode with Zoho flags OFF.
_DEMO_CONTACTS = {
    "RJ4521": {
        "Full_Name": "Rajesh Joshi",
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
