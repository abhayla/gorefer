"""T-127 (W4) — combined daily funnel digest + threshold alerts.

Locks down:
  - the digest reads the T-126 CrmReadPort.fetch_send_queue_counts + GoRefer's own
    event counts for the PREVIOUS IST day and fills the template's 15 positional
    slots in the verified order;
  - every wire reads the T-124 MESSAGING_DIGEST_* cascade keys, no literals;
  - the digest is inert (no send) when no recipients are configured, and when the
    scheduled hour doesn't match `messaging_digest_send_hour_ist`;
  - a real send is recorded accepted -> terminal status (never HTTP-200-as-success);
  - the instant-alert path fires at most once per rule per IST day (dedupe via an
    Event row), only when `messaging_digest_alerts_enabled`;
  - a send exception is caught and logged, never raised out of the schedule loop;
  - digest sends emit a PII-free Event so the digest itself is observable.
"""
from __future__ import annotations

from datetime import date, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.campaigns import digest
from apps.config.cascade import set_tenant
from apps.config.preferences import (
    MESSAGING_DIGEST_ALERT_RECOVERY_HITS,
    MESSAGING_DIGEST_ALERTS_ENABLED,
    MESSAGING_DIGEST_RECIPIENTS,
    MESSAGING_DIGEST_SEND_HOUR_IST,
)
from apps.events import vocab
from apps.events.models import Event
from apps.integrations.wati import status as wati_status
from apps.integrations.wati.adapter import DeliveryResult, SendResult
from apps.integrations.zoho.read import SendQueueCounts
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

IST_OFFSET = timedelta(hours=5, minutes=30)


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _ist_noon_utc(day: date):
    """A UTC instant that falls inside `day` in IST (safely mid-day)."""
    return timezone.datetime(day.year, day.month, day.day, 6, 30, tzinfo=dt_timezone.utc)


def _identity(tenant, client_id: str) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _set_config(tenant, **kv) -> None:
    for key, value in kv.items():
        set_tenant(key, value, tenant_id=tenant.id)


class _FakeCrmRead:
    def __init__(self, counts: SendQueueCounts):
        self._counts = counts
        self.calls = []

    def fetch_send_queue_counts(self, *, date_ist):
        self.calls.append(date_ist)
        return self._counts


class _FakeMessaging:
    kind = "log_only"

    def __init__(self, *, accepted=True, terminal_status=wati_status.STATUS_DELIVERED):
        self.template_sends = []
        self.session_sends = []
        self._accepted = accepted
        self._terminal_status = terminal_status

    def send_template(self, *, to, template, params):
        self.template_sends.append({"to": to, "template": template, "params": params})
        return SendResult(
            accepted=self._accepted, provider_message_id="fake-mid",
            raw_status=wati_status.STATUS_ACCEPTED if self._accepted else wati_status.STATUS_FAILED,
        )

    def send_session_text(self, *, to, message):
        self.session_sends.append({"to": to, "message": message})
        return SendResult(accepted=self._accepted, provider_message_id="fake-mid",
                           raw_status=wati_status.STATUS_ACCEPTED)

    def get_message_status(self, *, provider_message_id, recipient_mobile=None, template=None):
        return DeliveryResult(status=self._terminal_status, meta_error_code=None, classification=None)


# --------------------------------------------------------------------------- counts


def test_goref_counts_scoped_to_the_ist_day(tenant):
    identity = _identity(tenant, "RJ4521")
    program = ReferralProgram.objects.get(tenant=tenant)
    from apps.referrals.models import Referral

    referral = Referral.objects.create(
        tenant=tenant, referral_identity=identity, program=program, source="referral_link",
    )
    target_day = date(2026, 8, 10)
    in_day = _ist_noon_utc(target_day)
    outside_day = _ist_noon_utc(target_day - timedelta(days=1))

    # Event.timestamp is auto_now_add (stamped at INSERT, ignoring any explicit
    # kwarg) — backdate via a bulk .update() afterwards, which bypasses auto_now_add
    # entirely (only .save() on create applies it), same idiom as `_mint_aged` in
    # tests/test_t051_records_link.py backdates a signed token's clock.
    def _backdated(event_type, *, is_confirmed_human=False, ts=in_day):
        e = Event.objects.create(
            tenant=tenant, event_type=event_type, referral=referral, is_bot=False,
            is_confirmed_human=is_confirmed_human,
        )
        Event.objects.filter(pk=e.pk).update(timestamp=ts)
        return e

    _backdated(vocab.CLICK, is_confirmed_human=True, ts=in_day)
    _backdated(vocab.CLICK, is_confirmed_human=True, ts=outside_day)
    _backdated(vocab.LEAD_CAPTURED, ts=in_day)
    _backdated(vocab.SHARE_RECOVERY_VIEWED, ts=in_day)

    counts = digest.goref_counts(tenant, target_day)
    assert counts["human_clicks"] == 1
    assert counts["leads"] == 1
    assert counts["recovery_saves"] == 1
    assert counts["top_referrer"] == "RJ4521"


