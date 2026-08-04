"""Live Zoho READ HTTP bodies (DA MISSION 2026-07-16, item 2).

`LiveZohoReadAdapter` previously raised NotImplementedError, so flipping
ENABLE_ZOHO_READ with real creds would have crashed the Referral Profile. These
tests pin the REQUEST shape (the half a sandbox run can't cheaply retro-fix — a
wrong field api-name fails identically every time) and the no-match path.

Proven here:
  1. Contacts search by ClientId with the enrichment fields (doc-08 B4);
  2. a no-match is a NORMAL unmatched result, never an exception (open-ended
     referrers need not be PIFS contacts — ADR-001);
  3. Leads search by Referrer_Client_Id backs the Referred-People tab;
  4. the TRUE open date (Account_Opened_On, ADR-017) is what's read — never a
     sync/import date;
  5. the adapter refuses to construct without creds (fail loud, never silently live);
  6. guardrail #2: the READ leg issues GETs only — it never writes.
"""
from __future__ import annotations

from unittest import mock

import pytest

from apps.integrations.zoho.read import (
    CONTACT_ENRICHMENT_FIELDS,
    LiveZohoReadAdapter,
    LogOnlyZohoReadAdapter,
)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")


# --- 1. contact enrichment: request shape ----------------------------------------

