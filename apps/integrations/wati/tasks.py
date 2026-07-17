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
    result = adapter.send_template(
        to=n.recipient_mobile,
        template=n.template,
        params={"role": n.recipient_role, "template_params": n.template_params or []},
    )
    # HTTP 200 / accepted is NOT delivery — record it, then verify the terminal status.
    n.provider_message_id = result.provider_message_id or ""
    n.status = st.STATUS_ACCEPTED
    n.save(update_fields=["provider_message_id", "status", "updated_at"])

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
