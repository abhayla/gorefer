"""T-104 — advisor callback via slot-tap on the EXISTING Wati inbound webhook.

Owner-approved Option B (COORDINATION.md 2026-08-12 00:14): Wati has no HTTP flow
node on this tenant, so a chatbot slot button sends its label back as an ordinary
inbound text message. `POST /api/wati/inbound` (apps/integrations/wati/api.py)
recognises an EXACT match against one of the three slot labels and reuses the
EXISTING advisor-callback service (apps.followups.advisor_callback) — the same
create-request + immediate-alert path `POST /api/callback-request/` already uses.

Gated on `ENABLE_ADVISOR_CALLBACK` (frozen dataclass flags — flipped per test via
`dataclasses.replace` + monkeypatch, the established pattern across this suite).
Every existing inbound behaviour (window stamp, cadence enqueue, outbound-ignore,
replay guard) must be unaffected — this feature is additive only.
"""
from __future__ import annotations

import dataclasses
import json

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config.cascade import set_tenant
from apps.followups import advisor_callback
from apps.followups.models import AdvisorCallbackRequest, ScheduledFollowup
from apps.integrations.wati.adapter import SendResult
from apps.tenants.resolve import get_bootstrap_tenant
from gorefer.flags import flags as flags_default

CUSTOMER_MOBILE_RAW = "9876543210"
CUSTOMER_MOBILE_NORM = "919876543210"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def tenant(seeded):
    t = get_bootstrap_tenant()
    set_tenant("followups_enabled", True, tenant_id=t.id)
    return t


@pytest.fixture
def client():
    return Client()


class _FakePort:
    def __init__(self):
        self.calls = []

    def send_template(self, *, to, template, params):
        self.calls.append({"to": to, "template": template, "params": params})
        return SendResult(accepted=True, provider_message_id="fake-1", raw_status="accepted")


def _flag_on(monkeypatch, on: bool):
    monkeypatch.setattr(
        "apps.integrations.wati.api.flags", dataclasses.replace(flags_default, ENABLE_ADVISOR_CALLBACK=on)
    )


def _post_inbound(client, settings, *, text=None, waId=CUSTOMER_MOBILE_RAW, extra=None):
    settings.WATI_WEBHOOK_KEY = "testkey123"
    body = {"waId": waId}
    if text is not None:
        body["text"] = text
    if extra:
        body.update(extra)
    return client.post(
        "/api/wati/inbound?token=testkey123",
        data=json.dumps(body), content_type="application/json",
    )


# --- flag gate -------------------------------------------------------------------

def test_flag_off_by_default():
    assert flags_default.ENABLE_ADVISOR_CALLBACK is False


def test_flag_off_no_callback_created_byte_identical_response(tenant, client, settings, monkeypatch):
    _flag_on(monkeypatch, False)
    resp = _post_inbound(client, settings, text="9-12")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["stamped"] is True
    assert AdvisorCallbackRequest.objects.count() == 0


# --- exact-match trigger -----------------------------------------------------------

@pytest.mark.parametrize("slot", ["9-12", "12-3", "3-6"])
def test_exact_slot_match_creates_request_and_alert(tenant, client, settings, monkeypatch, slot):
    _flag_on(monkeypatch, True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    resp = _post_inbound(client, settings, text=slot, extra={"senderName": "Rahul"})
    assert resp.status_code == 200

    req = AdvisorCallbackRequest.objects.get(mobile=CUSTOMER_MOBILE_NORM, slot=slot)
    assert req.name == "Rahul"
    assert req.alert_sent_at is not None
    assert req.reminder is not None
    assert req.reminder.status == ScheduledFollowup.STATUS_SCHEDULED

    assert len(fake.calls) == 1
    assert fake.calls[0]["to"] == advisor_callback.ADVISOR_ALERT_NUMBER_DEFAULT
    assert fake.calls[0]["to"] != CUSTOMER_MOBILE_NORM


def test_case_insensitive_and_whitespace_trimmed(tenant, client, settings, monkeypatch):
    _flag_on(monkeypatch, True)
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: _FakePort())

    resp = _post_inbound(client, settings, text="  9-12  ")
    assert resp.status_code == 200
    assert AdvisorCallbackRequest.objects.filter(mobile=CUSTOMER_MOBILE_NORM, slot="9-12").exists()


