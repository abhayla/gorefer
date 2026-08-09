"""Boundary task-level facade (ADR-045). Thin delegation only — no logic here.

Domain code calls these instead of reaching into `apps.integrations.wati.*` /
`apps.integrations.zoho.*` by name. Each function/constant is a pure pass-through to
the existing implementation, imported lazily (inside the function body) to avoid
app-loading cycles.
"""
from __future__ import annotations

import contextlib

from apps.integrations.zoho.tasks import MAX_SYNC_ATTEMPTS

__all__ = [
    "queue_lead_notifications",
    "enqueue_lead_upsert",
    "record_inbound",
    "ingest_conversion",
    "observe_zoho_upsert_action",
    "enqueue_referrer_congrats",
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


def enqueue_referrer_congrats(*, referral_id: int, conversion_id: int) -> None:
    """Enqueue the one-time referrer conversion-congrats send (T-058, P-01/Gap 5).
    See `congrats.enqueue_referrer_congrats`.

    Best-effort: any failure to enqueue is caught and logged, never raised. This is
    called from `zoho.ingest` via `transaction.on_commit` — the conversion write it
    rides on must gain NO new failure mode from a downstream notification.
    """
    try:
        from apps.integrations.congrats import enqueue_referrer_congrats as _impl

        _impl(referral_id=referral_id, conversion_id=conversion_id)
    except Exception:
        import logging

        logging.getLogger("gorefer.integrations.congrats").warning(
            "referrer congrats enqueue failed: referral=%s conversion=%s",
            referral_id, conversion_id, exc_info=True,
        )


@contextlib.contextmanager
def observe_zoho_upsert_action(sink: dict):
    """Diagnostic-only: capture the Zoho adapter's insert/update verdict for any
    `upsert_lead` call made within the block, without changing what it does.

    `LeadWriteResult.action` is Zoho's own server-side dedup verdict but is only
    logged, never persisted on the Lead. Wraps the selected adapter's `upsert_lead`
    for the duration of the block: it forwards the call untouched and copies
    `action`/`zoho_lead_id` into `sink`. Used by `golive_smoke`; production paths
    are unaffected — the wrap is installed and removed inside this context.
    """
    from apps.integrations.zoho import tasks as zoho_tasks

    original = zoho_tasks.get_zoho_adapter

    def _wrapped_get_adapter(*a, **kw):
        adapter = original(*a, **kw)
        inner = adapter.upsert_lead

        def _upsert(*args, **kwargs):
            result = inner(*args, **kwargs)
            sink["action"] = getattr(result, "action", None)
            sink["zoho_lead_id"] = getattr(result, "zoho_lead_id", None)
            return result

        adapter.upsert_lead = _upsert
        return adapter

    zoho_tasks.get_zoho_adapter = _wrapped_get_adapter
    try:
        yield sink
    finally:
        zoho_tasks.get_zoho_adapter = original


