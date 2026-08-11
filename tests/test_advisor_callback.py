"""T-097 — advisor callback: alert-now + timed-reminder tests.

The endpoint is flag-gated (`ENABLE_ADVISOR_CALLBACK`, default False — Constitution
§4). Endpoint tests run against `tests.urls_advisor_callback` (see that module for
why); the flag itself is confirmed OFF by default and unmounted in prod urlconf
separately below.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.config.cascade import set_tenant
from apps.followups import advisor_callback, services, tasks
from apps.followups.models import AdvisorCallbackRequest, ScheduledFollowup
from apps.integrations.wati.adapter import SendResult
from apps.tenants.resolve import get_bootstrap_tenant
from gorefer.flags import flags

CUSTOMER_MOBILE = "9876543210"
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
    """Records every send_template call so tests can assert recipient/template/params
    without touching the real (log-only-by-default) adapter."""

    def __init__(self):
        self.calls = []

    def send_template(self, *, to, template, params):
        self.calls.append({"to": to, "template": template, "params": params})
        return SendResult(accepted=True, provider_message_id="fake-1", raw_status="accepted")


# --- flag gate -----------------------------------------------------------------

def test_flag_off_by_default():
    assert flags.ENABLE_ADVISOR_CALLBACK is False


def test_endpoint_not_mounted_in_prod_urlconf(db, client):
    # The real /api/ NinjaAPI never registered the router (flag off at import time).
    resp = client.post(
        "/api/callback-request/",
        data=json.dumps({"mobile": "9876543210", "slot": "9-12"}),
        content_type="application/json",
    )
    assert resp.status_code == 404


# --- endpoint behaviour (flag-on test urlconf) ----------------------------------

@pytest.mark.urls("tests.urls_advisor_callback")
class TestCallbackEndpoint:
    def test_creates_request_and_sends_alert(self, tenant, client, monkeypatch):
        fake = _FakePort()
        monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

        resp = client.post(
            "/api/callback-request/",
            data=json.dumps({"mobile": CUSTOMER_MOBILE, "name": "Rahul", "slot": "9-12"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "created"
        assert body["slot"] == "9-12"
        assert body["reminder_at"]

        req = AdvisorCallbackRequest.objects.get(mobile=CUSTOMER_MOBILE_NORM, slot="9-12")
        assert req.alert_sent_at is not None
        assert req.reminder is not None
        assert req.reminder.status == ScheduledFollowup.STATUS_SCHEDULED

        # exactly one alert send, to the CONFIGURED staff number — never the customer's
        assert len(fake.calls) == 1
        assert fake.calls[0]["to"] == advisor_callback.ADVISOR_ALERT_NUMBER_DEFAULT
        assert fake.calls[0]["to"] != CUSTOMER_MOBILE_NORM
        assert fake.calls[0]["template"] == advisor_callback.ADVISOR_ALERT_TEMPLATE_DEFAULT
        values = [p["value"] for p in fake.calls[0]["params"]["template_params"]]
        assert values == ["Rahul", CUSTOMER_MOBILE_NORM, AdvisorCallbackRequest.SLOT_LABELS["9-12"]]

    def test_mobile_is_canonically_normalised(self, tenant, client, monkeypatch):
        monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: _FakePort())
        resp = client.post(
            "/api/callback-request/",
            data=json.dumps({"mobile": "+91 98765-43210", "slot": "12-3"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert AdvisorCallbackRequest.objects.filter(mobile=CUSTOMER_MOBILE_NORM, slot="12-3").exists()

    def test_unknown_slot_rejected(self, tenant, client):
        resp = client.post(
            "/api/callback-request/",
            data=json.dumps({"mobile": CUSTOMER_MOBILE, "slot": "midnight"}),
            content_type="application/json",
        )
        assert resp.status_code == 422
        assert AdvisorCallbackRequest.objects.count() == 0

    def test_missing_mobile_rejected(self, tenant, client):
        resp = client.post(
            "/api/callback-request/",
            data=json.dumps({"mobile": "", "slot": "9-12"}),
            content_type="application/json",
        )
        assert resp.status_code == 422

    def test_idempotent_same_mobile_slot_date(self, tenant, client, monkeypatch):
        fake = _FakePort()
        monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)
        payload = json.dumps({"mobile": CUSTOMER_MOBILE, "name": "Rahul", "slot": "3-6"})

        for _ in range(3):
            resp = client.post("/api/callback-request/", data=payload, content_type="application/json")
            assert resp.status_code == 200

        assert AdvisorCallbackRequest.objects.filter(mobile=CUSTOMER_MOBILE_NORM, slot="3-6").count() == 1
        assert ScheduledFollowup.objects.filter(source_event="advisor_callback").count() == 1
        assert len(fake.calls) == 1  # exactly one alert, not three

    def test_no_send_ever_reaches_the_customer_number(self, tenant, client, monkeypatch):
        fake = _FakePort()
        monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)
        client.post(
            "/api/callback-request/",
            data=json.dumps({"mobile": CUSTOMER_MOBILE, "slot": "9-12"}),
            content_type="application/json",
        )
        for call in fake.calls:
            assert call["to"] != CUSTOMER_MOBILE_NORM
            assert call["to"] == advisor_callback.ADVISOR_ALERT_NUMBER_DEFAULT

    def test_concurrent_duplicate_request_both_succeed(self, tenant, client, monkeypatch):
        fake = _FakePort()
        monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)
        payload = json.dumps({"mobile": CUSTOMER_MOBILE, "name": "Rahul", "slot": "3-6"})
        results = []
        errors = []

        def make_request():
            try:
                resp = client.post("/api/callback-request/", data=payload, content_type="application/json")
                results.append(resp)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(make_request) for _ in range(2)]
            for future in futures:
                future.result(timeout=5)

        assert errors == [], f"Concurrent requests raised: {errors}"
        assert len(results) == 2

        for resp in results:
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.content}"
            body = resp.json()
            assert body["status"] in ("created", "duplicate"), f"Unexpected status: {body}"
            assert body["slot"] == "3-6"
            assert body["reminder_at"]

        assert AdvisorCallbackRequest.objects.filter(mobile=CUSTOMER_MOBILE_NORM, slot="3-6").count() == 1
        assert ScheduledFollowup.objects.filter(source_event="advisor_callback").count() == 1
        assert len(fake.calls) == 1  # exactly one alert send


# --- reminder scheduling ---------------------------------------------------------

def test_compute_fire_at_future_slot_today(tenant):
    from datetime import timezone as dt_timezone

    # 05:00 IST -> "9-12" slot start is later today (09:00 IST).
    now = timezone.datetime(2026, 8, 11, 23, 30, tzinfo=dt_timezone.utc)  # 05:00 IST on the 12th
    fire_at = advisor_callback.compute_fire_at("9-12", now)
    ist = fire_at.astimezone(dt_timezone.utc) + services.IST_OFFSET
    assert ist.hour == 9
    assert ist.date() == (now.astimezone(dt_timezone.utc) + services.IST_OFFSET).date()


def test_compute_fire_at_past_slot_rolls_to_tomorrow(tenant):
    from datetime import timezone as dt_timezone

    now = timezone.datetime(2026, 8, 11, 12, 0, tzinfo=dt_timezone.utc)  # 17:30 IST — well past "9-12"
    fire_at = advisor_callback.compute_fire_at("9-12", now)
    ist_now = now.astimezone(dt_timezone.utc) + services.IST_OFFSET
    ist_fire = fire_at.astimezone(dt_timezone.utc) + services.IST_OFFSET
    assert ist_fire.date() == ist_now.date() + timezone.timedelta(days=1)
    assert ist_fire.hour == 9


# --- suppression: marking done cancels the pending reminder ----------------------

def test_done_before_fire_suppresses_reminder(tenant, monkeypatch):
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    req, created = advisor_callback.request_and_schedule(
        tenant, mobile=CUSTOMER_MOBILE_NORM, name="Rahul", slot="9-12",
    )
    assert created
    sf = req.reminder
    sf.fire_at = timezone.now() - timezone.timedelta(minutes=1)
    sf.save(update_fields=["fire_at"])

    req.done = True
    req.save(update_fields=["done"])

    counts = tasks.fire_due_followups()

    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_CANCELLED
    assert sf.reason == "advisor callback marked done"
    assert counts["cancelled"] >= 1
    assert fake.calls == []  # no reminder send happened


def test_not_done_sends_reminder_via_sweep(tenant, monkeypatch):
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    req, created = advisor_callback.request_and_schedule(
        tenant, mobile=CUSTOMER_MOBILE_NORM, name="Rahul", slot="12-3",
    )
    assert created
    sf = req.reminder
    sf.fire_at = timezone.now() - timezone.timedelta(minutes=1)
    sf.save(update_fields=["fire_at"])

    counts = tasks.fire_due_followups()

    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_SENT
    assert counts["sent"] >= 1
    assert len(fake.calls) == 1
    assert fake.calls[0]["to"] == advisor_callback.ADVISOR_ALERT_NUMBER_DEFAULT
    assert fake.calls[0]["template"] == advisor_callback.ADVISOR_REMINDER_TEMPLATE_DEFAULT
    values = [p["value"] for p in fake.calls[0]["params"]["template_params"]]
    assert values == ["Rahul", CUSTOMER_MOBILE_NORM, AdvisorCallbackRequest.SLOT_LABELS["12-3"]]


def test_reminder_reuses_quiet_hours_guard(tenant, monkeypatch):
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    req, created = advisor_callback.request_and_schedule(
        tenant, mobile=CUSTOMER_MOBILE_NORM, name="Rahul", slot="3-6",
    )
    sf = req.reminder
    sf.fire_at = timezone.now() - timezone.timedelta(minutes=1)
    sf.save(update_fields=["fire_at"])

    counts = tasks.fire_due_followups()

    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_SCHEDULED  # held, not cancelled/sent
    assert counts["held"] >= 1
    assert fake.calls == []


def test_reminder_reuses_min_gap_guard(tenant, monkeypatch):
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)
    monkeypatch.setattr(services, "within_min_gap", lambda *a, **k: True)
    fake = _FakePort()
    monkeypatch.setattr(advisor_callback, "get_messaging_port", lambda: fake)

    req, created = advisor_callback.request_and_schedule(
        tenant, mobile=CUSTOMER_MOBILE_NORM, name="Rahul", slot="9-12",
    )
    sf = req.reminder
    sf.fire_at = timezone.now() - timezone.timedelta(minutes=1)
    sf.save(update_fields=["fire_at"])

    counts = tasks.fire_due_followups()

    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_SCHEDULED
    assert counts["held"] >= 1
    assert fake.calls == []


# --- domain-level idempotency (bypassing the API layer) --------------------------

def test_request_and_schedule_idempotent(tenant):
    r1, c1 = advisor_callback.request_and_schedule(
        tenant, mobile=CUSTOMER_MOBILE_NORM, name="Rahul", slot="9-12",
    )
    r2, c2 = advisor_callback.request_and_schedule(
        tenant, mobile=CUSTOMER_MOBILE_NORM, name="Rahul", slot="9-12",
    )
    assert c1 is True
    assert c2 is False
    assert r1.pk == r2.pk
    assert AdvisorCallbackRequest.objects.count() == 1
    assert ScheduledFollowup.objects.filter(source_event="advisor_callback").count() == 1


def test_no_partner_named_symbol_leaks_into_this_module():
    # Owner ruling 2026-08-11 — partner isolation: no Zerodha-named identifier anywhere
    # in this feature's code. A crude source scan is enough for a regression trip-wire.
    import inspect

    src = inspect.getsource(advisor_callback) + inspect.getsource(AdvisorCallbackRequest)
    assert "zerodha" not in src.lower()
