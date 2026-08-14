"""T-125 (W2) — messaging campaign engine: eligibility, enqueue idempotency, the
fire-time gate (opt-out / converted-suppression / quiet hours / rolling budgets /
send-days-hour / on-reply cancel), fail-closed sending, language fallback, and
schedule registration.

All run in sync/demo mode (Q_CLUSTER sync=True); sends go through the LogOnly Wati
adapter unless a test explicitly swaps in a fake, mirroring tests/test_followups.py.
"""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.campaigns import send as campaign_send
from apps.campaigns import services, tasks
from apps.campaigns.models import (
    DEFAULT_SEND_DAYS_MASK,
    MessagingCampaign,
    MessagingCampaignStep,
    ScheduledCampaignMessage,
    SyncedReferrer,
)
from apps.followups.models import FollowupWindow
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.resolve import get_bootstrap_tenant

pytestmark = pytest.mark.django_db

MOBILE = "919812340001"
CID = "RJ9001"


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def _identity(tenant, client_id: str) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _campaign(tenant, *, enabled=True, **overrides) -> MessagingCampaign:
    defaults = dict(
        tenant=tenant, slug="referrer-recurring", name="Referrer recurring nudge",
        enabled=enabled, max_msgs_per_24h=1, max_msgs_per_72h=1, max_msgs_per_7d=2,
        send_hour_ist=9, send_days_mask=DEFAULT_SEND_DAYS_MASK,
        language_template_map={"en": "gr_platform_gorefer_refrecord_en_2026_08_07"},
    )
    defaults.update(overrides)
    return MessagingCampaign.objects.create(**defaults)


def _step(campaign, tenant, *, order=1, gap_days=3, enabled=True, language="en", template_name=""):
    return MessagingCampaignStep.objects.create(
        tenant=tenant, campaign=campaign, order=order, gap_days_from_previous=gap_days,
        enabled=enabled, language=language, template_name=template_name,
    )


def _referrer(tenant, *, client_id=CID, mobile=MOBILE, anchor_ago_days=0, active=True, language="en"):
    return SyncedReferrer.objects.create(
        tenant=tenant, client_id=client_id, mobile=mobile, name="Riya", language=language,
        record_created_at=timezone.now() - timedelta(days=anchor_ago_days), active=active,
    )


def _due(campaign, step, referrer, *, tenant, fire_ago_min=1, anchor_at=None):
    anchor_at = anchor_at or referrer.record_created_at
    return ScheduledCampaignMessage.objects.create(
        tenant=tenant, campaign=campaign, step=step, referrer=referrer,
        client_id=referrer.client_id, mobile=referrer.mobile, language=referrer.language,
        anchor_at=anchor_at, fire_at=timezone.now() - timedelta(minutes=fire_ago_min),
        dedupe_key=f"{tenant.id}|{campaign.id}|{referrer.mobile}|{step.id}|{anchor_at.isoformat()}",
    )


def _set_flags(monkeypatch, **overrides):
    from gorefer import flags as flags_mod

    new = dataclasses.replace(flags_mod.flags, **overrides)
    monkeypatch.setattr(flags_mod, "flags", new)
    return new


def _records_link_on(monkeypatch):
    _set_flags(monkeypatch, ENABLE_RECORDS_LINK=True)


def _always_in_window(monkeypatch):
    """Pin the timing gates out of the way so a test can isolate one other gate."""
    monkeypatch.setattr(services, "in_send_window", lambda *a, **k: True)
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)


# --------------------------------------------------------------------- eligibility


def test_eligible_referrers_respects_min_records(tenant):
    campaign = _campaign(tenant, min_records=1)
    ref = _referrer(tenant)
    assert services.eligible_referrers(campaign, tenant) == []  # zero GoRefer records

    from apps.referrals import redirect_service

    program = redirect_service.get_active_program(tenant)
    redirect_service._lazy_get_or_create_referral(tenant, program, CID)
    assert list(services.eligible_referrers(campaign, tenant)) == [ref]


