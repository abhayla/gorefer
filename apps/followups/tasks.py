"""Follow-up engine background tasks (django-q).

  - enqueue_followups(): on chat-open, insert one ScheduledFollowup per enabled rule step.
  - fire_due_followups(): the recurring sweep (registered in setup_schedules as
    `followup_sweep`, every 5 min). Selects due SCHEDULED rows, LOCKS each, runs the gate
    (services.evaluate_gate), and sends via the Wati adapter. Mirrors
    `apps.integrations.wati.tasks.reconcile_pending_deliveries` exactly — a recurring sweep
    over a due-table, the idiom the whole engine is built on.

In sync/demo mode (Q_CLUSTER sync=True, ENABLE_WATI_SEND=false) this runs inline against
the log-only adapter, so the whole flow is testable offline. Nothing sends until
`followups_enabled` is True for the tenant — checked at enqueue AND re-checked at fire time,
so a flag flipped OFF after scheduling cancels pending rows instead of sending them.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.events import vocab
from apps.events.models import Event
from apps.integrations.wati import status as st
from apps.integrations.wati.adapter import get_wati_adapter

from . import services
from .models import FollowupRule, ScheduledFollowup

logger = logging.getLogger("gorefer.followups.tasks")


def enqueue_followups(
    tenant_id: int,
    mobile: str,
    *,
    opened_at=None,
    prospect_id: int | None = None,
    source_event: str = "wati_inbound",
    pref_lang: str = "en",
) -> dict:
    """Insert one ScheduledFollowup per enabled rule at chat-open. Idempotent per window.

    dedupe_key = tenant|mobile|step|window-open — so a repeated enqueue for the SAME open
    creates nothing new (get_or_create on the unique key). Refuses when the flag is off or
    the contact is opted out.
    """
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return {"created": 0, "reason": "no tenant"}
    if not services.followups_enabled(tenant_id):
        return {"created": 0, "reason": "disabled"}
    if services.is_opted_out(tenant, mobile):
        return {"created": 0, "reason": "opted_out"}

    opened_at = opened_at or timezone.now()
    rules = FollowupRule.objects.filter(tenant=tenant, enabled=True).order_by("order", "id")
    created = 0
    for rule in rules:
        fire_at = opened_at + timedelta(minutes=rule.offset_minutes)
        dkey = f"{tenant_id}|{mobile}|{rule.step_key}|{opened_at.isoformat()}"
        _, was_created = ScheduledFollowup.objects.get_or_create(
            dedupe_key=dkey,
            defaults=dict(
                tenant=tenant,
                rule=rule,
                prospect_id=prospect_id,
                mobile=mobile,
                pref_lang=pref_lang,
                fire_at=fire_at,
                window_opened_at=opened_at,
                status=ScheduledFollowup.STATUS_SCHEDULED,
                source_event=source_event,
            ),
        )
        if was_created:
            created += 1
    return {"created": created}


def fire_due_followups(limit: int = 200) -> dict:
    """Sweep due SCHEDULED follow-ups: lock each, run the gate, send/cancel/skip.

    Row-locked (select_for_update) per row so a concurrent CRUD edit can't race a send.
    Returns a per-outcome tally.
    """
    now = timezone.now()
    due_ids = list(
        ScheduledFollowup.objects.filter(
            status=ScheduledFollowup.STATUS_SCHEDULED, fire_at__lte=now
        )
        .order_by("fire_at")
        .values_list("id", flat=True)[:limit]
    )
    counts = {"sent": 0, "cancelled": 0, "skipped": 0, "failed": 0, "held": 0}
    for sid in due_ids:
        try:
            with transaction.atomic():
                # Lock ONLY this row (of=("self",)) — never the FollowupRule it points at,
                # so locking a due row can't block a rule edit.
                sf = (
                    ScheduledFollowup.objects.select_for_update(of=("self",))
                    .get(pk=sid)
                )
                if sf.status != ScheduledFollowup.STATUS_SCHEDULED:
                    continue  # already handled by a concurrent sweep / cancelled by CRUD
                decision, reason = services.evaluate_gate(sf, now)
                _apply(sf, decision, reason, now, counts)
        except Exception:
            # One bad row must never sink the whole sweep — log and move on.
            logger.warning("followup fire failed for id=%s", sid, exc_info=True)
    return counts


def _apply(sf: ScheduledFollowup, decision: str, reason: str, now, counts: dict) -> None:
    if decision == services.DEC_CANCEL:
        sf.status = ScheduledFollowup.STATUS_CANCELLED
        sf.reason = reason
        sf.save(update_fields=["status", "reason", "updated_at"])
        counts["cancelled"] += 1
        return
    if decision == services.DEC_SKIP:
        sf.status = ScheduledFollowup.STATUS_SKIPPED
        sf.reason = reason
        sf.save(update_fields=["status", "reason", "updated_at"])
        counts["skipped"] += 1
        return
    if decision == services.DEC_HOLD:
        # Quiet hours — DON'T send; defer to 06:00 IST and stay SCHEDULED so a later
        # sweep sends it. Never messages anyone 23:00–06:00 IST (owner rule).
        sf.fire_at = services.next_active_time(now, sf.tenant_id)
        sf.reason = reason
        sf.save(update_fields=["fire_at", "reason", "updated_at"])
        counts["held"] += 1
        return

    adapter = get_wati_adapter()
    rule = sf.rule
    if decision == services.DEC_SEND_SESSION:
        message = services.body_for(rule, sf.pref_lang)
        result = adapter.send_session_text(to=sf.mobile, message=message)
    else:  # DEC_SEND_TEMPLATE
        result = adapter.send_template(
            to=sf.mobile, template=rule.template_name, params={"role": "prospect"}
        )

    if result.accepted:
        sf.status = ScheduledFollowup.STATUS_SENT
        sf.sent_at = now
        sf.reason = reason
        counts["sent"] += 1
        _emit_funnel_event(sf, decision)
    elif result.raw_status == st.STATUS_BLOCKED:
        # Fail-closed allowlist blocked it — a suppression, not a delivery failure.
        sf.status = ScheduledFollowup.STATUS_SKIPPED
        sf.reason = "recipient not in Wati allowlist (fail-closed)"
        counts["skipped"] += 1
    else:
        # Accepted != delivered elsewhere; here 'not accepted' is a real send failure.
        sf.status = ScheduledFollowup.STATUS_FAILED
        sf.reason = "send not accepted"
        counts["failed"] += 1
    sf.save(update_fields=["status", "sent_at", "reason", "updated_at"])


def _emit_funnel_event(sf: ScheduledFollowup, decision: str) -> None:
    """Emit a PII-free funnel event so a follow-up send is observable (Constitution §5).

    Deliberately carries NO mobile/name — the immutable event log never holds PII (#16).
    """
    try:
        Event.objects.create(
            tenant=sf.tenant,
            event_type=vocab.NOTIFICATION,
            source=vocab.SRC_WATI,
            user_type="system",
            metadata={"kind": "followup", "step": sf.rule.step_key, "decision": decision},
        )
    except Exception:
        logger.warning("followup funnel event emit failed", exc_info=True)
