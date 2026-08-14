"""Messaging campaign engine background tasks (T-125, W2).

  - enqueue_campaign_messages(): for each ENABLED campaign, for each eligible
    SyncedReferrer, insert one ScheduledCampaignMessage per enabled step — the
    ladder anchored on the referrer's `record_created_at` (decision ⑪). Idempotent
    per (campaign, mobile, step, anchor) via `dedupe_key` (mirrors
    `apps.followups.tasks.enqueue_followups` exactly).
  - fire_due_campaign_messages(): the recurring sweep — selects due SCHEDULED rows,
    locks each, runs `services.evaluate_gate`, and sends/cancels/skips/holds.
    Mirrors `apps.followups.tasks.fire_due_followups` row-for-row.
  - run_campaign_engine(): the single django-q schedule entry point (enqueue then
    fire in one pass) — inert when no campaign is enabled, per-campaign gates
    still apply inside (the `wa_engagement_report_daily` "poll often, gate on
    config" idiom, generalized to per-campaign rather than per-tenant config).

Demo mode (ENABLE_WATI_SEND=false) runs the same code path against the LogOnly
adapter (see `apps.campaigns.send`), so the whole flow is testable offline.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.events import vocab
from apps.events.models import Event

from . import services
from .models import MessagingCampaign, ScheduledCampaignMessage

logger = logging.getLogger("gorefer.campaigns.tasks")


def _ladder_fire_at(anchor_at, gap_days_from_anchor: int):
    from datetime import timedelta

    return anchor_at + timedelta(days=gap_days_from_anchor)


def enqueue_campaign_messages(campaign_id: int | None = None) -> dict:
    """Insert one ScheduledCampaignMessage per enabled step, per eligible referrer,
    for every ENABLED campaign (or just `campaign_id` when given). Idempotent.
    """
    campaigns = MessagingCampaign.objects.filter(enabled=True)
    if campaign_id is not None:
        campaigns = campaigns.filter(id=campaign_id)

    created = 0
    considered = 0
    for campaign in campaigns:
        tenant = campaign.tenant
        steps = list(campaign.steps.filter(enabled=True).order_by("order"))
        if not steps:
            continue
        for referrer in services.eligible_referrers(campaign, tenant):
            considered += 1
            anchor_at = referrer.record_created_at
            gap_total = 0
            for step in steps:
                gap_total += step.gap_days_from_previous
                fire_at = _ladder_fire_at(anchor_at, gap_total)
                dkey = (
                    f"{campaign.tenant_id}|{campaign.id}|{referrer.mobile}|"
                    f"{step.id}|{anchor_at.isoformat()}"
                )
                _, was_created = ScheduledCampaignMessage.objects.get_or_create(
                    dedupe_key=dkey,
                    defaults=dict(
                        tenant=tenant,
                        campaign=campaign,
                        step=step,
                        referrer=referrer,
                        client_id=referrer.client_id,
                        mobile=referrer.mobile,
                        language=referrer.language or "en",
                        anchor_at=anchor_at,
                        fire_at=fire_at,
                        status=ScheduledCampaignMessage.STATUS_SCHEDULED,
                    ),
                )
                if was_created:
                    created += 1
    return {"created": created, "considered": considered}


def fire_due_campaign_messages(limit: int = 200) -> dict:
    """Sweep due SCHEDULED campaign messages: lock each, gate, send/cancel/skip/hold."""
    now = timezone.now()
    due_ids = list(
        ScheduledCampaignMessage.objects.filter(
            status=ScheduledCampaignMessage.STATUS_SCHEDULED, fire_at__lte=now
        )
        .order_by("fire_at")
        .values_list("id", flat=True)[:limit]
    )
    counts = {"sent": 0, "cancelled": 0, "skipped": 0, "failed": 0, "held": 0}
    for sid in due_ids:
        try:
            with transaction.atomic():
                scm = (
                    ScheduledCampaignMessage.objects.select_for_update(of=("self",)).get(pk=sid)
                )
                if scm.status != ScheduledCampaignMessage.STATUS_SCHEDULED:
                    continue  # already handled by a concurrent sweep / CRUD edit
                decision, reason = services.evaluate_gate(scm, now)
                _apply(scm, decision, reason, now, counts)
        except Exception:
            logger.warning("campaign message fire failed for id=%s", sid, exc_info=True)
    return counts


def _apply(scm: ScheduledCampaignMessage, decision: str, reason: str, now, counts: dict) -> None:
    if decision == services.DEC_CANCEL:
        scm.status = ScheduledCampaignMessage.STATUS_CANCELLED
        scm.reason = reason
        scm.save(update_fields=["status", "reason", "updated_at"])
        counts["cancelled"] += 1
        return
    if decision == services.DEC_SKIP:
        scm.status = ScheduledCampaignMessage.STATUS_SKIPPED
        scm.reason = reason
        scm.save(update_fields=["status", "reason", "updated_at"])
        counts["skipped"] += 1
        return
    if decision == services.DEC_HOLD:
        # DON'T send now (outside window / budget / quiet hours); defer and stay
        # SCHEDULED so a later sweep retries — never dropped.
        scm.fire_at = services.compute_defer(scm, now)
        scm.reason = reason
        scm.save(update_fields=["fire_at", "reason", "updated_at"])
        counts["held"] += 1
        return

    from .send import send_campaign_message

    # Decision ⑮ — per-RECIPIENT language drives template selection (the referrer's
    # language at enqueue time, `scm.language`), EN fallback via `template_for`. The
    # step's own `language`/`template_name` is an explicit per-step OVERRIDE only
    # (doc precedent: `MessagingCampaignStep.resolved_template_name`'s "overrides the
    # campaign's map when set") — it must never silently outrank the recipient's
    # actual language, or a Hindi-preferring referrer would get an English-authored
    # step's template regardless of their own language.
    template = scm.step.template_name or scm.campaign.template_for(scm.language)
    result = send_campaign_message(
        tenant=scm.tenant, client_id=scm.client_id, mobile=scm.mobile, template=template,
    )
    outcome = result.get("outcome")

    if outcome in ("sent", "would_send"):
        scm.status = ScheduledCampaignMessage.STATUS_SENT
        scm.sent_at = now
        scm.reason = reason
        counts["sent"] += 1
        _emit_funnel_event(scm)
    elif outcome == "failed":
        scm.status = ScheduledCampaignMessage.STATUS_FAILED
        scm.reason = result.get("reason") or "send not accepted"
        counts["failed"] += 1
    else:  # skipped
        scm.status = ScheduledCampaignMessage.STATUS_SKIPPED
        scm.reason = result.get("reason") or "skipped"
        counts["skipped"] += 1
    scm.save(update_fields=["status", "sent_at", "reason", "updated_at"])


def _emit_funnel_event(scm: ScheduledCampaignMessage) -> None:
    """PII-free funnel event (T-051 precedent: no mobile/token in the immutable log)."""
    try:
        Event.objects.create(
            tenant=scm.tenant,
            event_type=vocab.NOTIFICATION,
            source=vocab.SRC_WATI,
            user_type="system",
            metadata={"kind": "messaging_campaign", "campaign": scm.campaign.slug, "step": scm.step_id},
        )
    except Exception:
        logger.warning("campaign funnel event emit failed", exc_info=True)


def run_campaign_engine() -> dict:
    """The single django-q schedule entry point: enqueue then fire, one pass.

    Runs INERT (both stages no-op) when no campaign is ENABLED — `enqueue_campaign_
    messages` only iterates `enabled=True` rows and `fire_due_campaign_messages` has
    no due rows to find when nothing was ever enqueued.
    """
    enqueue_result = enqueue_campaign_messages()
    fire_result = fire_due_campaign_messages()
    return {"enqueue": enqueue_result, "fire": fire_result}
