"""M-FUP-1 — 24h-window follow-up engine (Phase 1) tests.

Covers the DoD (doc 14 §7): rule resolution / enqueue, the send gate
(window-open→session / closed→template-or-skip), engaged-exit + opt-out cancel,
idempotency, and CRUD state transitions — plus the adapter session-send, the inbound
window feed, and the schedule registration.

All run in sync/demo mode (ENABLE_WATI_SEND=false → log-only adapter that simulates an
accepted send), so the whole flow is exercised offline. The engine is gated by the
`followups_enabled` cascade key (default OFF); tests enable it per-tenant via
config.cascade.set_tenant, mirroring how an admin would.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.config.cascade import set_tenant
from apps.events.models import PII_KEYS, Event
from apps.followups import services, tasks
from apps.followups.models import FollowupRule, FollowupWindow, ScheduledFollowup
from apps.tenants.resolve import get_bootstrap_tenant

MOBILE = "919876543210"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def tenant(seeded):
    return get_bootstrap_tenant()


@pytest.fixture
def enabled(tenant):
    """Turn the engine on for the tenant (what an admin does before go-live)."""
    set_tenant("followups_enabled", True, tenant_id=tenant.id)
    return tenant


def _rule(tenant, *, step_key="nudge_15m", offset=15, channel=FollowupRule.CHANNEL_SESSION,
          template_name="", enabled=True, only_if_window_open=True, stop_on_reply=True, order=100):
    return FollowupRule.objects.create(
        tenant=tenant, step_key=step_key, offset_minutes=offset, channel=channel,
        template_name=template_name, body_en=f"Hi! ({step_key})", body_hi="",
        enabled=enabled, only_if_window_open=only_if_window_open,
        stop_on_reply=stop_on_reply, order=order,
    )


def _open_window(tenant, *, ago_hours=1.0, mobile=MOBILE, opted_out=False):
    return FollowupWindow.objects.create(
        tenant=tenant, mobile=mobile, opted_out=opted_out,
        last_inbound_at=timezone.now() - timedelta(hours=ago_hours),
    )


def _scheduled(tenant, rule, *, mobile=MOBILE, fire_ago_min=1, window=None, pref_lang="en"):
    window_opened = (window.last_inbound_at if window else timezone.now() - timedelta(hours=1))
    return ScheduledFollowup.objects.create(
        tenant=tenant, rule=rule, mobile=mobile, pref_lang=pref_lang,
        fire_at=timezone.now() - timedelta(minutes=fire_ago_min),
        window_opened_at=window_opened,
        dedupe_key=f"{tenant.id}|{mobile}|{rule.step_key}|{window_opened.isoformat()}",
    )


# --- flag gate ---------------------------------------------------------------

def test_followups_disabled_by_default(tenant):
    assert services.followups_enabled(tenant.id) is False


def test_followups_enabled_after_set_tenant(enabled):
    assert services.followups_enabled(enabled.id) is True


# --- enqueue / rule resolution ------------------------------------------------

def test_enqueue_creates_one_row_per_enabled_rule(enabled):
    _rule(enabled, step_key="s1", offset=15, order=1)
    _rule(enabled, step_key="s2", offset=120, order=2)
    _rule(enabled, step_key="s3_off", offset=200, enabled=False, order=3)
    opened = timezone.now()

    out = tasks.enqueue_followups(enabled.id, MOBILE, opened_at=opened)

    assert out["created"] == 2  # the disabled rule is skipped
    rows = ScheduledFollowup.objects.filter(mobile=MOBILE).order_by("fire_at")
    assert [r.rule.step_key for r in rows] == ["s1", "s2"]
    # fire_at = window-open + offset
    assert rows[0].fire_at == opened + timedelta(minutes=15)
    assert rows[1].fire_at == opened + timedelta(minutes=120)


def test_enqueue_refuses_when_flag_off(tenant):
    _rule(tenant, step_key="s1")
    out = tasks.enqueue_followups(tenant.id, MOBILE)
    assert out == {"created": 0, "reason": "disabled"}
    assert ScheduledFollowup.objects.count() == 0


def test_enqueue_refuses_opted_out_contact(enabled):
    _rule(enabled, step_key="s1")
    FollowupWindow.objects.create(tenant=enabled, mobile=MOBILE, opted_out=True)
    out = tasks.enqueue_followups(enabled.id, MOBILE)
    assert out["reason"] == "opted_out"
    assert ScheduledFollowup.objects.count() == 0


def test_enqueue_is_idempotent_per_window_open(enabled):
    _rule(enabled, step_key="s1")
    opened = timezone.now()
    first = tasks.enqueue_followups(enabled.id, MOBILE, opened_at=opened)
    second = tasks.enqueue_followups(enabled.id, MOBILE, opened_at=opened)  # same open
    assert first["created"] == 1
    assert second["created"] == 0  # deduped on (tenant, mobile, step, window-open)
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1


# --- send gate: window open → session ----------------------------------------

def test_window_open_sends_session(enabled):
    rule = _rule(enabled, channel=FollowupRule.CHANNEL_SESSION)
    win = _open_window(enabled, ago_hours=1)
    _scheduled(enabled, rule, window=win)

    counts = tasks.fire_due_followups()

    assert counts["sent"] == 1
    sf = ScheduledFollowup.objects.get()
    assert sf.status == ScheduledFollowup.STATUS_SENT
    assert sf.sent_at is not None


def test_session_send_emits_pii_free_funnel_event(enabled):
    rule = _rule(enabled)
    win = _open_window(enabled, ago_hours=1)
    _scheduled(enabled, rule, window=win)

    tasks.fire_due_followups()

    ev = Event.objects.filter(event_type="notification").get()
    assert ev.metadata["kind"] == "followup"
    assert ev.metadata["decision"] == services.DEC_SEND_SESSION
    blob = json.dumps(ev.metadata)
    assert MOBILE not in blob
    assert not (PII_KEYS & set(ev.metadata.keys()))


# --- send gate: window closed → template or skip -----------------------------

def test_window_closed_session_only_skips(enabled):
    rule = _rule(enabled, channel=FollowupRule.CHANNEL_SESSION, only_if_window_open=True)
    win = _open_window(enabled, ago_hours=25)  # window closed
    _scheduled(enabled, rule, window=win)

    tasks.fire_due_followups()

    sf = ScheduledFollowup.objects.get()
    assert sf.status == ScheduledFollowup.STATUS_SKIPPED
    assert "window closed" in sf.reason


def test_window_closed_falls_back_to_template(enabled):
    rule = _rule(enabled, channel=FollowupRule.CHANNEL_SESSION,
                 only_if_window_open=False, template_name="gr_followup_tmpl")
    win = _open_window(enabled, ago_hours=25)
    _scheduled(enabled, rule, window=win)

    counts = tasks.fire_due_followups()

    assert counts["sent"] == 1
    assert ScheduledFollowup.objects.get().status == ScheduledFollowup.STATUS_SENT


def test_template_channel_sends_template_even_in_window(enabled):
    rule = _rule(enabled, channel=FollowupRule.CHANNEL_TEMPLATE, template_name="gr_tmpl")
    win = _open_window(enabled, ago_hours=1)
    _scheduled(enabled, rule, window=win)

    tasks.fire_due_followups()

    assert ScheduledFollowup.objects.get().status == ScheduledFollowup.STATUS_SENT


# --- send gate: engaged-exit + opt-out cancel --------------------------------

def test_reply_after_open_cancels(enabled):
    rule = _rule(enabled, stop_on_reply=True)
    win = _open_window(enabled, ago_hours=2)
    sf = _scheduled(enabled, rule, window=win)
    # A LATER inbound than the window that scheduled this step = a reply.
    win.last_inbound_at = sf.window_opened_at + timedelta(minutes=30)
    win.save()

    tasks.fire_due_followups()

    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_CANCELLED
    assert "replied" in sf.reason


def test_opt_out_cancels_at_fire_time(enabled):
    rule = _rule(enabled)
    win = _open_window(enabled, ago_hours=1, opted_out=True)
    _scheduled(enabled, rule, window=win)

    tasks.fire_due_followups()

    assert ScheduledFollowup.objects.get().status == ScheduledFollowup.STATUS_CANCELLED


def test_flag_off_after_schedule_cancels(enabled):
    rule = _rule(enabled)
    win = _open_window(enabled, ago_hours=1)
    _scheduled(enabled, rule, window=win)
    # Admin flips it back off AFTER rows were scheduled.
    set_tenant("followups_enabled", False, tenant_id=enabled.id)

    tasks.fire_due_followups()

    sf = ScheduledFollowup.objects.get()
    assert sf.status == ScheduledFollowup.STATUS_CANCELLED
    assert "disabled" in sf.reason


def test_converted_lead_cancels(enabled):
    from apps.referrals.models import Lead, Prospect, Referral, ReferralProgram

    program = ReferralProgram.objects.first()
    prospect = Prospect.objects.create(tenant=enabled, mobile=MOBILE, name="P")
    referral = Referral.objects.create(tenant=enabled, program=program, source="partner_direct")
    Lead.objects.create(tenant=enabled, referral=referral, prospect=prospect,
                        status="account_opened", consent=True)

    rule = _rule(enabled)
    win = _open_window(enabled, ago_hours=1)
    _scheduled(enabled, rule, window=win)

    tasks.fire_due_followups()

    assert ScheduledFollowup.objects.get().status == ScheduledFollowup.STATUS_CANCELLED


def test_disabled_rule_cancels_at_fire_time(enabled):
    rule = _rule(enabled, enabled=False)
    win = _open_window(enabled, ago_hours=1)
    _scheduled(enabled, rule, window=win)

    tasks.fire_due_followups()

    assert ScheduledFollowup.objects.get().status == ScheduledFollowup.STATUS_CANCELLED


def test_future_rows_not_fired(enabled):
    rule = _rule(enabled)
    win = _open_window(enabled, ago_hours=1)
    sf = _scheduled(enabled, rule, window=win)
    sf.fire_at = timezone.now() + timedelta(hours=1)  # not due yet
    sf.save()

    counts = tasks.fire_due_followups()

    assert counts == {"sent": 0, "cancelled": 0, "skipped": 0, "failed": 0, "held": 0}
    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_SCHEDULED


# --- window feed (inbound webhook) -------------------------------------------

def test_stamp_inbound_fresh_open_then_refresh(tenant):
    now = timezone.now()
    win1, fresh1 = services.stamp_inbound(tenant, MOBILE, now)
    assert fresh1 is True
    win2, fresh2 = services.stamp_inbound(tenant, MOBILE, now + timedelta(minutes=5))
    assert fresh2 is False  # still inside the window → refresh, not a new open
    win3, fresh3 = services.stamp_inbound(tenant, MOBILE, now + timedelta(hours=25))
    assert fresh3 is True  # window had closed → new open
    assert FollowupWindow.objects.filter(mobile=MOBILE).count() == 1


def test_record_inbound_enqueues_on_fresh_open(enabled):
    from apps.integrations.wati.webhook import record_inbound

    _rule(enabled, step_key="s1")
    # A non-canonical 10-digit mobile normalizes to the 91-key.
    out = record_inbound(enabled, "9876543210")
    assert out["opened_fresh"] is True
    assert out["mobile"] == MOBILE
    assert out["enqueued"] == 1
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1


def test_record_inbound_refresh_does_not_reenqueue(enabled):
    from apps.integrations.wati.webhook import record_inbound

    _rule(enabled, step_key="s1")
    record_inbound(enabled, MOBILE)
    out2 = record_inbound(enabled, MOBILE)  # inside window
    assert out2["opened_fresh"] is False
    assert out2["enqueued"] == 0
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1


# --- adapter: session send ---------------------------------------------------

def test_logonly_adapter_session_send_accepted():
    from apps.integrations.wati.adapter import LogOnlyWatiAdapter

    res = LogOnlyWatiAdapter().send_session_text(to=MOBILE, message="hi")
    assert res.accepted is True


def test_live_adapter_session_send_respects_allowlist(monkeypatch):
    from apps.integrations.wati import status as st
    from apps.integrations.wati.adapter import LiveWatiAdapter

    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/12345")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "false")
    monkeypatch.setenv("WATI_TEST_RECIPIENTS", "")  # empty allowlist blocks everything

    sent = {}

    def transport(method, url, headers, body):
        sent["called"] = True
        return (200, '{"result": true}')

    adapter = LiveWatiAdapter(transport=transport)
    res = adapter.send_session_text(to=MOBILE, message="hi")
    assert res.accepted is False
    assert res.raw_status == st.STATUS_BLOCKED
    assert "called" not in sent  # blocked BEFORE any network call


def test_live_adapter_session_send_accepted_when_allowlisted(monkeypatch):
    from apps.integrations.wati.adapter import LiveWatiAdapter

    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/12345")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "true")

    def transport(method, url, headers, body):
        assert "sendSessionMessage" in url
        return (200, '{"result": true}')

    res = LiveWatiAdapter(transport=transport).send_session_text(to=MOBILE, message="hi")
    assert res.accepted is True


# --- CRUD API (staff-only, tenant-scoped) ------------------------------------

@pytest.fixture
def staff_client(seeded):
    user = get_user_model().objects.create_user(
        username="admin", password="x", is_staff=True
    )
    c = Client()
    c.force_login(user)
    return c


def test_api_requires_staff(seeded):
    # Anonymous → 401.
    assert Client().get("/api/followups/rules").status_code == 401
    # Authenticated but not staff → 401.
    user = get_user_model().objects.create_user(username="joe", password="x", is_staff=False)
    c = Client()
    c.force_login(user)
    assert c.get("/api/followups/rules").status_code == 401


def test_api_rule_create_list_patch(staff_client):
    r = staff_client.post(
        "/api/followups/rules",
        data={"step_key": "nudge_15m", "offset_minutes": 15, "body_en": "Hi"},
        content_type="application/json",
    )
    assert r.status_code == 201
    rule_id = r.json()["id"]

    lst = staff_client.get("/api/followups/rules").json()
    assert [x["step_key"] for x in lst] == ["nudge_15m"]

    p = staff_client.patch(
        f"/api/followups/rules/{rule_id}",
        data={"offset_minutes": 20, "enabled": False},
        content_type="application/json",
    )
    assert p.status_code == 200
    body = p.json()
    assert body["offset_minutes"] == 20
    assert body["enabled"] is False


def test_api_rejects_duplicate_step_key(staff_client):
    payload = {"step_key": "dup", "offset_minutes": 15}
    assert staff_client.post("/api/followups/rules", data=payload,
                             content_type="application/json").status_code == 201
    assert staff_client.post("/api/followups/rules", data=payload,
                             content_type="application/json").status_code == 409


def test_api_cancel_scheduled(staff_client, enabled):
    rule = _rule(enabled, step_key="s1")
    win = _open_window(enabled, ago_hours=1)
    sf = _scheduled(enabled, rule, window=win)

    r = staff_client.post(f"/api/followups/scheduled/{sf.id}/cancel")
    assert r.status_code == 200
    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_CANCELLED

    # Cancelling a non-scheduled row → 409.
    assert staff_client.post(f"/api/followups/scheduled/{sf.id}/cancel").status_code == 409


def test_api_reschedule_scheduled(staff_client, enabled):
    rule = _rule(enabled, step_key="s1")
    win = _open_window(enabled, ago_hours=1)
    sf = _scheduled(enabled, rule, window=win)
    new_fire = (timezone.now() + timedelta(hours=3)).isoformat()

    r = staff_client.post(
        f"/api/followups/scheduled/{sf.id}/reschedule",
        data={"fire_at": new_fire}, content_type="application/json",
    )
    assert r.status_code == 200
    sf.refresh_from_db()
    assert abs((sf.fire_at - (timezone.now() + timedelta(hours=3))).total_seconds()) < 5


def test_api_delete_rule_cancels_pending(staff_client, enabled):
    rule = _rule(enabled, step_key="s1")
    win = _open_window(enabled, ago_hours=1)
    sf = _scheduled(enabled, rule, window=win)

    r = staff_client.delete(f"/api/followups/rules/{rule.id}")
    assert r.status_code == 200
    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_CANCELLED  # pending row cancelled (doc 14 §3)


# --- quiet hours (23:00–06:00 IST, no sends) ---------------------------------

# A UTC instant that reads 01:00 IST (inside quiet) and one that reads 12:00 IST (active).
QUIET_UTC = datetime(2026, 7, 24, 19, 30, tzinfo=dt_timezone.utc)   # 25th 01:00 IST
ACTIVE_UTC = datetime(2026, 7, 24, 6, 30, tzinfo=dt_timezone.utc)   # 12:00 IST


def test_in_quiet_hours_ist():
    assert services.in_quiet_hours(QUIET_UTC) is True
    assert services.in_quiet_hours(ACTIVE_UTC) is False


def test_next_active_time_is_6am_ist():
    # 01:00 IST → the next 06:00 IST is the same IST day = 00:30 UTC.
    assert services.next_active_time(QUIET_UTC) == datetime(2026, 7, 25, 0, 30, tzinfo=dt_timezone.utc)


def test_gate_holds_a_send_during_quiet_hours(enabled):
    rule = _rule(enabled)
    win = FollowupWindow.objects.create(
        tenant=enabled, mobile=MOBILE, last_inbound_at=QUIET_UTC - timedelta(hours=1)
    )
    sf = _scheduled(enabled, rule, window=win)

    decision, reason = services.evaluate_gate(sf, now=QUIET_UTC)

    assert decision == services.DEC_HOLD
    assert "quiet hours" in reason


def test_gate_sends_during_active_hours(enabled):
    rule = _rule(enabled)
    win = FollowupWindow.objects.create(
        tenant=enabled, mobile=MOBILE, last_inbound_at=ACTIVE_UTC - timedelta(hours=1)
    )
    sf = _scheduled(enabled, rule, window=win)

    decision, _ = services.evaluate_gate(sf, now=ACTIVE_UTC)

    assert decision == services.DEC_SEND_SESSION


def test_fire_defers_due_row_during_quiet_hours(enabled, monkeypatch):
    # Force "quiet hours" regardless of the real clock so the sweep takes the HOLD path.
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: True)
    rule = _rule(enabled)
    win = _open_window(enabled, ago_hours=1)
    sf = _scheduled(enabled, rule, window=win)

    counts = tasks.fire_due_followups()

    assert counts["held"] == 1
    assert counts["sent"] == 0
    sf.refresh_from_db()
    assert sf.status == ScheduledFollowup.STATUS_SCHEDULED  # deferred, not sent/cancelled
    assert sf.fire_at > timezone.now()                      # pushed to the next 06:00 IST
    assert "quiet hours" in sf.reason


# --- cadence config command --------------------------------------------------

def test_seed_cadence_creates_every_3h_through_24h(tenant):
    call_command("seed_followup_cadence")  # defaults: 3h interval, 24h horizon, tenant pifs

    rules = FollowupRule.objects.filter(tenant=tenant).order_by("offset_minutes")
    assert [r.step_key for r in rules] == [
        "nudge_3h", "nudge_6h", "nudge_9h", "nudge_12h", "nudge_15h", "nudge_18h", "nudge_21h",
    ]
    assert [r.offset_minutes for r in rules] == [180, 360, 540, 720, 900, 1080, 1260]
    assert all(r.channel == FollowupRule.CHANNEL_SESSION and r.enabled for r in rules)


def test_seed_cadence_is_idempotent(tenant):
    call_command("seed_followup_cadence")
    call_command("seed_followup_cadence")  # re-run must not duplicate
    assert FollowupRule.objects.filter(tenant=tenant).count() == 7


# --- inbound poll (window-feed) ----------------------------------------------

class _FakeAdapter:
    def __init__(self, ts_by_mobile):
        self._ts = ts_by_mobile

    def get_latest_inbound_at(self, mobile):
        return self._ts.get(mobile)


def test_poll_opens_window_and_enqueues_from_watchlist(enabled, monkeypatch):
    _rule(enabled, step_key="s1")
    set_tenant("followup_poll_watch_mobiles", MOBILE, tenant_id=enabled.id)
    monkeypatch.setattr(tasks, "get_wati_adapter", lambda: _FakeAdapter({MOBILE: timezone.now()}))

    counts = tasks.poll_inbound_windows()

    assert counts["opened"] == 1 and counts["enqueued"] == 1
    assert FollowupWindow.objects.filter(mobile=MOBILE).exists()
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1


def test_poll_skips_already_seen_inbound(enabled, monkeypatch):
    _rule(enabled, step_key="s1")
    set_tenant("followup_poll_watch_mobiles", MOBILE, tenant_id=enabled.id)
    t0 = timezone.now()
    monkeypatch.setattr(tasks, "get_wati_adapter", lambda: _FakeAdapter({MOBILE: t0}))

    first = tasks.poll_inbound_windows()
    second = tasks.poll_inbound_windows()  # same inbound timestamp → nothing new

    assert first["opened"] == 1 and second["opened"] == 0
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1


def test_poll_noop_when_no_inbound(enabled, monkeypatch):
    _rule(enabled, step_key="s1")
    set_tenant("followup_poll_watch_mobiles", MOBILE, tenant_id=enabled.id)
    monkeypatch.setattr(tasks, "get_wati_adapter", lambda: _FakeAdapter({}))

    counts = tasks.poll_inbound_windows()

    assert counts["opened"] == 0
    assert not ScheduledFollowup.objects.filter(mobile=MOBILE).exists()


def test_poll_refuses_when_flag_off(tenant, monkeypatch):
    _rule(tenant, step_key="s1")  # flag NOT enabled (tenant fixture, not `enabled`)
    set_tenant("followup_poll_watch_mobiles", MOBILE, tenant_id=tenant.id)
    monkeypatch.setattr(tasks, "get_wati_adapter", lambda: _FakeAdapter({MOBILE: timezone.now()}))

    counts = tasks.poll_inbound_windows()

    assert counts["checked"] == 0  # disabled tenant skipped entirely
    assert not FollowupWindow.objects.filter(mobile=MOBILE).exists()


# --- schedule registration ---------------------------------------------------

def test_followup_schedules_registered():
    from apps.events.management.commands.setup_schedules import SCHEDULES

    assert SCHEDULES["followup_sweep"] == ("apps.followups.tasks.fire_due_followups", 5)
    assert SCHEDULES["followup_inbound_poll"] == ("apps.followups.tasks.poll_inbound_windows", 5)
