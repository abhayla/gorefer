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

from apps.common.phone import normalize_phone, to_zoho_mobile
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
    dedup on Mobile (insert first time, update thereafter).

    `existing` seeds records ALREADY in Zoho, keyed exactly as Zoho stores them
    (bare 10-digit) — so a format mismatch shows up as a spurious insert, which is
    precisely the silent twin the DA's 2026-07-15 correction is about.
    """

    def __init__(self, existing: dict[str, str] | None = None):
        self.calls = []
        self._seen: dict[str, str] = dict(existing or {})

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


# --- 0. Zoho mobile format: BARE 10-digit (DA correction 2026-07-15) --------------

def test_zoho_mobile_is_bare_10_digit_derived_from_canonical():
    """Zoho stores Indian mobiles with NO country code. The write leg must match that
    stored format or the upsert's dedup key misses and silently twins the lead."""
    assert to_zoho_mobile("919335179938") == "9335179938"   # strips 91
    assert to_zoho_mobile("9335179938") == "9335179938"     # already bare
    assert to_zoho_mobile("+91-93351 79938") == "9335179938"  # punctuated
    assert to_zoho_mobile("09335179938") == "9335179938"    # strips leading 0


def test_zoho_mobile_refuses_to_pad_a_malformed_number():
    """<10 digits => malformed. Never pad: a padded number is a WRONG number, and
    writing one into a CRM is worse than writing none."""
    assert to_zoho_mobile("12345") == ""
    assert to_zoho_mobile("") == ""
    assert to_zoho_mobile(None) == ""


def test_internal_format_is_unchanged_only_the_zoho_leg_reformats():
    """GoRefer internal + WATI keep the 91-prefix; only the Zoho write leg is bare."""
    assert normalize_phone("9335179938") == "919335179938"  # internal unchanged
    assert to_zoho_mobile("9335179938") == "9335179938"     # Zoho leg bare


# --- 1. upsert shape / server-side dedup -----------------------------------------

def test_record_carries_zoho_format_mobile_and_journey_reference():
    record = build_lead_record(
        payload={"name": "Rahul", "mobile": "98765 43210", "referred_by": "RJ4521"},
        gorefer_reference="GR-7",
    )
    assert record["Mobile"] == "9876543210"  # BARE 10-digit — Zoho's stored format
    assert record["Phone"] == "9876543210"
    assert record[GOREFER_REFERENCE_FIELD] == "GR-7"
    assert record["Referrer_Client_Id"] == "RJ4521"


def test_referrer_mobile_gets_the_same_bare_treatment():
    """DA correction #4 — Referrer_Mobile matches the same Zoho-stored format."""
    record = build_lead_record(
        payload={"name": "R", "mobile": "9876543210", "referrer_mobile": "919335179938"},
        gorefer_reference="GR-1",
    )
    assert record["Referrer_Mobile"] == "9335179938"


def test_dedup_is_server_side_on_mobile():
    """Model 2: Zoho decides create-vs-update. Guards against a regression back to
    a hand-rolled search-then-create (which races)."""
    assert DUPLICATE_CHECK_FIELDS == ["Mobile"]


def test_live_upsert_matches_the_da_confirmed_wire_contract(monkeypatch):
    """The live HTTP body must match the contract the DA proved against live Zoho.

    Confirmed by the DA against the PIFS org (COORDINATION 2026-07-16):
    POST /crm/v8/Leads/upsert · duplicate_check_fields:["Mobile"] · bare-10-digit
    Mobile · fields Last_Name/Mobile/GoRefer_Reference/Referrer_Client_Id/City ·
    response data[].code/action/details.id.

    This asserts the REQUEST shape, which is the half that a live sandbox run can't
    retro-fix cheaply: a wrong field api-name fails all 5 retries identically.
    """
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()
    posted = {}

    def fake_post_json(path, *, body):
        posted["path"] = path
        posted["body"] = body
        return {"data": [{"code": "SUCCESS", "action": "insert", "details": {"id": "zoho-1"}}]}

    with mock.patch.object(adapter.http, "post_json", side_effect=fake_post_json):
        result = adapter.upsert_lead(
            payload={
                "name": "Rahul",
                "mobile": "9876543210",
                "city": "Prayagraj",
                "referred_by": "RJ4521",
            },
            gorefer_reference="GR-1",
        )

    assert posted["path"] == "/crm/v8/Leads/upsert"
    assert posted["body"]["duplicate_check_fields"] == ["Mobile"]
    record = posted["body"]["data"][0]
    # BARE 10-digit — must match Zoho's stored format, not GoRefer's internal 91-form.
    assert record["Mobile"] == "9876543210"
    # Every field the DA confirmed Zoho accepts in one payload.
    assert record["Last_Name"] == "Rahul"
    assert record["GoRefer_Reference"] == "GR-1"
    assert record["Referrer_Client_Id"] == "RJ4521"
    assert record["City"] == "Prayagraj"
    assert result.zoho_lead_id == "zoho-1" and result.action == "insert"


