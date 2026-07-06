"""Zoho status webhook — the SOLE entry point for conversion mutation (M6).

Interim auth (R2): a static shared key + a Zoho server-IP allowlist. The HMAC
"wax-seal" (signature + timestamp + nonce) is deferred to DF-2. A failed record is
retried; on repeated failure it lands in the dead-letter tray (never dropped).

Guardrail #2: conversion/account status is set ONLY here (via ingest_conversion) —
never by an internal business write.
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.integrations.models import ZohoDeadLetter, ZohoSyncWatermark
from apps.tenants.resolve import get_current_tenant

from .ingest import DuplicateDelivery, ingest_conversion

logger = logging.getLogger("gorefer.zoho.webhook")


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def authenticate(request) -> bool:
    """Static key + IP allowlist. Both must pass (allowlist empty = allow any — dev)."""
    expected = getattr(settings, "ZOHO_WEBHOOK_KEY", "")
    provided = request.headers.get("X-Zoho-Webhook-Key", "")
    if not expected or provided != expected:
        return False
    allowlist = [ip for ip in getattr(settings, "ZOHO_WEBHOOK_IP_ALLOWLIST", "").split(",") if ip]
    if allowlist and _client_ip(request) not in allowlist:
        return False
    return True


def process_webhook(request, payload: dict) -> dict:
    """Auth + ingest one Zoho status update. Returns a small result dict.

    On ingest failure the record is parked in the dead-letter tray (retriable),
    never lost. Advances the watermark on success.
    """
    tenant = get_current_tenant(request)
    try:
        conversion = ingest_conversion(tenant=tenant, payload=payload)
    except DuplicateDelivery:
        return {"status": "duplicate", "applied": False}
    except Exception as exc:  # park, never drop
        logger.exception("zoho ingest failed — dead-lettering")
        ZohoDeadLetter.objects.create(
            tenant=tenant, dedupe_key=payload.get("event_id", ""), payload=payload, error=str(exc)
        )
        return {"status": "dead_lettered", "applied": False}

    # Advance the watermark (resume point) + mark sync fresh.
    _advance_watermark(tenant, payload.get("event_id", ""))
    _mark_sync_fresh(tenant)
    return {"status": "ok", "applied": True, "conversion_id": conversion.id if conversion else None}


def _advance_watermark(tenant, event_id: str):
    from django.utils import timezone

    wm, _ = ZohoSyncWatermark.objects.get_or_create(tenant=tenant)
    wm.last_event_id = event_id or wm.last_event_id
    wm.last_processed_at = timezone.now()
    wm.save(update_fields=["last_event_id", "last_processed_at"])


def _mark_sync_fresh(tenant):
    """Light up the M4 SyncHealth scaffold (#19)."""
    from django.utils import timezone

    from apps.events.models import SyncHealth

    row, _ = SyncHealth.objects.get_or_create(tenant=tenant)
    row.last_successful_zoho_sync_at = timezone.now()
    row.zoho_state = "healthy"
    row.save(update_fields=["last_successful_zoho_sync_at", "zoho_state", "updated_at"])
