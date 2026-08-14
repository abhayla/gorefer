"""Messaging campaign engine — eligibility, enqueue ladder math and the fire-time
gate (T-125, W2 of the configurable messaging engine plan).

Kept separate from `tasks.py` (the django-q entry points) exactly like
`apps.followups.services` / `apps.followups.tasks` split decisions from I/O — the
gate returns a DECISION, `tasks.py` applies it (sends + writes). Every gate that has
a followups-engine equivalent REUSES that function verbatim (imported, not
reimplemented): `is_opted_out`, `has_converted`, `in_quiet_hours`, `next_active_time`
are all generic on (tenant, mobile) / (now, tenant_id) and carry no followups-only
assumption, so importing them here cannot drift from the followups engine's own
behaviour. What is new is per-campaign: eligibility, per-recipient rolling send
budgets, and the send-days/send-hour window (decisions ②/⑦ of the plan).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.followups.services import (
    has_converted,
    in_quiet_hours,
    is_opted_out,
    next_active_time,
)

from .models import MessagingCampaign, ScheduledCampaignMessage, SyncedReferrer

logger = logging.getLogger("gorefer.campaigns.services")

# Gate decisions — same vocabulary as apps.followups.services for a reader who
# already knows that engine.
DEC_SEND = "send"
DEC_CANCEL = "cancel"
DEC_SKIP = "skip"
DEC_HOLD = "hold"  # would send, but a timing/budget gate defers it — stays SCHEDULED


# --------------------------------------------------------------------- eligibility


def record_count(tenant, client_id: str) -> int:
    """GoRefer's own referral-record count for this client_id (§ min_records).

    Deliberately GoRefer's OWN count, not a Zoho count — the eligibility predicate
    is about activity GoRefer itself has observed (doc precedent: ADR-013, GoRefer
    never fabricates a Zoho-side fact; it only reads what it has).
    """
    from apps.referrals.models import Referral

    return (
        Referral.objects.for_tenant(tenant)
        .filter(referral_identity__client_id=client_id, deleted_at__isnull=True)
        .count()
    )


def is_eligible(campaign: MessagingCampaign, tenant, referrer: SyncedReferrer, *, now=None) -> bool:
    """One referrer's eligibility for one campaign (config fields on `campaign`).

    Order: manual exclude wins over everything (an operator's explicit "never");
    manual include bypasses the predicate fields; otherwise every predicate field
    must pass. `activity_window_days` reads the referrer's own anchor
    (`record_created_at`) — blank/None means no window limit.
    """
    now = now or timezone.now()
    exclude = set(campaign.manual_exclude_mobiles or [])
    include = set(campaign.manual_include_mobiles or [])
    if referrer.mobile in exclude:
        return False
    if referrer.mobile in include:
        return True

    if campaign.activity_window_days is not None:
        cutoff = now - timedelta(days=campaign.activity_window_days)
        if referrer.record_created_at < cutoff:
            return False

    if campaign.min_records and record_count(tenant, referrer.client_id) < campaign.min_records:
        return False

    if campaign.exclude_converted and has_converted(tenant, referrer.mobile):
        return False

    return True


def eligible_referrers(campaign: MessagingCampaign, tenant, *, now=None):
    """Every ACTIVE synced referrer this campaign is currently eligible to message."""
    now = now or timezone.now()
    qs = SyncedReferrer.objects.for_tenant(tenant).filter(active=True)
    return [ref for ref in qs if is_eligible(campaign, tenant, ref, now=now)]


# --------------------------------------------------------------------- rolling budgets


def _sent_count_since(tenant, mobile: str, since) -> int:
    """Count of ENGINE sends to this mobile in the window, ACROSS ALL CAMPAIGNS.

    The rolling budgets are per-recipient, not per-campaign-stream (plan decision
    ⑦): a referrer messaged heavily by campaign A must not also be hammered by
    campaign B in the same window, so this deliberately does not filter by
    `campaign`.
    """
    return (
        ScheduledCampaignMessage.objects.for_tenant(tenant)
        .filter(mobile=mobile, status=ScheduledCampaignMessage.STATUS_SENT, sent_at__gte=since)
        .count()
    )


def budget_exceeded(tenant, campaign: MessagingCampaign, mobile: str, now) -> bool:
    """True when sending NOW would exceed any of the campaign's 24h/72h/7d caps.

    Rolling windows, counted from GoRefer's OWN send events for this mobile
    ACROSS ALL CAMPAIGNS — a per-recipient budget, not a per-campaign one (§
    CLAUDE.md honest-limit note in the plan: a Zoho-side send is invisible to
    this count until W3's read lands — stated here, not hidden).
    """
    checks = (
        (timedelta(hours=24), campaign.max_msgs_per_24h),
        (timedelta(hours=72), campaign.max_msgs_per_72h),
        (timedelta(days=7), campaign.max_msgs_per_7d),
    )
    for window, cap in checks:
        if cap <= 0:
            continue
        if _sent_count_since(tenant, mobile, now - window) >= cap:
            return True
    return False


def next_budget_slot(tenant, campaign: MessagingCampaign, mobile: str, now) -> "timezone.datetime":
    """Earliest instant a budget-held send may be retried: just after the OLDEST
    counted send (across all campaigns, per-recipient) inside the tightest
    violated window rolls out of it."""
    checks = (
        (timedelta(hours=24), campaign.max_msgs_per_24h),
        (timedelta(hours=72), campaign.max_msgs_per_72h),
        (timedelta(days=7), campaign.max_msgs_per_7d),
    )
    candidates = []
    for window, cap in checks:
        if cap <= 0:
            continue
        since = now - window
        oldest = (
            ScheduledCampaignMessage.objects.for_tenant(tenant)
            .filter(mobile=mobile, status=ScheduledCampaignMessage.STATUS_SENT, sent_at__gte=since)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
            .first()
        )
        if oldest is not None and _sent_count_since(tenant, mobile, since) >= cap:
            candidates.append(oldest + window)
    return max(candidates) if candidates else now + timedelta(minutes=15)


# --------------------------------------------------------------------- send-days/hour window


def in_send_window(campaign: MessagingCampaign, now) -> bool:
    """True when `now` (an aware UTC instant) falls on an allowed send day AND
    matches the campaign's configured send hour (IST), mirroring the followups
    engine's fixed +5:30 offset approach (no `tzdata` dependency)."""
    from datetime import timezone as dt_timezone

    from apps.followups.services import IST_OFFSET

    ist = now.astimezone(dt_timezone.utc) + IST_OFFSET
    if ist.isoweekday() not in campaign.send_days():
        return False
    return ist.hour == campaign.send_hour_ist


def next_send_window(campaign: MessagingCampaign, now):
    """The next instant (aware UTC) that satisfies BOTH the send-days mask and the
    send hour — walks forward day by day (bounded) rather than assuming tomorrow,
    since a day may be off in the mask."""
    from datetime import timezone as dt_timezone

    from apps.followups.services import IST_OFFSET

    ist = now.astimezone(dt_timezone.utc) + IST_OFFSET
    candidate = ist.replace(hour=campaign.send_hour_ist, minute=0, second=0, microsecond=0)
    if candidate <= ist:
        candidate += timedelta(days=1)
    for _ in range(8):  # at most one full week of walking
        if candidate.isoweekday() in campaign.send_days():
            return candidate - IST_OFFSET
        candidate += timedelta(days=1)
    return candidate - IST_OFFSET  # pathological empty mask — return anyway, never loop forever


# --------------------------------------------------------------------- the fire-time gate


def evaluate_gate(scm: ScheduledCampaignMessage, now=None) -> tuple[str, str]:
    """Decide what to do with a due scheduled campaign message. Pure — no side effects.

    Order: campaign enabled → step enabled → opt-out → on-reply cancel →
    converted-suppression → send-days/hour → rolling budgets → quiet hours.
    """
    now = now or timezone.now()
    campaign = scm.campaign
    tenant_id = scm.tenant_id

    if not campaign.enabled:
        return DEC_CANCEL, "campaign disabled"
    if not scm.step.enabled:
        return DEC_CANCEL, "step disabled"
    if is_opted_out(scm.tenant, scm.mobile):
        return DEC_CANCEL, "opted out"

    # on_reply cancellation: an inbound newer than this row's enqueue (created_at)
    # means the contact engaged — cancel the rest of their ladder for this campaign.
    from apps.followups.models import FollowupWindow

    window = FollowupWindow.objects.for_tenant(scm.tenant).filter(mobile=scm.mobile).first()
    if window is not None and window.last_inbound_at is not None \
            and window.last_inbound_at > scm.created_at:
        return DEC_CANCEL, "on_reply: inbound after enqueue"

    if campaign.exclude_converted and has_converted(scm.tenant, scm.mobile):
        return DEC_CANCEL, "engaged: converted"

    if not in_send_window(campaign, now):
        return DEC_HOLD, "outside configured send-days/hour window"

    if budget_exceeded(scm.tenant, campaign, scm.mobile, now):
        return DEC_HOLD, "rolling send budget reached"

    if in_quiet_hours(now, tenant_id):
        _, end = _quiet_end(tenant_id)
        return DEC_HOLD, f"quiet hours — deferred to {end:02d}:00 IST"

    return DEC_SEND, "eligible"


def _quiet_end(tenant_id):
    from apps.followups.services import _quiet_bounds

    return _quiet_bounds(tenant_id)


def compute_defer(scm: ScheduledCampaignMessage, now) -> "timezone.datetime":
    """Earliest instant a HELD row may be retried — satisfies send-window, budget
    and quiet-hours together (iterates like `apps.followups.services.compute_defer`,
    capped so a pathological config can never loop forever)."""
    campaign = scm.campaign
    tenant_id = scm.tenant_id
    t = now
    for _ in range(4):
        moved = False
        if not in_send_window(campaign, t):
            t = next_send_window(campaign, t)
            moved = True
        if budget_exceeded(scm.tenant, campaign, scm.mobile, t):
            nb = next_budget_slot(scm.tenant, campaign, scm.mobile, t)
            if nb > t:
                t = nb
                moved = True
        if in_quiet_hours(t, tenant_id):
            t = next_active_time(t, tenant_id)
            moved = True
        if not moved:
            break
    return t
