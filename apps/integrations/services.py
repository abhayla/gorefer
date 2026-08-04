"""Boundary task-level facade (ADR-045). Thin delegation only — no logic here.

Domain code calls these instead of reaching into `apps.integrations.wati.*` /
`apps.integrations.zoho.*` by name. Each function/constant is a pure pass-through to
the existing implementation, imported lazily (inside the function body) to avoid
app-loading cycles.
"""
from __future__ import annotations

from apps.integrations.zoho.tasks import MAX_SYNC_ATTEMPTS

__all__ = [
    "queue_lead_notifications",
    "enqueue_lead_upsert",
    "record_inbound",
    "ingest_conversion",
    "MAX_SYNC_ATTEMPTS",
]


def queue_lead_notifications(*, tenant, referral, prospect, client_id: str) -> list[int]:
    """Create + enqueue the lead-time WATI notifications. See `wati.notify`."""
    from apps.integrations.wati.notify import queue_lead_notifications as _impl

    return _impl(tenant=tenant, referral=referral, prospect=prospect, client_id=client_id)


def enqueue_lead_upsert(lead_id: int) -> None:
    """Enqueue the Zoho upsert for one lead. See `zoho.tasks.enqueue_upsert`."""
    from apps.integrations.zoho.tasks import enqueue_upsert

    return enqueue_upsert(lead_id)


def record_inbound(tenant, mobile: str, at=None, *, prospect_id: int | None = None,
                   source_event: str = "wati_inbound", pref_lang: str = "en") -> dict:
    """Stamp a WATI inbound-window event. See `wati.webhook.record_inbound`."""
    from apps.integrations.wati.webhook import record_inbound as _impl

    return _impl(
        tenant, mobile, at,
        prospect_id=prospect_id, source_event=source_event, pref_lang=pref_lang,
    )


def ingest_conversion(*, tenant, payload: dict):
    """Ingest one Zoho conversion/status update. See `zoho.ingest.ingest_conversion`.

    The single sanctioned conversion writer (guardrail #2) — unchanged by this facade.
    """
    from apps.integrations.zoho.ingest import ingest_conversion as _impl

    return _impl(tenant=tenant, payload=payload)