def test_eligible_referrers_respects_activity_window(tenant):
    campaign = _campaign(tenant, activity_window_days=7)
    fresh = _referrer(tenant, client_id="RJ1", mobile="919000000001", anchor_ago_days=1)
    stale = _referrer(tenant, client_id="RJ2", mobile="919000000002", anchor_ago_days=30)

    result = services.eligible_referrers(campaign, tenant)
    assert fresh in result
    assert stale not in result


def test_eligible_referrers_excludes_converted(tenant):
    from apps.referrals.models import Lead, Prospect, Referral
    from apps.referrals.models import ReferralProgram as RP

    campaign = _campaign(tenant, exclude_converted=True)
    _referrer(tenant)
    program = RP.objects.get(tenant=tenant)
    prospect = Prospect.objects.create(tenant=tenant, mobile=MOBILE, name="P")
    referral = Referral.objects.create(tenant=tenant, program=program, source="partner_direct")
    Lead.objects.create(tenant=tenant, referral=referral, prospect=prospect,
                        status="new", consent=True)
    Referral.objects.filter(pk=referral.pk).update(conversion_status="account_opened")

    assert services.eligible_referrers(campaign, tenant) == []


def test_manual_exclude_wins_over_include(tenant):
    campaign = _campaign(tenant, manual_include_mobiles=[MOBILE], manual_exclude_mobiles=[MOBILE])
    _referrer(tenant)
    assert services.eligible_referrers(campaign, tenant) == []


def test_manual_include_bypasses_min_records(tenant):
    campaign = _campaign(tenant, min_records=99, manual_include_mobiles=[MOBILE])
    ref = _referrer(tenant)
    assert list(services.eligible_referrers(campaign, tenant)) == [ref]


def test_inactive_referrer_never_eligible(tenant):
    campaign = _campaign(tenant)
    _referrer(tenant, active=False)
    assert services.eligible_referrers(campaign, tenant) == []


# --------------------------------------------------------------------- enqueue + idempotency


def test_enqueue_creates_ladder_anchored_on_record_created_at(tenant):
    campaign = _campaign(tenant)
    s1 = _step(campaign, tenant, order=1, gap_days=3)
    s2 = _step(campaign, tenant, order=2, gap_days=3)
    ref = _referrer(tenant)

    out = tasks.enqueue_campaign_messages(campaign.id)

    assert out["created"] == 2
    rows = ScheduledCampaignMessage.objects.order_by("fire_at")
    assert [r.step_id for r in rows] == [s1.id, s2.id]
    assert rows[0].fire_at == ref.record_created_at + timedelta(days=3)
    assert rows[1].fire_at == ref.record_created_at + timedelta(days=6)


def test_enqueue_is_idempotent(tenant):
    campaign = _campaign(tenant)
    _step(campaign, tenant)
    _referrer(tenant)

    first = tasks.enqueue_campaign_messages(campaign.id)
    second = tasks.enqueue_campaign_messages(campaign.id)

    assert first["created"] == 1
    assert second["created"] == 0
    assert ScheduledCampaignMessage.objects.count() == 1


def test_enqueue_skips_disabled_campaign(tenant):
    campaign = _campaign(tenant, enabled=False)
    _step(campaign, tenant)
    _referrer(tenant)

    out = tasks.enqueue_campaign_messages()
    assert out["created"] == 0
    assert ScheduledCampaignMessage.objects.count() == 0


def test_enqueue_skips_disabled_step(tenant):
    campaign = _campaign(tenant)
    _step(campaign, tenant, order=1, enabled=True)
    _step(campaign, tenant, order=2, enabled=False)
    _referrer(tenant)

    out = tasks.enqueue_campaign_messages(campaign.id)
    assert out["created"] == 1


# --------------------------------------------------------------------- fire-time gate: cancel


def test_campaign_disabled_cancels_pending(tenant, monkeypatch):
    _always_in_window(monkeypatch)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    scm = _due(campaign, step, ref, tenant=tenant)
    campaign.enabled = False
    campaign.save(update_fields=["enabled"])

    tasks.fire_due_campaign_messages()

    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_CANCELLED
    assert "disabled" in scm.reason