def test_live_upsert_parses_action_update_on_replay(monkeypatch):
    """Replay must surface action=update — Model 2's no-twin guarantee, at the wire.

    The DA proved live that an identical re-call returns action=update with the SAME
    record id. This asserts we PARSE that correctly: if we mis-read the response and
    reported "insert", a real twin would be indistinguishable from a healthy replay.
    """
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()

    def fake_post_json(path, *, body):
        return {"data": [{
            "code": "SUCCESS",
            "action": "update",
            "duplicate_field": "Mobile",
            "details": {"id": "zoho-existing-1"},
        }]}

    with mock.patch.object(adapter.http, "post_json", side_effect=fake_post_json):
        result = adapter.upsert_lead(
            payload={"name": "Rahul", "mobile": "9876543210"}, gorefer_reference="GR-1"
        )

    assert result.action == "update", "replay must be reported as an update, never an insert"
    assert result.zoho_lead_id == "zoho-existing-1"


def test_live_upsert_raises_on_a_zoho_error_row(monkeypatch):
    """A non-SUCCESS row must raise, so the retry/backfill layer parks the lead.

    Zoho answers HTTP 200 with a per-row error code, so a caller that only checked
    the status code would record a phantom success and strand the lead invisibly —
    the exact failure the retry layer exists to prevent.
    """
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()

    def fake_post_json(path, *, body):
        return {"data": [{"code": "MANDATORY_NOT_FOUND", "message": "required field missing"}]}

    with mock.patch.object(adapter.http, "post_json", side_effect=fake_post_json):
        with pytest.raises(RuntimeError, match="MANDATORY_NOT_FOUND"):
            adapter.upsert_lead(
                payload={"name": "Rahul", "mobile": "9876543210"}, gorefer_reference="GR-1"
            )


def test_live_fetch_referrer_history_reads_true_open_dates(monkeypatch):
    """DF-4: the LAZY per-referrer history fetch (the primary mechanism; the all-time
    bulk backfill stays deferred).

    Must carry Zoho's TRUE Account_Opened_On (ADR-017) — keying history off the
    import date would stack every historical account onto day 1 and fake a spike.
    """
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()
    seen = {}

    def fake_get(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return {"data": [{"Full_Name": "Sunil", "Account_Opened_On": "2019-04-02"}]}

    with mock.patch.object(adapter.http, "get", side_effect=fake_get):
        history = adapter.fetch_referrer_history(referrer_client_id="RJ4521")

    assert seen["path"] == "/crm/v8/Leads/search"
    assert seen["params"]["criteria"] == "(Referrer_Client_Id:equals:RJ4521)"
    assert "Account_Opened_On" in seen["params"]["fields"]
    assert history.referrer_client_id == "RJ4521"
    assert history.conversions[0]["Account_Opened_On"] == "2019-04-02"


def test_live_fetch_referrer_history_blank_id_makes_no_call(monkeypatch):
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()

    with mock.patch.object(adapter.http, "get") as get:
        history = adapter.fetch_referrer_history(referrer_client_id="")

    get.assert_not_called()
    assert history.conversions == []


def test_live_upsert_refuses_without_dedup_key(monkeypatch):
    """No mobile => an upsert degrades to a blind create. Must refuse, not create."""
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()
    with pytest.raises(RuntimeError, match="no bare 10-digit mobile"):
        adapter.upsert_lead(payload={"name": "NoPhone", "mobile": ""}, gorefer_reference="GR-1")


def test_live_upsert_refuses_a_malformed_short_mobile(monkeypatch):
    """<10 digits => no usable dedup key. Refuse rather than pad or blind-create."""
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")
    adapter = LiveZohoAdapter()
    with pytest.raises(RuntimeError, match="no bare 10-digit mobile"):
        adapter.upsert_lead(payload={"name": "Short", "mobile": "12345"}, gorefer_reference="GR-1")


# --- 2. idempotency: no double-create, reference never lost -----------------------

@pytest.mark.django_db(transaction=True)
def test_resubmit_does_not_create_second_lead_and_keeps_reference():
    """THE acceptance test: re-submitting the same form must not twin the lead."""
    call_command("seed_program")
    rec = _RecordingAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=rec):
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
    # Zoho saw both writes, but both carried the SAME bare-10-digit dedup key => update.
    assert {c["Mobile"] for c in rec.calls} == {"9876543210"}


