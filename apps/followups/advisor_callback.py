"""T-097 — advisor callback: alert a staff number now, remind at the promised slot.

A chatbot flow captures a preferred call-back slot (one of three fixed windows).
GoRefer sends an IMMEDIATE alert to a staff number, then rides the EXISTING
`apps.followups` engine (ScheduledFollowup + `fire_due_followups` sweep) for a TIMED
reminder at the slot's start — no second scheduler.

Kept as its own module (not folded into `services.py`/`tasks.py`) because the gate
here is deliberately NOT `services.evaluate_gate`: that gate encodes prospect-nudge
concepts (24h window, engaged-exit-on-reply, per-AP `followups_enabled`) that don't
apply to a staff alert. This module reuses the two guards that DO apply — quiet
hours and the anti-burst min-gap — by calling the same `services` functions, so the
staff number is protected by the identical rules a customer nudge is.
"""
from __future__ import annotations

from datetime import timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from apps.config.cascade import resolve
from apps.integrations.ports import get_messaging_port

from . import services
from .models import AdvisorCallbackRequest, FollowupRule, ScheduledFollowup

STEP_KEY = "advisor_callback_reminder"

ADVISOR_ALERT_NUMBER_KEY = "advisor_alert_number"
ADVISOR_ALERT_NUMBER_DEFAULT = "917388882020"
ADVISOR_ALERT_TEMPLATE_KEY = "advisor_alert_template_en"
ADVISOR_ALERT_TEMPLATE_DEFAULT = "gr_pifs_advisor_callback_alert_en_2026_08_11"
ADVISOR_REMINDER_TEMPLATE_KEY = "advisor_reminder_template_en"
ADVISOR_REMINDER_TEMPLATE_DEFAULT = "gr_pifs_advisor_callback_reminder_en_2026_08_11"

DEC_SEND = "send"


def _advisor_number(tenant_id: int | None) -> str:
    return str(resolve(ADVISOR_ALERT_NUMBER_KEY, tenant_id=tenant_id, default=ADVISOR_ALERT_NUMBER_DEFAULT))


def _alert_template(tenant_id: int | None) -> str:
    return str(
        resolve(ADVISOR_ALERT_TEMPLATE_KEY, tenant_id=tenant_id, default=ADVISOR_ALERT_TEMPLATE_DEFAULT)
    )


def _reminder_template(tenant_id: int | None) -> str:
    return str(
        resolve(ADVISOR_REMINDER_TEMPLATE_KEY, tenant_id=tenant_id, default=ADVISOR_REMINDER_TEMPLATE_DEFAULT)
    )


def _params(name: str, mobile: str, slot: str) -> dict:
    label = AdvisorCallbackRequest.SLOT_LABELS.get(slot, slot)
    return {
        "template_params": [
            {"name": "1", "value": name or "Not provided"},
            {"name": "2", "value": mobile},
            {"name": "3", "value": label},
        ],
    }


def compute_fire_at(slot: str, now):
    """Start of `slot` in IST, today — or tomorrow if that time already passed."""
    hour = AdvisorCallbackRequest.SLOT_START_HOUR_IST[slot]
    ist = now.astimezone(dt_timezone.utc) + services.IST_OFFSET
    target_ist = ist.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target_ist <= ist:
        target_ist += timedelta(days=1)
    return target_ist - services.IST_OFFSET


def _get_or_create_rule(tenant) -> FollowupRule:
    rule, _ = FollowupRule.objects.get_or_create(
        tenant=tenant,
        step_key=STEP_KEY,
        defaults=dict(
            offset_minutes=0,
            channel=FollowupRule.CHANNEL_TEMPLATE,
            template_name=ADVISOR_REMINDER_TEMPLATE_DEFAULT,
            enabled=True,
            only_if_window_open=False,
            stop_on_reply=False,
            order=900,
        ),
    )
    return rule


