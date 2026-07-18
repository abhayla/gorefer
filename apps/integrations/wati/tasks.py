"""Background tasks (django-q) for WATI sends + terminal-status verification (M5).

send_notification():
  1. submit the template via the adapter (ACCEPTED — not delivery),
  2. verify the TERMINAL status (delivered/read/failed) — the ONLY proof of
     delivery (doc-08 A3); NEVER trust the HTTP-200/accepted ack,
  3. record the terminal status + Meta error classification on the Notification,
  4. emit a source-tagged `notification` event so the funnel can start at
     "delivered" (Gap 12) — the ~33% WATI leak becomes visible, not hidden.

In sync/demo mode (Q_CLUSTER sync=True, ENABLE_WATI_SEND=false) this runs inline
against the log-only adapter, so the whole flow is testable offline.
"""
from __future__ import annotations

import logging

from django_q.tasks import async_task

from apps.events import vocab
from apps.events.models import Event
from apps.integrations.models import Notification
from apps.integrations.wati import status as st
from apps.integrations.wati.adapter import get_wati_adapter

logger = logging.getLogger("gorefer.wati.tasks")


def enqueue_send(notification_id: int) -> None:
    """Enqueue the send task (runs inline when Q_CLUSTER sync=True)."""
    async_task("apps.integrations.wati.tasks.send_notification", notification_id)


def send_notification(notification_id: int) -> str:
    """Send + verify terminal delivery status for one notification. Returns status."""
    n = Notification.objects.filter(id=notification_id).first()
    if n is None or n.status not in {"queued"}:
        return "noop"

    adapter = get_wati_adapter()
    # Stamp which adapter handled this send, so a demo/log-only "delivery" is always
    # distinguishable from a real Wati delivery (Fable5 M7).
    n.adapter_kind = getattr(adapter, "kind", "")
    result = adapter.send_template(
        to=n.recipient_mobile,
        template=n.template,
        params={"role": n.recipient_role, "template_params": n.template_params or []},
    )

    # Fail-closed allowlist blocked this recipient — NOTHING was sent. Record it as a
    # skip with a reason (not a delivery failure): the funnel must show it did not go
    # AND that it was suppressed by the gate, never mistaken for a Meta failure.
    if result.raw_status == st.STATUS_BLOCKED:
        n.status = "skipped"
        n.skip_reason = "recipient not in WATI allowlist (fail-closed)"
        n.save(update_fields=["status", "skip_reason", "adapter_kind", "updated_at"])
        return st.STATUS_BLOCKED

    # HTTP 200 / accepted is NOT delivery — record it, then verify the terminal status.
    n.provider_message_id = result.provider_message_id or ""
    n.status = st.STATUS_ACCEPTED
    n.save(update_fields=["provider_message_id", "status", "adapter_kind", "updated_at"])

    if not result.accepted:
        _finalize(n, st.STATUS_FAILED, meta_error_code=None)
        return st.STATUS_FAILED

    # The Wati ack has no message id, so terminal status is reconciled by mobile +
    # template (getMessages), not by an id. If it can't be reconciled yet the adapter
    # honestly returns the non-terminal 'accepted' — we then leave the row ACCEPTED
    # (not fabricated as delivered); a later reconcile pass moves it terminal.
    delivery = adapter.get_message_status(
        provider_message_id=n.provider_message_id,
        recipient_mobile=n.recipient_mobile,
        template=n.template,
    )
    if delivery.status == st.STATUS_ACCEPTED:
        # No terminal proof available — keep it at ACCEPTED, don't finalize.
        return st.STATUS_ACCEPTED
    _finalize(n, delivery.status, meta_error_code=delivery.meta_error_code)
    return delivery.status


def _finalize(n: Notification, terminal_status: str, *, meta_error_code):
    """Record the terminal status + classification; emit the funnel notification event."""
    n.status = terminal_status
    if terminal_status == st.STATUS_FAILED:
        n.meta_error_code = meta_error_code
        n.failure_classification = st.classify_failure(meta_error_code)
    n.save(update_fields=["status", "meta_error_code", "failure_classification", "updated_at"])

    # Funnel can start at "delivered": a source-tagged notification event carrying
    # the terminal status in metadata (no PII).
    Event.objects.create(
        tenant=n.tenant,
        event_type=vocab.NOTIFICATION,
        source=vocab.SRC_WATI,
        referral=n.referral,
        user_type="system",
        metadata={"role": n.recipient_role, "delivery_status": terminal_status},
    )


# How long a row may sit at ACCEPTED before the reconcile sweep re-polls it, and how
# old is "too old" (give up and mark it a delivery-status failure so the funnel stops
# hiding it). Both in minutes.
RECONCILE_MIN_AGE_MINUTES = 3
RECONCILE_EXPIRE_MINUTES = 24 * 60  # 24h — a delivery that never went terminal is stale


def reconcile_pending_deliveries(limit: int = 200) -> dict:
    """Re-poll WATI terminal status for notifications stranded at ACCEPTED (Fable5 H4).

    `send_notification` reads terminal status *immediately* after the send; any delivery
    that isn't terminal in that instant is left at ACCEPTED with no other path to move it
    (there is no WATI delivery webhook). Without this sweep those rows stay ACCEPTED
    forever and the funnel under-reports real delivered/failed outcomes. This runs on a
    schedule (setup_schedules): for each ACCEPTED row older than RECONCILE_MIN_AGE, re-ask
    getMessages; finalize on a terminal status, or expire very old ones to FAILED so a
    silently-lost send is visible, not hidden.
    """
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.now()
    min_age_cutoff = now - timedelta(minutes=RECONCILE_MIN_AGE_MINUTES)
    expire_cutoff = now - timedelta(minutes=RECONCILE_EXPIRE_MINUTES)

    pending = (
        Notification.objects.filter(status=st.STATUS_ACCEPTED, updated_at__lte=min_age_cutoff)
        .order_by("updated_at")[:limit]
    )
    finalized = expired = still_pending = 0
    for n in pending:
        # Demo rows never reach ACCEPTED-and-stuck (log-only finalizes immediately), so
        # this path is the live adapter. Build it directly (not via the flag) so a
        # reconcile sweep still works if the flag was toggled off after the send.
        adapter = _adapter_for_reconcile(n)
        if adapter is None:
            still_pending += 1
            continue
        delivery = adapter.get_message_status(
            provider_message_id=n.provider_message_id,
            recipient_mobile=n.recipient_mobile,
            template=n.template,
        )
        if delivery.status in st.TERMINAL_STATUSES:
            _finalize(n, delivery.status, meta_error_code=delivery.meta_error_code)
            finalized += 1
        elif n.updated_at <= expire_cutoff:
            # Too old and still no terminal proof — record a delivery-status failure so
            # the leak is visible (never silently 'accepted' forever).
            _finalize(n, st.STATUS_FAILED, meta_error_code=None)
            n.failure_classification = "no terminal status within reconcile window"
            n.save(update_fields=["failure_classification", "updated_at"])
            expired += 1
        else:
            still_pending += 1
    return {"finalized": finalized, "expired": expired, "still_pending": still_pending}


def _adapter_for_reconcile(n: Notification):
    """Return a LIVE adapter to re-poll a real send, or None if config is missing.

    A row stuck at ACCEPTED came from the live adapter (log-only finalizes at once). We
    construct the live adapter directly so reconciliation isn't gated on the current
    flag state — but if live config is absent we skip (can't reconcile), never crash.
    """
    from apps.integrations.wati.adapter import LiveWatiAdapter

    try:
        return LiveWatiAdapter()
    except RuntimeError:
        return None
