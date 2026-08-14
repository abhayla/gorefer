"""T-126 (W3) — CrmReadPort.fetch_referrer_audience + fetch_send_queue_counts.

Proven here:
  1. `fetch_referrer_audience` lists the Zoho `Referrers` module (NOT COQL, NOT
     `/search` — a full audience needs no criteria), maps Client_Id/Mobile/Name/
     Created_Time, and always returns language="" (no Language field exists on the
     live module);
  2. pagination follows `more_records` and a truncated fetch is flagged, never
     silently treated as complete;
  3. `fetch_send_queue_counts` searches WA_Send_Queue by Business_Date, groups
     referral-vs-other by the configurable template-name-prefix rule, and rolls an
     unrecognized status into the OTHER bucket rather than dropping it;
  4. guardrail #2: both new methods issue GETs only, never a write;
  5. the LogOnly adapter answers both offline, with no network and no creds.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest import mock

import pytest

from apps.integrations.zoho.read import (
    SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_DEFAULT,
    LiveZohoReadAdapter,
    LogOnlyZohoReadAdapter,
)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")


# --- 1. referrer audience: request shape + field map ------------------------------

def test_live_fetch_referrer_audience_lists_referrers_module_not_search(creds):
    adapter = LiveZohoReadAdapter()
    seen = {}

    def fake_get(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return {
            "data": [{
                "Client_Id": "RJ4521", "Mobile": "9876504321", "Name": "Rajesh Joshi",
                "Created_Time": "2026-03-12T10:00:00+05:30",
            }],
            "info": {"more_records": False},
        }

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        audience = adapter.fetch_referrer_audience()

    assert seen["path"] == "/crm/v8/Referrers"  # list endpoint, no "/search" suffix
    assert "criteria" not in seen["params"]
    assert set(seen["params"]["fields"].split(",")) == {"Client_Id", "Mobile", "Name", "Created_Time"}
    assert len(audience.rows) == 1
    row = audience.rows[0]
    assert row.client_id == "RJ4521"
    assert row.mobile == "9876504321"
    assert row.name == "Rajesh Joshi"
    assert row.language == ""  # no Language field on the live module
    assert row.record_created_at == datetime.fromisoformat("2026-03-12T10:00:00+05:30")
    assert audience.truncated is False


def test_live_fetch_referrer_audience_skips_blank_client_id(creds):
    adapter = LiveZohoReadAdapter()

    def fake_get(path, *, params=None):
        return {
            "data": [
                {"Client_Id": "", "Mobile": "9876500000", "Name": "No id"},
                {"Client_Id": "OK1234", "Mobile": "9876500001", "Name": "Has id",
                 "Created_Time": "2026-01-01T00:00:00+05:30"},
            ],
            "info": {"more_records": False},
        }

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        audience = adapter.fetch_referrer_audience()

    assert [r.client_id for r in audience.rows] == ["OK1234"]


def test_live_fetch_referrer_audience_paginates(creds):
    adapter = LiveZohoReadAdapter()
    pages = {
        1: {"data": [{"Client_Id": "A1", "Mobile": "9876500001", "Name": "A",
                       "Created_Time": "2026-01-01T00:00:00+05:30"}],
            "info": {"more_records": True}},
        2: {"data": [{"Client_Id": "A2", "Mobile": "9876500002", "Name": "B",
                       "Created_Time": "2026-01-02T00:00:00+05:30"}],
            "info": {"more_records": False}},
    }

    def fake_get(path, *, params=None):
        return pages[params["page"]]

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        audience = adapter.fetch_referrer_audience()

    assert [r.client_id for r in audience.rows] == ["A1", "A2"]
    assert audience.truncated is False


def test_live_fetch_referrer_audience_flags_truncation_at_page_cap(creds, monkeypatch):
    import apps.integrations.zoho.read as read_mod

    monkeypatch.setattr(read_mod, "_REFERRERS_MAX_PAGES", 2)
    adapter = LiveZohoReadAdapter()

    def fake_get(path, *, params=None):
        n = params["page"]
        return {
            "data": [{"Client_Id": f"P{n}", "Mobile": "9876500000", "Name": "x",
                       "Created_Time": "2026-01-01T00:00:00+05:30"}],
            "info": {"more_records": True},  # always more — forces the cap
        }

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        audience = adapter.fetch_referrer_audience()

    assert audience.truncated is True
    assert len(audience.rows) == 2  # exactly the capped page count


# --- 2. send-queue counts: request shape + grouping --------------------------------

@pytest.mark.django_db
def test_live_fetch_send_queue_counts_searches_by_business_date(creds):
    adapter = LiveZohoReadAdapter()
    seen = {}

    def fake_get(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return {"data": [], "info": {"more_records": False}}

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        adapter.fetch_send_queue_counts(date_ist=date(2026, 8, 14))

    assert seen["path"] == "/crm/v8/WA_Send_Queue/search"
    assert seen["params"]["criteria"] == "(Business_Date:equals:2026-08-14)"
    assert set(seen["params"]["fields"].split(",")) == {"Queue_Status", "Template_Name"}


@pytest.mark.django_db
def test_live_fetch_send_queue_counts_groups_referral_vs_other_and_keeps_unknown_status(creds):
    adapter = LiveZohoReadAdapter()

    def fake_get(path, *, params=None):
        return {
            "data": [
                {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "SENT"},
                {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31", "Queue_Status": "FAILED"},
                {"Template_Name": "gr_platform_gorefer_refrecord_en_2026_07_31",
                 "Queue_Status": "WEIRD_NEW_STATUS"},
                {"Template_Name": "angel_one_referral_broadcast_en", "Queue_Status": "SENT"},
            ],
            "info": {"more_records": False},
        }

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        counts = adapter.fetch_send_queue_counts(date_ist=date(2026, 8, 14))

    assert counts.referral == {"SENT": 1, "FAILED": 1, "OTHER": 1}
    assert counts.other == {"SENT": 1}
    assert counts.date_ist == "2026-08-14"
    assert counts.truncated is False


def test_live_fetch_send_queue_counts_grouping_rule_is_configurable(creds, monkeypatch):
    """The prefix list is a cascade-resolved config row (decision ⑭), not a literal."""
    from apps.integrations.zoho import read as read_mod

    monkeypatch.setattr(
        read_mod, "resolve",
        lambda key, **kw: ["custom_prefix_"] if key == read_mod.SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_KEY
        else kw.get("default"),
    )
    adapter = LiveZohoReadAdapter()

    def fake_get(path, *, params=None):
        return {
            "data": [{"Template_Name": "custom_prefix_x", "Queue_Status": "SENT"},
                      {"Template_Name": "gr_platform_gorefer_refrecord", "Queue_Status": "SENT"}],
            "info": {"more_records": False},
        }

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        counts = adapter.fetch_send_queue_counts(date_ist=date(2026, 8, 14))

    assert counts.referral == {"SENT": 1}  # only the reconfigured prefix counts
    assert counts.other == {"SENT": 1}     # the usual "gr_" prefix now falls to "other"


def test_default_referral_prefixes_cover_the_gorefer_template_family():
    assert "gr_" in SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_DEFAULT
    assert "gorefer_" in SEND_QUEUE_REFERRAL_TEMPLATE_PREFIXES_DEFAULT


# --- 3. guardrail #2: both new methods issue GETs only -----------------------------

@pytest.mark.django_db
def test_live_read_audience_and_queue_issue_only_gets(creds):
    adapter = LiveZohoReadAdapter()

    with mock.patch.object(adapter.http, "get", return_value={"data": [], "info": {}}) as get, \
            mock.patch.object(adapter.http, "post_json") as post:
        adapter.fetch_referrer_audience()
        adapter.fetch_send_queue_counts(date_ist=date(2026, 8, 14))

    assert get.call_count == 2
    post.assert_not_called()


# --- 4. demo parity: LogOnly answers both offline -----------------------------------

def test_demo_fetch_referrer_audience_needs_no_creds_and_no_network(monkeypatch):
    for var in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    audience = LogOnlyZohoReadAdapter().fetch_referrer_audience()
    assert len(audience.rows) >= 1
    assert audience.truncated is False


@pytest.mark.django_db
def test_demo_fetch_send_queue_counts_needs_no_creds_and_groups_referral_vs_other(monkeypatch):
    for var in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    counts = LogOnlyZohoReadAdapter().fetch_send_queue_counts(date_ist=date(2026, 8, 14))
    assert sum(counts.referral.values()) > 0
    assert sum(counts.other.values()) > 0