def test_opt_out_cancels(tenant, monkeypatch):
    _always_in_window(monkeypatch)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    FollowupWindow.objects.create(tenant=tenant, mobile=MOBILE, opted_out=True)
    scm = _due(campaign, step, ref, tenant=tenant)

    tasks.fire_due_campaign_messages()

    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_CANCELLED
    assert "opted out" in scm.reason


def test_converted_suppression_cancels(tenant, monkeypatch):
    from apps.referrals.models import Lead, Prospect, Referral
    from apps.referrals.models import ReferralProgram as RP

    _always_in_window(monkeypatch)
    campaign = _campaign(tenant, exclude_converted=True)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    program = RP.objects.get(tenant=tenant)
    prospect = Prospect.objects.create(tenant=tenant, mobile=MOBILE, name="P")
    referral = Referral.objects.create(tenant=tenant, program=program, source="partner_direct")
    Lead.objects.create(tenant=tenant, referral=referral, prospect=prospect, status="new", consent=True)
    Referral.objects.filter(pk=referral.pk).update(conversion_status="account_opened")
    scm = _due(campaign, step, ref, tenant=tenant)

    tasks.fire_due_campaign_messages()

    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_CANCELLED
    assert "converted" in scm.reason


def test_on_reply_cancels_remaining_steps(tenant, monkeypatch):
    """An inbound AFTER enqueue (row created_at) cancels the mobile's pending steps."""
    _always_in_window(monkeypatch)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    scm = _due(campaign, step, ref, tenant=tenant)
    # An inbound strictly AFTER this row's enqueue instant = engagement.
    FollowupWindow.objects.create(
        tenant=tenant, mobile=MOBILE, last_inbound_at=scm.created_at + timedelta(minutes=1)
    )

    tasks.fire_due_campaign_messages()

    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_CANCELLED
    assert "on_reply" in scm.reason


