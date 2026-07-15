"""Model 2 — Zoho WRITE as an idempotent upsert keyed on normalized mobile.

DA decision 2026-07-15 (supersedes DF-9): ENABLE_ZOHO_WRITE goes ON for PIFS, but
GoRefer must NEVER blind-create in Zoho. These tests prove:
  1. the write is an UPSERT with server-side dedup (duplicate_check_fields=[Mobile]);
  2. re-submitting the same form does NOT create a 2nd lead and does NOT lose the
     GoRefer journey-reference (#10);
  3. phone normalization uses the ONE canonical helper (a punctuated/unprefixed
     mobile dedups to the same person);
  4. LiveZohoAdapter refuses to construct without creds (fail loud, not silently live);
  5. flag off => log-only, zero network;
  6. DPDP: PII never reaches the immutable event log.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import Client

from apps.common.phone import normalize_phone
from apps.events.models import Event
from apps.integrations.zoho.adapter import (
    DUPLICATE_CHECK_FIELDS,
    GOREFER_REFERENCE_FIELD,
    LeadWriteResult,
    LiveZohoAdapter,
    LogOnlyZohoAdapter,
    build_lead_record,
    get_zoho_adapter,
    gorefer_reference_for,
)
from apps.referrals.models import Lead, Prospect

# --- helpers ---------------------------------------------------------------------

def _capture(client, *, client_id="RJ4521", mobile="9876543210", name="Rahul Sharma"):
    """Drive the real capture-first endpoint (same path the landing form uses)."""
    client.get(f"/r/{client_id}", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    return client.post(
        "/api/leads/",
        data={
            "client_id": client_id, "name": name, "mobile": mobile,
            "email": "rahul@example.com", "city": "Prayagraj", "consent": True,
        },
        content_type="application/json",
    )


class _RecordingAdapter:
    """Stands in for the live adapter: records calls, simulates Zoho's server-side
    dedup on Mobile (insert first time, update thereafter)."""

    def __init__(self):
        self.calls = []
        self._seen: dict[str, str] = {}

    def upsert_lead(self, *, payload: dict, gorefer_reference: str) -> LeadWriteResult:
        record = build_lead_record(payload=payload, gorefer_reference=gorefer_reference)
        self.calls.append(record)
        mobile = record["Mobile"]
        if mobile in self._seen:
            return LeadWriteResult(
                zoho_lead_id=self._seen[mobile],
                gorefer_reference=gorefer_reference,
                action="update",
            )
        zid = f"zoho-{len(self._seen) + 1}"
        self._seen[mobile] = zid
        return LeadWriteResult(
            zoho_lead_id=zid, gorefer_reference=gorefer_reference, action="insert"
        )


# --- 1. upsert shape / server-side dedup -----------------------------------------

def test_record_carries_normalized_mobile_and_journey_reference():
    record = build_lead_record(
        payload={"name": "Rahul", "mobile": "98765 43210", "referred_by": "RJ4521"},
        gorefer_reference="GR-7",
    )
    assert record["Mobile"] == "919876543210"  # canonical helper applied
    assert record[GOREFER_REFERENCE_FIELD] == "GR-7"
    assert record["Referrer_Client_Id"] == "RJ4521"


def test_dedup_is_server_side_on_mobile():
    """Model 2: Zoho decides create-vs-update. Guards against a regression back to
    a hand-rolled search-then-create (which races)."""
    assert DUPLICATE_CHECK_FIELDS == ["Mobile"]


def test_live_upsert_posts_duplicate_check_fields(monkeypatch):
    """The live call must hit /Leads/upsert with duplicate_check_fields=[Mobile]."""
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()
    posted = {}

    def fake_post(url, *, data, headers):
        posted["url"] = url
        if "oauth" in url:
            return {"access_token": "tok"}
        posted["body"] = json.loads(data.decode())
        return {"data": [{"code": "SUCCESS", "action": "insert", "details": {"id": "zoho-1"}}]}

    with mock.patch.object(LiveZohoAdapter, "_post", side_effect=fake_post):
        result = adapter.upsert_lead(
            payload={"name": "Rahul", "mobile": "9876543210"}, gorefer_reference="GR-1"
        )

    assert posted["url"].endswith("/crm/v8/Leads/upsert")
    assert posted["body"]["duplicate_check_fields"] == ["Mobile"]
    assert posted["body"]["data"][0]["Mobile"] == "919876543210"
    assert result.zoho_lead_id == "zoho-1" and result.action == "insert"


def test_live_upsert_refuses_without_dedup_key(monkeypatch):
    """No mobile => an upsert degrades to a blind create. Must refuse, not create."""
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()
    with pytest.raises(RuntimeError, match="no normalized mobile"):
        adapter.upsert_lead(payload={"name": "NoPhone", "mobile": ""}, gorefer_reference="GR-1")


# --- 2. idempotency: no double-create, reference never lost -----------------------

@pytest.mark.django_db(transaction=True)
def test_resubmit_does_not_create_second_lead_and_keeps_reference():
    """THE acceptance test: re-submitting the same form must not twin the lead."""
    call_command("seed_program")
    rec = _RecordingAdapter()
    with mock.patch("apps.referrals.lead_service.get_zoho_adapter", return_value=rec):
        assert _capture(Client()).status_code in (200, 201)
        assert _capture(Client()).status_code in (200, 201)  # same person, again

    leads = Lead.objects.filter(prospect__mobile="919876543210")
    assert leads.count() == 1, "re-submit created a 2nd GoRefer lead"
    assert Prospect.objects.filter(mobile="919876543210").count() == 1

    lead = leads.first()
    assert lead.gorefer_reference == gorefer_reference_for(lead.referral), (
        "journey-reference lost on re-run"
    )
    assert lead.zoho_lead_id == "zoho-1"
    # Zoho saw both writes, but both carried the SAME dedup key => update, not twin.
    assert {c["Mobile"] for c in rec.calls} == {"919876543210"}


def test_repeat_upsert_updates_rather_than_inserts():
    """A second upsert for the same mobile resolves to UPDATE, not a new record."""
    rec = _RecordingAdapter()
    payload = {"name": "Rahul", "mobile": "9876543210"}
    a = rec.upsert_lead(payload=payload, gorefer_reference="GR-1")
    b = rec.upsert_lead(payload=payload, gorefer_reference="GR-1")
    assert a.action == "insert" and b.action == "update"
    assert a.zoho_lead_id == b.zoho_lead_id  # same Zoho record, not a twin


@pytest.mark.django_db(transaction=True)
def test_punctuated_mobile_dedups_to_same_person():
    """Canonical helper reuse: '+91-98765 43210' and '9876543210' are one person.
    A forked normalizer here would silently split them into two Zoho leads."""
    call_command("seed_program")
    rec = _RecordingAdapter()
    with mock.patch("apps.referrals.lead_service.get_zoho_adapter", return_value=rec):
        _capture(Client(), mobile="9876543210")
        _capture(Client(), mobile="+91-98765 43210")

    assert {c["Mobile"] for c in rec.calls} == {"919876543210"}
    assert Prospect.objects.filter(mobile="919876543210").count() == 1
    assert normalize_phone("+91-98765 43210") == normalize_phone("9876543210")


@pytest.mark.django_db(transaction=True)
def test_zoho_failure_does_not_lose_the_lead():
    """Capture-first: a Zoho outage must not fail the request or drop the lead."""
    call_command("seed_program")
    boom = mock.Mock()
    boom.upsert_lead.side_effect = RuntimeError("Zoho HTTP 500")
    with mock.patch("apps.referrals.lead_service.get_zoho_adapter", return_value=boom):
        resp = _capture(Client())
    assert resp.status_code in (200, 201)  # request still succeeded
    assert Lead.objects.filter(prospect__mobile="919876543210").exists()  # survived


# --- 3. flag gating / fail-loud ---------------------------------------------------

def test_flag_off_selects_log_only_adapter_and_sends_nothing():
    """Demo default: ENABLE_ZOHO_WRITE=false => fixture/log-only adapter, zero network."""
    from gorefer.flags import flags as live_flags

    assert live_flags.ENABLE_ZOHO_WRITE is False, "demo default must keep Zoho WRITE off"
    assert isinstance(get_zoho_adapter(), LogOnlyZohoAdapter)


def test_flag_on_selects_live_adapter(monkeypatch):
    """Flipping the flag must select the LIVE adapter — proving the flag is the only
    thing standing between demo and a real write (and that it fails loud w/o creds)."""
    import dataclasses

    from gorefer.flags import flags as live_flags

    # flags is a FROZEN dataclass — swap in a modified copy rather than mutate.
    monkeypatch.setattr(
        "apps.integrations.zoho.adapter.flags",
        dataclasses.replace(live_flags, ENABLE_ZOHO_WRITE=True),
    )
    for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="credentials not configured"):
        get_zoho_adapter()


def test_log_only_adapter_is_deterministic_per_mobile():
    """Demo analogue of Zoho's dedup: same canonical mobile => same fake id."""
    a = LogOnlyZohoAdapter()
    r1 = a.upsert_lead(payload={"name": "R", "mobile": "9876543210"}, gorefer_reference="GR-1")
    r2 = a.upsert_lead(payload={"name": "R", "mobile": "+91 98765 43210"}, gorefer_reference="GR-1")
    assert r1.zoho_lead_id == r2.zoho_lead_id == "demo-zoho-919876543210"


def test_live_adapter_refuses_to_construct_without_creds(monkeypatch):
    """Fail LOUD, never silently live — same pattern as LiveZohoReadAdapter."""
    for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="ZOHO_.* credentials not configured"):
        LiveZohoAdapter()


# --- 4. DPDP ----------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_pii_never_reaches_the_immutable_event_log():
    call_command("seed_program")
    rec = _RecordingAdapter()
    with mock.patch("apps.referrals.lead_service.get_zoho_adapter", return_value=rec):
        _capture(Client())

    blob = json.dumps([e.metadata for e in Event.objects.all()])
    for pii in ("Rahul", "9876543210", "919876543210", "rahul@example.com", "Prayagraj"):
        assert pii not in blob, f"PII {pii!r} leaked into the event log"