def test_zoho_queue_summary_maps_sent_delivered_rate(tenant, monkeypatch):
    counts = SendQueueCounts(
        date_ist="2026-08-10",
        referral={"SENT": 7, "FAILED": 1, "SUPPRESSED_CAPPED": 1, "SUPPRESSED_INVALID": 1},
        other={"SENT": 3, "FAILED": 1},
    )
    fake_crm = _FakeCrmRead(counts)
    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)

    summary = digest.zoho_queue_summary(tenant, date(2026, 8, 10))
    assert summary["referral_total"] == 10
    assert summary["delivered"] == 7
    assert summary["not_delivered"] == 3
    assert summary["rate_pct"] == 70.0
    assert summary["capped"] == 1
    assert summary["invalid"] == 1
    assert summary["other_total"] == 4
    assert fake_crm.calls == [date(2026, 8, 10)]


def test_build_slots_fifteen_values_in_order():
    zoho = {
        "referral_total": 10, "delivered": 7, "not_delivered": 3, "rate_pct": 70.0,
        "capped": 1, "invalid": 1, "other_total": 4, "other_breakdown": {"SENT": 3, "FAILED": 1},
    }
    goref = {
        "human_clicks": 5, "landing_views": 4, "leads": 2, "accounts": 1,
        "recovery_saves": 2, "top_referrer": "RJ4521", "top_referrer_count": 3,
    }
    slots = digest.build_slots(date(2026, 8, 10), zoho, goref)
    assert len(slots) == 15
    assert slots[0] == "2026-08-10"
    assert slots[2] == "10"
    assert slots[3] == "7"
    assert slots[4] == "3"
    assert slots[5] == "70%"
    assert slots[10] == "5"
    assert slots[11] == "4"
    assert slots[12] == "2"
    assert slots[13] == "1"
    assert "RJ4521" in slots[14]


# --------------------------------------------------------------------------- digest send


def test_run_digest_for_tenant_no_recipients_is_a_noop(tenant, monkeypatch):
    _set_config(tenant, **{MESSAGING_DIGEST_RECIPIENTS: ""})
    result = digest.run_digest_for_tenant(tenant)
    assert result["skipped"] is True


def test_run_digest_for_tenant_sends_to_every_recipient(tenant, monkeypatch):
    _set_config(tenant, **{MESSAGING_DIGEST_RECIPIENTS: "919876543210,919876543211"})
    fake_crm = _FakeCrmRead(SendQueueCounts(date_ist="x", referral={"SENT": 1}, other={}))
    fake_messaging = _FakeMessaging()
    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)
    monkeypatch.setattr(digest, "get_messaging_port", lambda: fake_messaging)

    result = digest.run_digest_for_tenant(tenant, day=date(2026, 8, 10))

    assert result["skipped"] is False
    assert len(fake_messaging.template_sends) == 2
    assert all(len(s["params"]["template_params"]) == 15 for s in fake_messaging.template_sends)
    assert all(r["outcome"] == "sent" for r in result["results"])
    assert Event.objects.for_tenant(tenant).filter(
        event_type=vocab.NOTIFICATION, metadata__kind=digest.EVENT_KIND_DIGEST,
    ).count() == 2


def test_run_digest_for_tenant_records_failed_terminal_status(tenant, monkeypatch):
    _set_config(tenant, **{MESSAGING_DIGEST_RECIPIENTS: "919876543210"})
    fake_crm = _FakeCrmRead(SendQueueCounts(date_ist="x", referral={}, other={}))
    fake_messaging = _FakeMessaging(terminal_status=wati_status.STATUS_FAILED)
    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)
    monkeypatch.setattr(digest, "get_messaging_port", lambda: fake_messaging)

    result = digest.run_digest_for_tenant(tenant, day=date(2026, 8, 10))
    assert result["results"][0]["outcome"] == "failed"

    from apps.integrations.models import Notification

    n = Notification.objects.for_tenant(tenant).latest("id")
    assert n.status == wati_status.STATUS_FAILED
    assert n.recipient_role == "office"


def test_run_digest_for_tenant_send_exception_does_not_raise(tenant, monkeypatch):
    _set_config(tenant, **{MESSAGING_DIGEST_RECIPIENTS: "919876543210"})
    fake_crm = _FakeCrmRead(SendQueueCounts(date_ist="x", referral={}, other={}))

    class _BoomMessaging(_FakeMessaging):
        def send_template(self, *, to, template, params):
            raise RuntimeError("network exploded")

    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)
    monkeypatch.setattr(digest, "get_messaging_port", lambda: _BoomMessaging())

    result = digest.run_digest_for_tenant(tenant, day=date(2026, 8, 10))  # must not raise
    assert result["results"][0]["outcome"] == "failed"