def test_reply_before_enqueue_does_not_cancel(tenant, monkeypatch):
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    _identity(tenant, CID)
    FollowupWindow.objects.create(
        tenant=tenant, mobile=MOBILE, last_inbound_at=timezone.now() - timedelta(days=10)
    )
    _due(campaign, step, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["cancelled"] == 0
    assert counts["sent"] == 1


# --------------------------------------------------------------------- fire-time gate: hold (defer, not drop)


def test_quiet_hours_holds_not_cancels(tenant, monkeypatch):
    monkeypatch.setattr(services, "in_send_window", lambda *a, **k: True)
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: True)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    scm = _due(campaign, step, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["held"] == 1
    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_SCHEDULED  # deferred, not dropped
    assert scm.fire_at > timezone.now()
    assert "quiet hours" in scm.reason


def test_outside_send_window_holds_not_cancels(tenant, monkeypatch):
    monkeypatch.setattr(services, "in_send_window", lambda *a, **k: False)
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    scm = _due(campaign, step, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["held"] == 1
    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_SCHEDULED
    assert "send-days/hour" in scm.reason


def test_rolling_budget_holds_a_second_send(tenant, monkeypatch):
    """max_msgs_per_24h=1: a second SENT row inside 24h must HOLD, not send."""
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign = _campaign(tenant, max_msgs_per_24h=1, max_msgs_per_72h=99, max_msgs_per_7d=99)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    _identity(tenant, CID)
    # A prior SENT row for this mobile+campaign inside the 24h window.
    ScheduledCampaignMessage.objects.create(
        tenant=tenant, campaign=campaign, step=step, referrer=ref,
        client_id=CID, mobile=MOBILE, language="en", anchor_at=timezone.now(),
        fire_at=timezone.now() - timedelta(hours=2), status=ScheduledCampaignMessage.STATUS_SENT,
        sent_at=timezone.now() - timedelta(hours=2),
        dedupe_key="prior-sent-row",
    )
    scm = _due(campaign, step, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["held"] == 1
    assert counts["sent"] == 0
    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_SCHEDULED
    assert "budget" in scm.reason


def test_rolling_budget_lets_a_lone_send_through(tenant, monkeypatch):
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign = _campaign(tenant, max_msgs_per_24h=1)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    _identity(tenant, CID)
    scm = _due(campaign, step, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["sent"] == 1 and counts["held"] == 0
    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_SENT


def test_rolling_budget_is_per_recipient_across_campaigns(tenant, monkeypatch):
    """A SENT row from campaign A consumes the SAME mobile's budget headroom for
    campaign B — the cap is per-recipient, not per-campaign-stream (plan ⑦)."""
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign_a = _campaign(
        tenant, slug="referrer-recurring-a", max_msgs_per_24h=1, max_msgs_per_72h=99, max_msgs_per_7d=99
    )
    campaign_b = _campaign(
        tenant, slug="referrer-recurring-b", max_msgs_per_24h=1, max_msgs_per_72h=99, max_msgs_per_7d=99
    )
    step_a = _step(campaign_a, tenant)
    step_b = _step(campaign_b, tenant)
    ref = _referrer(tenant)
    _identity(tenant, CID)
    # A prior SENT row for this mobile under campaign A (not B) inside the 24h window.
    ScheduledCampaignMessage.objects.create(
        tenant=tenant, campaign=campaign_a, step=step_a, referrer=ref,
        client_id=CID, mobile=MOBILE, language="en", anchor_at=timezone.now(),
        fire_at=timezone.now() - timedelta(hours=2), status=ScheduledCampaignMessage.STATUS_SENT,
        sent_at=timezone.now() - timedelta(hours=2),
        dedupe_key="prior-sent-row-campaign-a",
    )
    scm_b = _due(campaign_b, step_b, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["held"] == 1
    assert counts["sent"] == 0
    scm_b.refresh_from_db()
    assert scm_b.status == ScheduledCampaignMessage.STATUS_SCHEDULED
    assert "budget" in scm_b.reason


# --------------------------------------------------------------------- send: fail-closed guards


def test_unknown_client_id_is_skipped_not_sent(tenant, monkeypatch):
    """T-129: `send_campaign_message` now builds the "token" param straight from
    `client_id` (the RECORDS button carries the raw id, not a signed token — Meta
    silently blanks a URL-button value containing ':'), so the integration can no
    longer produce a blank-token candidate the way the old minted-token path could.
    The real remaining fail-BEFORE-send case is an id `resolve_link_details` cannot
    mint for at all (no matching identity)."""
    _records_link_on(monkeypatch)
    _identity(tenant, CID)

    monkeypatch.setattr(
        campaign_send, "resolve_link_details",
        lambda tenant, client_id: {"error": "unknown_client_id"},
    )

    result = campaign_send.send_campaign_message(
        tenant=tenant, client_id=CID, mobile=MOBILE,
        template="gr_platform_gorefer_refrecord_en_2026_08_07",
    )

    assert result["outcome"] == "skipped"
    assert result["reason"] == "unknown_client_id"


def test_computed_var_guard_still_refuses_a_blank_client_id(tenant, monkeypatch):
    """The `assert_computed_vars_filled` fail-closed contract (T-073) still holds for
    the "token" param even though its source moved from a minted token to the raw
    client_id — proven directly against `_campaign_params`, since the integration
    path itself can no longer construct a blank one (identity lookup guards it
    upstream, in `resolve_link_details`)."""
    from apps.integrations.computed_vars import MissingComputedVar, assert_computed_vars_filled

    params = campaign_send._campaign_params(
        "", {"name": "Riya", "record_date": "1 Jan 2026"}
    )
    with pytest.raises(MissingComputedVar):
        assert_computed_vars_filled("gr_platform_gorefer_refrecord_en_2026_08_07", params)


def test_send_refused_when_records_link_flag_off(tenant, monkeypatch):
    _set_flags(monkeypatch, ENABLE_RECORDS_LINK=False)
    _identity(tenant, CID)

    result = campaign_send.send_campaign_message(
        tenant=tenant, client_id=CID, mobile=MOBILE,
        template="gr_platform_gorefer_refrecord_en_2026_08_07",
    )

    assert result["outcome"] == "skipped"
    assert "ENABLE_RECORDS_LINK" in result["reason"]


def test_send_skips_with_no_template_configured(tenant, monkeypatch):
    _records_link_on(monkeypatch)
    result = campaign_send.send_campaign_message(
        tenant=tenant, client_id=CID, mobile=MOBILE, template="",
    )
    assert result["outcome"] == "skipped"
    assert "no template" in result["reason"]


def test_send_records_link_happy_path_sends_and_records_notification(tenant, monkeypatch):
    _records_link_on(monkeypatch)
    _identity(tenant, CID)
    from apps.integrations.models import Notification

    result = campaign_send.send_campaign_message(
        tenant=tenant, client_id=CID, mobile=MOBILE,
        template="gr_platform_gorefer_refrecord_en_2026_08_07",
    )

    assert result["outcome"] == "sent"
    n = Notification.objects.get()
    assert n.recipient_mobile == MOBILE
    assert n.category == "UTILITY"


# --------------------------------------------------------------------- language -> template (EN fallback)


def test_step_template_falls_back_to_english(tenant):
    campaign = _campaign(tenant, language_template_map={"en": "gr_platform_gorefer_refrecord_en_2026_08_07"})
    step = _step(campaign, tenant, language="hi")  # no HI mapping yet
    assert step.resolved_template_name() == "gr_platform_gorefer_refrecord_en_2026_08_07"


def test_end_to_end_fire_uses_recipient_language_template_mapping(tenant, monkeypatch):
    """The RECIPIENT's language (from the synced referrer) drives template selection —
    not the step's own static `language` field, which is authored as "en" here on
    purpose to prove the send path doesn't fall back to it."""
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign = _campaign(
        tenant,
        language_template_map={
            "en": "gr_platform_gorefer_refrecord_en_2026_08_07",
            "hi": "gr_platform_gorefer_refrecord_hi_2026_08_07",
        },
    )
    step = _step(campaign, tenant, language="en")  # step authored in EN...
    ref = _referrer(tenant, language="hi")          # ...but this referrer prefers HI
    _identity(tenant, CID)
    _due(campaign, step, ref, tenant=tenant)

    tasks.fire_due_campaign_messages()

    from apps.integrations.models import Notification

    n = Notification.objects.get()
    assert n.template == "gr_platform_gorefer_refrecord_hi_2026_08_07"


# --------------------------------------------------------------------- demo mode (ENABLE_WATI_SEND off)


def test_demo_mode_logs_intended_send_via_logonly_adapter(tenant, monkeypatch):
    """With ENABLE_WATI_SEND off (the untouched default), the port factory resolves
    the LogOnly adapter — the engine still runs the full flow end-to-end offline."""
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign = _campaign(tenant)
    step = _step(campaign, tenant)
    ref = _referrer(tenant)
    _identity(tenant, CID)
    scm = _due(campaign, step, ref, tenant=tenant)

    counts = tasks.fire_due_campaign_messages()

    assert counts["sent"] == 1
    scm.refresh_from_db()
    assert scm.status == ScheduledCampaignMessage.STATUS_SENT


# --------------------------------------------------------------------- run_campaign_engine


def test_run_campaign_engine_inert_when_no_campaign_enabled(tenant):
    _campaign(tenant, enabled=False)
    out = tasks.run_campaign_engine()
    assert out["enqueue"]["created"] == 0
    assert out["fire"] == {"sent": 0, "cancelled": 0, "skipped": 0, "failed": 0, "held": 0}


def test_run_campaign_engine_end_to_end(tenant, monkeypatch):
    _always_in_window(monkeypatch)
    _records_link_on(monkeypatch)
    campaign = _campaign(tenant)
    _step(campaign, tenant, gap_days=0)  # fires immediately at the anchor
    _identity(tenant, CID)
    _referrer(tenant, anchor_ago_days=1)  # anchor already in the past -> due now

    out = tasks.run_campaign_engine()

    assert out["enqueue"]["created"] == 1
    assert out["fire"]["sent"] == 1


# --------------------------------------------------------------------- schedule registration


def test_campaign_engine_schedule_registered():
    from apps.events.management.commands.setup_schedules import SCHEDULES

    assert SCHEDULES["messaging_campaign_engine"] == ("apps.campaigns.tasks.run_campaign_engine", 10)