def test_internal_91_prefixed_matches_preexisting_bare_zoho_lead_no_twin():
    """THE silent-twin regression test (DA correction 2026-07-15).

    Zoho already holds `9335179938`. GoRefer normalizes internally to
    `919335179938`. If the write leg sent the internal form, the upsert's dedup key
    would MISS the stored record and INSERT a parallel lead — and Zoho's native
    `Mobile` uniqueness could not catch it, because the two strings differ. The
    correct behaviour is action=update against the existing lead.
    """
    rec = _RecordingAdapter(existing={"9335179938": "zoho-preexisting-1"})

    result = rec.upsert_lead(
        payload={"name": "Ramesh", "mobile": "919335179938"},  # GoRefer internal form
        gorefer_reference="GR-42",
    )

    assert result.action == "update", "internal 91-prefixed form twinned the Zoho lead"
    assert result.zoho_lead_id == "zoho-preexisting-1", "wrote a parallel lead, not the existing one"
    assert rec.calls[0]["Mobile"] == "9335179938", "dedup key must be Zoho's bare format"


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
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=rec):
        _capture(Client(), mobile="9876543210")
        _capture(Client(), mobile="+91-98765 43210")

    # Zoho leg: ONE bare-10-digit dedup key. Internal store: ONE 91-prefixed prospect.
    assert {c["Mobile"] for c in rec.calls} == {"9876543210"}
    assert Prospect.objects.filter(mobile="919876543210").count() == 1
    assert normalize_phone("+91-98765 43210") == normalize_phone("9876543210")


@pytest.mark.django_db(transaction=True)
def test_zoho_failure_does_not_lose_the_lead():
    """Capture-first: a Zoho outage must not fail the request or drop the lead."""
    call_command("seed_program")
    boom = mock.Mock()
    boom.upsert_lead.side_effect = RuntimeError("Zoho HTTP 500")
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=boom):
        resp = _capture(Client())
    assert resp.status_code in (200, 201)  # request still succeeded
    lead = Lead.objects.filter(prospect__mobile="919876543210").first()
    assert lead is not None  # survived
    # ...and is left RETRYABLE, not stranded — the retry/backfill sweep will heal it.
    assert lead.zoho_sync_status == Lead.SYNC_PENDING


# --- 3. flag gating / fail-loud ---------------------------------------------------

def test_flag_off_selects_log_only_adapter_and_sends_nothing():
    """Demo default: ENABLE_ZOHO_WRITE=false => fixture/log-only adapter, zero network."""
    from gorefer.flags import flags as live_flags

    assert live_flags.ENABLE_ZOHO_WRITE is False, "demo default must keep Zoho WRITE off"
    assert isinstance(get_zoho_adapter(), LogOnlyZohoAdapter)


def test_flag_on_selects_live_adapter(monkeypatch):
    """Flipping the flag must select the LIVE adapter — proving the flag is the only
    thing standing between demo and a real write (and that it fails loud w/o creds).

    Patches the RESOLVER rather than the frozen `flags` object: the selector now reads
    the EFFECTIVE flag (admin Settings override -> env default), so that is where the
    decision is made. Intent unchanged — flag on => live adapter => fails loud.
    """
    monkeypatch.setattr(
        "apps.config.integration_flags.resolve_flag", lambda key, **kw: True
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
    assert r1.zoho_lead_id == r2.zoho_lead_id == "demo-zoho-9876543210"


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
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=rec):
        _capture(Client())

    blob = json.dumps([e.metadata for e in Event.objects.all()])
    for pii in ("Rahul", "9876543210", "919876543210", "rahul@example.com", "Prayagraj"):
        assert pii not in blob, f"PII {pii!r} leaked into the event log"