def test_run_daily_digest_only_fires_at_the_configured_hour(tenant, monkeypatch):
    _set_config(tenant, **{
        MESSAGING_DIGEST_SEND_HOUR_IST: 9, MESSAGING_DIGEST_RECIPIENTS: "919876543210",
    })
    fake_crm = _FakeCrmRead(SendQueueCounts(date_ist="x", referral={}, other={}))
    fake_messaging = _FakeMessaging()
    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)
    monkeypatch.setattr(digest, "get_messaging_port", lambda: fake_messaging)

    # 09:00 IST == 03:30 UTC
    off_hour = timezone.datetime(2026, 8, 11, 1, 0, tzinfo=dt_timezone.utc)
    results = digest.run_daily_digest(now_utc=off_hour)
    assert results[tenant.slug]["skipped"] is True
    assert fake_messaging.template_sends == []

    on_hour = timezone.datetime(2026, 8, 11, 3, 30, tzinfo=dt_timezone.utc)
    results = digest.run_daily_digest(now_utc=on_hour)
    assert results[tenant.slug]["skipped"] is False
    assert len(fake_messaging.template_sends) == 1


# --------------------------------------------------------------------------- alerts


def test_alerts_inert_when_disabled(tenant, monkeypatch):
    _set_config(tenant, **{MESSAGING_DIGEST_ALERTS_ENABLED: False})
    result = digest.run_alerts_for_tenant(tenant)
    assert result["skipped"] is True


def test_recovery_alert_fires_once_per_day(tenant, monkeypatch):
    _set_config(tenant, **{
        MESSAGING_DIGEST_ALERTS_ENABLED: True,
        MESSAGING_DIGEST_ALERT_RECOVERY_HITS: 1,
        MESSAGING_DIGEST_RECIPIENTS: "919876543210",
    })
    identity = _identity(tenant, "RJ4521")
    program = ReferralProgram.objects.get(tenant=tenant)
    from apps.referrals.models import Referral

    referral = Referral.objects.create(
        tenant=tenant, referral_identity=identity, program=program, source="referral_link",
    )
    # IST calendar day, not the UTC one `timezone.now().date()` would give — the
    # digest's own day-bounds math (`_ist_day_bounds_utc`) windows by IST day, and
    # UTC 18:30-23:59 is already the NEXT IST day, so a naive UTC date flakes in
    # that window even though the event and the "today" arg are both real-time.
    today = (timezone.now() + IST_OFFSET).date()
    for _ in range(3):
        Event.objects.create(
            tenant=tenant, event_type=vocab.SHARE_RECOVERY_VIEWED, referral=referral, is_bot=False,
            timestamp=timezone.now(),
        )

    fake_crm = _FakeCrmRead(SendQueueCounts(date_ist="x", referral={}, other={}))
    fake_messaging = _FakeMessaging()
    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)
    monkeypatch.setattr(digest, "get_messaging_port", lambda: fake_messaging)

    first = digest.run_alerts_for_tenant(tenant, day=today)
    assert digest.RULE_RECOVERY_HITS in first["fired"]
    assert len(fake_messaging.session_sends) == 1

    second = digest.run_alerts_for_tenant(tenant, day=today)
    assert digest.RULE_RECOVERY_HITS not in second["fired"]
    assert len(fake_messaging.session_sends) == 1  # not sent again


def test_failure_ratio_alert_fires_when_over_threshold(tenant, monkeypatch):
    _set_config(tenant, **{
        MESSAGING_DIGEST_ALERTS_ENABLED: True,
        MESSAGING_DIGEST_RECIPIENTS: "919876543210",
    })
    counts = SendQueueCounts(date_ist="x", referral={"SENT": 1, "FAILED": 9}, other={})
    fake_crm = _FakeCrmRead(counts)
    fake_messaging = _FakeMessaging()
    monkeypatch.setattr(digest, "get_crm_read_port", lambda: fake_crm)
    monkeypatch.setattr(digest, "get_messaging_port", lambda: fake_messaging)

    today = timezone.now().date()
    result = digest.run_alerts_for_tenant(tenant, day=today)
    assert digest.RULE_FAILURE_RATIO in result["fired"]
    assert len(fake_messaging.session_sends) == 1


def test_schedules_registered():
    from apps.events.management.commands.setup_schedules import SCHEDULES

    assert SCHEDULES["funnel_digest_daily"] == ("apps.campaigns.digest.run_daily_digest", 60)
    assert SCHEDULES["funnel_digest_alerts"] == ("apps.campaigns.digest.run_instant_alerts", 15)