def request_and_schedule(tenant, *, mobile: str, name: str, slot: str, now=None):
    """Create the (idempotent) request row + its linked ScheduledFollowup reminder.

    Returns (request, created). `created=False` means this exact (mobile, slot,
    request_date=today IST) already exists — the caller must not re-send the alert
    or re-schedule the reminder.
    """
    now = now or timezone.now()
    request_date = (now.astimezone(dt_timezone.utc) + services.IST_OFFSET).date()

    existing = AdvisorCallbackRequest.objects.for_tenant(tenant).filter(
        mobile=mobile, slot=slot, request_date=request_date
    ).first()
    if existing is not None:
        return existing, False

    rule = _get_or_create_rule(tenant)
    fire_at = compute_fire_at(slot, now)

    req = AdvisorCallbackRequest.objects.create(
        tenant=tenant, mobile=mobile, name=name, slot=slot, request_date=request_date,
    )
    # A duplicate slipping past the pre-check (race) trips the unique constraint here;
    # let it propagate — the caller treats any IntegrityError-on-create as "already
    # requested" and re-reads the existing row (see api layer).
    sf = ScheduledFollowup.objects.create(
        tenant=tenant,
        rule=rule,
        mobile=_advisor_number(tenant.id if tenant else None),
        pref_lang="en",
        fire_at=fire_at,
        window_opened_at=now,
        status=ScheduledFollowup.STATUS_SCHEDULED,
        source_event="advisor_callback",
        dedupe_key=f"advisor_reminder|{tenant.id if tenant else 0}|{req.pk}",
    )
    req.reminder = sf
    req.save(update_fields=["reminder", "updated_at"])
    return req, True


def send_alert(tenant, request: AdvisorCallbackRequest) -> bool:
    """Send the IMMEDIATE staff alert. Never raises — a send failure must not fail
    the customer-facing capture; the reminder still fires later regardless."""
    try:
        to = _advisor_number(tenant.id if tenant else None)
        template = _alert_template(tenant.id if tenant else None)
        result = get_messaging_port().send_template(
            to=to, template=template, params=_params(request.name, request.mobile, request.slot)
        )
        request.alert_sent_at = timezone.now()
        request.save(update_fields=["alert_sent_at", "updated_at"])
        return bool(result.accepted)
    except Exception:
        import logging

        logging.getLogger("gorefer.followups.advisor_callback").warning(
            "advisor callback alert send failed for request=%s", request.pk, exc_info=True
        )
        return False


def evaluate_gate(sf: ScheduledFollowup, now=None) -> tuple[str, str]:
    """Pure gate for an advisor-reminder row: done? -> cancel; else quiet-hours/min-gap
    (reusing the SAME guards `services.evaluate_gate` uses) -> hold; else send."""
    now = now or timezone.now()
    req = getattr(sf, "advisor_callback_request", None)
    if req is not None and req.done:
        return services.DEC_CANCEL, "advisor callback marked done"

    if services.in_quiet_hours(now, sf.tenant_id):
        _, end = services._quiet_bounds(sf.tenant_id)
        return services.DEC_HOLD, f"quiet hours — deferred to {end:02d}:00 IST"
    if services.within_min_gap(sf.tenant, sf.mobile, now, sf.tenant_id):
        return services.DEC_HOLD, "min-gap — spacing sends to the advisor number"
    return DEC_SEND, "reminder due"


def apply(sf: ScheduledFollowup, decision: str, reason: str, now, counts: dict) -> None:
    if decision == services.DEC_CANCEL:
        sf.status = ScheduledFollowup.STATUS_CANCELLED
        sf.reason = reason
        sf.save(update_fields=["status", "reason", "updated_at"])
        counts["cancelled"] += 1
        return
    if decision == services.DEC_HOLD:
        sf.fire_at = services.compute_defer(now, sf.tenant, sf.mobile, sf.tenant_id)
        sf.reason = reason
        sf.save(update_fields=["fire_at", "reason", "updated_at"])
        counts["held"] += 1
        return

    req = getattr(sf, "advisor_callback_request", None)
    to = _advisor_number(sf.tenant_id)
    template = _reminder_template(sf.tenant_id)
    name = req.name if req else ""
    mobile = req.mobile if req else ""
    slot = req.slot if req else ""
    result = get_messaging_port().send_template(to=to, template=template, params=_params(name, mobile, slot))
    if result.accepted:
        sf.status = ScheduledFollowup.STATUS_SENT
        sf.sent_at = now
        sf.reason = reason
        counts["sent"] += 1
    else:
        sf.status = ScheduledFollowup.STATUS_FAILED
        sf.reason = "send not accepted"
        counts["failed"] += 1
    sf.save(update_fields=["status", "sent_at", "reason", "updated_at"])
