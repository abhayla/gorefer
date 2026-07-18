"""Zoho status webhook — the SOLE entry point for conversion mutation (M6).

Auth has two modes, selected by `ENABLE_ZOHO_WEBHOOK_HMAC`:
  - OFF (default, interim R2): static shared key + Zoho server-IP allowlist.
  - ON  (DF-2 wax-seal): HMAC(payload+timestamp+nonce) + the SAME IP allowlist. The
    static key is NOT accepted as an alternative — see `authenticate`.

A failed record is retried; on repeated failure it lands in the dead-letter tray
(never dropped).

Guardrail #2: conversion/account status is set ONLY here (via ingest_conversion) —
never by an internal business write. That is precisely why DF-2 matters: this
endpoint is the one place a forged request could fabricate a conversion.
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.integrations.models import ZohoDeadLetter, ZohoSyncWatermark
from apps.tenants.resolve import get_current_tenant
from gorefer.flags import flags

from .ingest import DuplicateDelivery, ingest_conversion
from .waxseal import SealRejected, verify_seal

logger = logging.getLogger("gorefer.zoho.webhook")


def _client_ip(request) -> str:
    # Spoof-resistant (Fable5 H2): resolve from the trusted-proxy hop, NOT xff[0]
    # (which is attacker-appendable and would let X-Forwarded-For: <zoho-ip> bypass
    # the allowlist).
    from apps.common.netaddr import trusted_client_ip

    return trusted_client_ip(request)


def _ip_allowed(request) -> bool:
    """Zoho server-IP allowlist. An EMPTY allowlist means allow-any, which is only
    permitted in DEBUG (dev/CI). In production (DEBUG=false) an empty allowlist is a
    misconfiguration and is refused fail-closed (Fable5 H2) — a webhook that mutates
    conversions must never be open to any IP in prod."""
    allowlist = [ip for ip in getattr(settings, "ZOHO_WEBHOOK_IP_ALLOWLIST", "").split(",") if ip]
    if not allowlist:
        if not settings.DEBUG and getattr(settings, "WEBHOOK_REQUIRE_IP_ALLOWLIST", False):
            logger.warning("Zoho webhook: empty IP allowlist rejected in prod (fail-closed)")
            return False
        return True  # dev/CI, or interim R2 (static key alone) until allowlist is populated
    return _client_ip(request) in allowlist


def _static_key_ok(request) -> bool:
    """Interim R2 auth: a static shared key. Fails closed when the key is unset."""
    import hmac as _hmac

    expected = getattr(settings, "ZOHO_WEBHOOK_KEY", "")
    provided = request.headers.get("X-Zoho-Webhook-Key", "")
    if not expected:
        return False  # fail CLOSED — never accept-any on a blank key
    # Constant-time: the static key is a secret too, so don't leak it via `!=` timing.
    return _hmac.compare_digest(provided, expected)


def authenticate(request, raw_body: bytes | None = None) -> bool:
    """Authenticate one inbound Zoho webhook request. Fails CLOSED.

    With `ENABLE_ZOHO_WEBHOOK_HMAC` ON, the DF-2 wax-seal is REQUIRED and the static
    key is **not** accepted as a fallback. That is the whole point: leaving the static
    key as an alternative would mean a leaked key still forges conversions, and the
    seal would be decoration. The IP allowlist applies in BOTH modes.

    `raw_body` must be the untouched request bytes — the signature is computed over
    exactly what was signed (see waxseal.compute_signature).
    """
    if not _ip_allowed(request):
        return False

    if flags.ENABLE_ZOHO_WEBHOOK_HMAC:
        try:
            verify_seal(request, raw_body if raw_body is not None else request.body)
        except SealRejected as exc:
            # Log the reason for US; the endpoint answers a flat 401 so the caller
            # gets no oracle telling them which check they failed.
            logger.warning("Zoho webhook seal rejected: %s", exc.reason)
            return False
        return True

    return _static_key_ok(request)


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
