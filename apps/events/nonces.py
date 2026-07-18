"""One-time nonce service for the beacon + name-reveal gate (ADR-021).

A nonce is minted when a human click is logged and handed to the page JS. The
beacon consumes it (marking the click confirmed-human); the name-reveal endpoint
requires the SAME fresh, unused nonce. Single-use + short TTL make id->name
enumeration impractical (paired with rate-limiting + bot filtering at the view).
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.utils import timezone

from .models import ClickNonce

NONCE_TTL = timedelta(minutes=30)


def mint_nonce(*, tenant, referral, visitor_id: str, client_id: str) -> str:
    token = secrets.token_urlsafe(24)
    ClickNonce.objects.create(
        tenant=tenant,
        nonce=token,
        visitor_id=visitor_id or "",
        referral=referral,
        client_id=client_id or "",
        expires_at=timezone.now() + NONCE_TTL,
    )
    return token


def _live_nonce(nonce: str, visitor_id: str) -> ClickNonce | None:
    if not nonce:
        return None
    row = ClickNonce.objects.filter(nonce=nonce).first()
    if row is None or row.consumed_at is not None:
        return None
    if row.expires_at <= timezone.now():
        return None
    if visitor_id and row.visitor_id and row.visitor_id != visitor_id:
        return None
    return row


def consume_nonce(*, nonce: str, visitor_id: str) -> ClickNonce | None:
    """Validate + consume a nonce (single-use). Returns the row or None if invalid."""
    row = _live_nonce(nonce, visitor_id)
    if row is None:
        return None
    row.consumed_at = timezone.now()
    row.save(update_fields=["consumed_at"])
    return row


def peek_nonce(*, nonce: str, visitor_id: str) -> ClickNonce | None:
    """Validate WITHOUT consuming (name-reveal reuses the beacon's nonce)."""
    return _live_nonce(nonce, visitor_id)


# Retain expired/consumed nonces a little past their TTL for audit, then purge.
NONCE_PURGE_GRACE = timedelta(hours=1)


def purge_expired_nonces() -> int:
    """Delete ClickNonce rows well past their usefulness (Fable5 H3).

    Every /r/{id} hit mints a nonce (redirect_service), so the table grows unbounded
    under crawling without this sweep — the Zoho wax-seal nonces had a purge; these
    did not. Only rows already expired (or consumed) beyond a grace window are removed,
    so an in-flight beacon/name-reveal nonce is never yanked. Scheduled hourly.
    """
    cutoff = timezone.now() - NONCE_PURGE_GRACE
    deleted, _ = ClickNonce.objects.filter(expires_at__lt=cutoff).delete()
    return deleted
