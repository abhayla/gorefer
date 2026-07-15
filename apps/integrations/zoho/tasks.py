"""Background tasks (django-q) for the Zoho WRITE leg — retry + backfill.

Why this exists: the lead is saved locally FIRST (capture-first, 06-API §5.3), and
the Zoho upsert is a mirror. Before this module a Zoho outage logged the failure and
left the lead local-only forever — Ashok would never see it. That is silent data
loss from the operator's point of view, even though nothing was technically dropped.

The flow:
  1. capture_lead() saves locally, then on_commit -> enqueue_upsert(lead_id).
     The form submit NEVER waits on Zoho (also removes Zoho latency from the request).
  2. upsert_lead_task() attempts the upsert:
       success -> synced + zoho_lead_id + zoho_synced_at
       failure -> attempts += 1; pending (retry later) or failed (attempts exhausted)
  3. backfill_unsynced() (scheduled) re-enqueues pending|failed leads with
     attempts < max, oldest first — so anything stranded during an outage lands
     once Zoho recovers.

Idempotency is structural, not bookkeeping: the write is an upsert keyed on the
bare-10-digit mobile, so replaying a task can only ever UPDATE the same Zoho lead —
it can never twin. That is what makes an aggressive retry safe.

Flag-off/demo: get_zoho_adapter() returns the log-only adapter, so the task runs
end-to-end offline with zero network. In sync mode (Q_CLUSTER sync=True, the
dev/CI/demo default) it executes inline.

Guardrail #2: this is the WRITE leg. It NEVER sets account/conversion status —
that comes only from the Zoho inbound webhook.
"""
from __future__ import annotations

import logging

from django.utils import timezone
from django_q.tasks import async_task

from apps.integrations.zoho.adapter import get_zoho_adapter, gorefer_reference_for

logger = logging.getLogger("gorefer.zoho.tasks")

# Bounded retry: stop re-attempting a lead that keeps failing, so a permanently
# broken record (e.g. a field Zoho rejects) cannot spin forever. It stays `failed`
# and VISIBLE in the admin rather than silently retrying into the void.
MAX_SYNC_ATTEMPTS = 5

# How many stranded leads one sweep re-enqueues. Bounded so a long outage's backlog
# drains steadily instead of stampeding Zoho the moment it recovers.
BACKFILL_BATCH_SIZE = 50


def enqueue_upsert(lead_id: int) -> None:
    """Enqueue the Zoho upsert for one lead (runs inline when Q_CLUSTER sync=True)."""
    async_task("apps.integrations.zoho.tasks.upsert_lead_task", lead_id)


def upsert_lead_task(lead_id: int) -> str:
    """Upsert one lead into Zoho; record sync state. Returns the resulting status.

    Safe to replay: the upsert dedups server-side on the bare-10-digit mobile.
    """
    from apps.referrals.models import Lead

    lead = Lead.objects.filter(id=lead_id, deleted_at__isnull=True).select_related(
        "prospect", "referral"
    ).first()
    if lead is None:
        return "noop"  # deleted/erased (DPDP) between enqueue and run
    if lead.zoho_sync_status == Lead.SYNC_SYNCED:
        return "noop"  # already mirrored — don't re-write on a duplicate enqueue

    prospect, referral = lead.prospect, lead.referral
    adapter = get_zoho_adapter()
    gref = gorefer_reference_for(referral)

    try:
        result = adapter.upsert_lead(
            payload={
                "name": prospect.name,
                "mobile": prospect.mobile,
                "email": prospect.email,
                "city": prospect.city,
                "referred_by": _referrer_client_id(referral),
            },
            gorefer_reference=gref,
        )
    except Exception as exc:
        return _record_failure(lead, exc)

    lead.zoho_sync_status = Lead.SYNC_SYNCED
    lead.zoho_synced_at = timezone.now()
    lead.zoho_last_error = ""
    if result.zoho_lead_id:
        lead.zoho_lead_id = result.zoho_lead_id
    if result.gorefer_reference:
        lead.gorefer_reference = result.gorefer_reference
    lead.save(update_fields=[
        "zoho_sync_status", "zoho_synced_at", "zoho_last_error",
        "zoho_lead_id", "gorefer_reference", "updated_at",
    ])
    logger.info(
        "Zoho sync ok: lead=%s action=%s zoho_lead_id=%s", lead.pk, result.action, result.zoho_lead_id
    )
    return Lead.SYNC_SYNCED


def _record_failure(lead, exc: Exception) -> str:
    """Increment attempts, record the error, and park the lead pending|failed."""
    from apps.referrals.models import Lead

    lead.zoho_sync_attempts += 1
    # Store the error text (truncated) for operator triage. It is an integration
    # error, not PII, and lives on the erasable Lead — never in the event log.
    lead.zoho_last_error = f"{type(exc).__name__}: {exc}"[:500]
    lead.zoho_sync_status = (
        Lead.SYNC_FAILED if lead.zoho_sync_attempts >= MAX_SYNC_ATTEMPTS else Lead.SYNC_PENDING
    )
    lead.save(update_fields=[
        "zoho_sync_attempts", "zoho_last_error", "zoho_sync_status", "updated_at",
    ])
    logger.warning(
        "Zoho sync failed: lead=%s attempt=%s/%s status=%s err=%s",
        lead.pk, lead.zoho_sync_attempts, MAX_SYNC_ATTEMPTS, lead.zoho_sync_status, exc,
    )
    return lead.zoho_sync_status


def backfill_unsynced() -> int:
    """Re-enqueue leads that never reached Zoho. Returns how many were enqueued.

    Scheduled (see `setup_schedules`). Picks pending|failed leads with attempts
    below the cap, OLDEST FIRST so the earliest-stranded lead is worked first, and
    bounded per sweep so a recovered Zoho isn't stampeded. Exhausted leads are left
    alone deliberately — they need a human, and the admin surfaces them.
    """
    from apps.referrals.models import Lead

    stranded = (
        Lead.objects.filter(
            zoho_sync_status__in=[Lead.SYNC_PENDING, Lead.SYNC_FAILED],
            zoho_sync_attempts__lt=MAX_SYNC_ATTEMPTS,
            deleted_at__isnull=True,
        )
        .order_by("created_at")[:BACKFILL_BATCH_SIZE]
    )
    lead_ids = list(stranded.values_list("id", flat=True))
    for lead_id in lead_ids:
        enqueue_upsert(lead_id)
    if lead_ids:
        logger.info("Zoho backfill: re-enqueued %d unsynced lead(s)", len(lead_ids))
    return len(lead_ids)


def _referrer_client_id(referral) -> str:
    identity = getattr(referral, "referral_identity", None)
    return identity.client_id if identity is not None else ""