def test_live_read_searches_contacts_by_client_id(creds):
    """Contacts/search on ClientId, asking for the enrichment fields (doc-08 B4)."""
    adapter = LiveZohoReadAdapter()
    seen = {}

    def fake_get(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return {"data": [{
            "Full_Name": "Rajesh Joshi",
            "Mailing_City": "Pune",
            "Account_Status": "Active",
            "Account_Opened_On": "2019-03-12",
        }]}

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        contact = adapter.fetch_contact_by_client_id(client_id="RJ4521")

    assert seen["path"] == "/crm/v8/Contacts/search"
    # doc-08 B4: Contacts spells it `ClientId` (Referrers uses `Client_Id`).
    assert seen["params"]["criteria"] == "(ClientId:equals:RJ4521)"
    requested = seen["params"]["fields"].split(",")
    assert set(requested) == set(CONTACT_ENRICHMENT_FIELDS)
    assert contact.matched is True
    assert contact.full_name == "Rajesh Joshi"
    assert contact.client_id == "RJ4521"


def test_live_read_reads_the_true_account_opened_date(creds):
    """ADR-017: analytics run off Zoho's TRUE open date, never the import date."""
    adapter = LiveZohoReadAdapter()

    def fake_get(path, *, params=None):
        return {"data": [{"Full_Name": "Amit", "Account_Opened_On": "2020-08-01"}]}

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        contact = adapter.fetch_contact_by_client_id(client_id="DA1707")

    assert "Account_Opened_On" in CONTACT_ENRICHMENT_FIELDS
    assert contact.account_opened_on == "2020-08-01"


# --- 2. no-match is normal, not an error -----------------------------------------

def test_live_read_no_match_returns_unmatched_not_an_error(creds):
    """An open-ended referrer need not be a PIFS Contact (ADR-001). Zoho answers 204
    (empty) and the profile must render '— not on file —', not blow up."""
    adapter = LiveZohoReadAdapter()

    with mock.patch.object(adapter.http, "get", return_value={}):
        contact = adapter.fetch_contact_by_client_id(client_id="ZZ0000")

    assert contact.matched is False
    assert contact.full_name is None
    assert contact.client_id == "ZZ0000"


def test_live_read_blank_client_id_makes_no_call(creds):
    """A blank id can't match anything — don't spend an HTTP round-trip proving it."""
    adapter = LiveZohoReadAdapter()

    with mock.patch.object(adapter.http, "get") as get:
        contact = adapter.fetch_contact_by_client_id(client_id="")

    get.assert_not_called()
    assert contact.matched is False


# --- 3. referred people ----------------------------------------------------------

def test_live_read_searches_leads_by_referrer_client_id(creds):
    """The Referred-People tab reads Leads stamped with Referrer_Client_Id — the
    same field GoRefer's own WRITE leg stamps."""
    adapter = LiveZohoReadAdapter()
    seen = {}

    def fake_get(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return {"data": [
            {"Full_Name": "Sunil Kamble", "City": "Mumbai", "Account_Status": "Account opened",
             "Account_Opened_On": "2026-06-15", "Referral_Bonus": "Eligible"},
            {"City": "Delhi", "Account_Status": "Lead captured"},  # unnamed lead
        ]}

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        result = adapter.fetch_referred_people(referrer_client_id="RJ4521")

    assert seen["path"] == "/crm/v8/Leads/search"
    assert seen["params"]["criteria"] == "(Referrer_Client_Id:equals:RJ4521)"
    assert result.referrer_client_id == "RJ4521"
    assert len(result.people) == 2
    assert result.people[0].name == "Sunil Kamble"
    assert result.people[0].opened_on == "2026-06-15"
    # A blank Zoho value must normalize to None so the view shows "— not on file —".
    assert result.people[1].name is None


def test_live_read_referred_people_no_match_is_empty_list(creds):
    adapter = LiveZohoReadAdapter()

    with mock.patch.object(adapter.http, "get", return_value={}):
        result = adapter.fetch_referred_people(referrer_client_id="ZZ0000")

    assert result.people == []


def test_live_read_never_reads_a_reward_amount(creds):
    """Gap 4/7: reward AMOUNTS live only in the Zerodha Console. The referred-people
    read must carry eligibility wording only — never an amount field."""
    from apps.integrations.zoho.read import REFERRED_PERSON_FIELDS

    assert not any("Amount" in f for f in REFERRED_PERSON_FIELDS)


# --- 4. fail loud without creds --------------------------------------------------

def test_live_read_adapter_refuses_to_construct_without_creds(monkeypatch):
    """Never silently live: no creds => RuntimeError, not a quiet no-op."""
    for var in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        LiveZohoReadAdapter()


# --- 5. guardrail #2: READ never writes ------------------------------------------

def test_live_read_issues_only_gets(creds):
    """The READ leg must never POST. If it ever gains a write, this fails."""
    adapter = LiveZohoReadAdapter()

    with mock.patch.object(adapter.http, "get", return_value={}) as get, \
            mock.patch.object(adapter.http, "post_json") as post:
        adapter.fetch_contact_by_client_id(client_id="RJ4521")
        adapter.fetch_referred_people(referrer_client_id="RJ4521")

    assert get.call_count == 2
    post.assert_not_called()


# --- 6. a Zoho outage must not take the profile down ------------------------------

@pytest.mark.django_db
def test_profile_survives_a_zoho_read_outage():
    """Enrichment is decoration; the GoRefer-owned numbers are the page.

    Wiring the live READ introduced real network I/O on the profile path. Without
    this, a Zoho outage / expired token would 500 the whole Referral Profile and take
    the clicks + leads (which need no Zoho at all) down with it. Degrade instead.
    """
    from apps.dashboard import profile

    boom = mock.MagicMock()
    boom.fetch_contact_by_client_id.side_effect = RuntimeError("Zoho HTTP 502: down")
    boom.fetch_referred_people.side_effect = RuntimeError("Zoho HTTP 502: down")

    with mock.patch.object(profile, "get_crm_read_port", return_value=boom):
        band = profile.top_band(None, "RJ4521")
        people = profile.referred_people(None, "RJ4521")

    # The page renders: enrichment degrades to unmatched, GoRefer's own data survives.
    assert people == []
    assert band is not None


# --- 7. demo parity: the log-only adapter still answers offline -------------------

def test_demo_read_adapter_needs_no_creds_and_no_network(monkeypatch):
    """Flag off => fixtures, zero network, no creds required (demo mode holds)."""
    for var in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    contact = LogOnlyZohoReadAdapter().fetch_contact_by_client_id(client_id="RJ4521")
    assert contact.matched is True and contact.full_name == "Rajesh Joshi"