def test_name_absent_degrades_cleanly(tenant, client, settings, monkeypatch):
    _flag_on(monkeypatch, True)
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: _FakePort())

    resp = _post_inbound(client, settings, text="12-3")
    assert resp.status_code == 200
    req = AdvisorCallbackRequest.objects.get(mobile=CUSTOMER_MOBILE_NORM, slot="12-3")
    assert req.name == ""


# --- must NOT trigger on partial/contains matches ---------------------------------

@pytest.mark.parametrize("text", [
    "call me 9-12 please",
    "9-12!",
    "the slot is 9-12 today",
    "912",
    "",
    None,
])
def test_non_exact_text_does_not_trigger(tenant, client, settings, monkeypatch, text):
    _flag_on(monkeypatch, True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    resp = _post_inbound(client, settings, text=text)
    assert resp.status_code == 200
    assert AdvisorCallbackRequest.objects.count() == 0
    assert fake.calls == []


# --- existing webhook behaviour is unaffected -------------------------------------

def test_normal_inbound_unaffected_when_flag_on(tenant, client, settings, monkeypatch):
    """A normal (non-slot) inbound takes EXACTLY the path it takes today: window
    stamp + cadence enqueue, no advisor-callback side effect — flag on or off."""
    _flag_on(monkeypatch, True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    resp = _post_inbound(client, settings, text="Hi, I have a question about the referral")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["stamped"] is True
    assert body["mobile"] == CUSTOMER_MOBILE_NORM
    assert AdvisorCallbackRequest.objects.count() == 0
    assert fake.calls == []


def test_outbound_still_ignored_when_flag_on(tenant, client, settings, monkeypatch):
    _flag_on(monkeypatch, True)
    resp = _post_inbound(client, settings, text="9-12", extra={"owner": True})
    assert resp.status_code == 200
    assert resp.json()["reason"] == "outbound"
    assert AdvisorCallbackRequest.objects.count() == 0


def test_matched_slot_still_stamps_window_and_enqueues(tenant, client, settings, monkeypatch):
    """Additive, not a replacement: a matching inbound STILL stamps the 24h window
    and runs the normal cadence enqueue exactly as an unmatched inbound would."""
    _flag_on(monkeypatch, True)
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: _FakePort())

    resp = _post_inbound(client, settings, text="3-6")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["stamped"] is True
    assert body["opened_fresh"] is True


# --- idempotency (unique constraint; asserted, not re-implemented) ----------------

def test_double_tap_same_day_creates_one_request_one_alert(tenant, client, settings, monkeypatch):
    _flag_on(monkeypatch, True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    for _ in range(2):
        resp = _post_inbound(client, settings, text="9-12", waId="9876500001")
        assert resp.status_code == 200

    assert AdvisorCallbackRequest.objects.filter(mobile="919876500001", slot="9-12").count() == 1
    assert ScheduledFollowup.objects.filter(source_event="advisor_callback").count() == 1
    assert len(fake.calls) == 1


# --- no customer-facing send from this path ---------------------------------------

def test_no_send_ever_reaches_the_customer_number(tenant, client, settings, monkeypatch):
    _flag_on(monkeypatch, True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    _post_inbound(client, settings, text="12-3")
    assert len(fake.calls) >= 1
    for call in fake.calls:
        assert call["to"] != CUSTOMER_MOBILE_NORM
        assert call["to"] == advisor_callback.ADVISOR_ALERT_NUMBER_DEFAULT
