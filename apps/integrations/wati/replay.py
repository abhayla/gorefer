"""Wati webhook replay protection (T-048).

WHY THIS EXISTS
---------------
The Zoho webhook is sealed (HMAC + timestamp freshness + one-time nonce), so a captured
request cannot be re-sent. The Wati webhook has no such option: **Wati's sender is fixed
and carries exactly one credential, the `?token=` query param** — it cannot attach a
signature, a timestamp header, or a nonce (verified against the live tenant's webhook
configuration; see `Wati-GoRefer/Wati-Integration-Contract.md` §7). A captured request
therefore stays valid forever, and anyone holding it can re-POST it indefinitely.

The concrete harm that motivated this is not hypothetical: `/api/wati/inbound` opens the
24h WhatsApp session window and, on a FRESH open, enqueues the referrer's entire nudge
cadence. Replaying one captured inbound a day later re-opens the window and re-fires the
whole cadence at that person — a real message-spam primitive, on demand.

THE IDENTITY IS WATI'S, NOT OURS
--------------------------------
Because we cannot ask Wati for a nonce, dedupe is keyed on the identity Wati already puts
in the body. Every key below is one this integration has actually observed on Wati
message payloads (`getMessages` items and the "New Contact Message" webhook), not an
invented header:

    id                  the Wati message id (the primary identity)
    whatsappMessageId   Meta's message id, when present
    conversationId      only as part of a composite, never alone

A payload carrying none of these falls back to a SHA-256 of the exact request bytes, so a
byte-identical replay is still caught. That fallback is deliberately conservative: it
refuses only a true byte-for-byte repeat, never two genuinely distinct events.
"""
from __future__ import annotations

import hashlib
import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger("gorefer.wati.replay")

#: Keys Wati actually sends that identify a single event. Ordered most-specific first.
#: Do NOT add a key here without a captured payload showing Wati emits it.
IDENTITY_KEYS = ("id", "whatsappMessageId")

#: Receipts only need to outlive the harm window. The worst a replay does is re-open a
#: 24h WhatsApp session window / re-fire a cadence, so a week is comfortably beyond it
#: while keeping the table small. Structural security posture — deliberately NOT a
#: tenant config knob (a tenant must not be able to shorten its own replay window).
RECEIPT_RETENTION_DAYS = 7


def event_key(endpoint: str, raw_body: bytes, payload: dict | None) -> str:
    """The dedupe identity for one Wati webhook delivery.

    Returns `"<key>=<value>"` when Wati gave us an id, else `"sha256=<digest>"` of the
    exact bytes. The `endpoint` is kept OUT of the key and stored in its own column, so
    the same message id arriving at two different endpoints is two distinct events.
    """
    if isinstance(payload, dict):
        for key in IDENTITY_KEYS:
            value = payload.get(key)
            if value not in (None, "", [], {}):
                # Bounded: an oversized/garbage id must never overflow the column.
                return f"{key}={str(value)[:150]}"
    return "sha256=" + hashlib.sha256(raw_body or b"").hexdigest()


def claim_event(endpoint: str, key: str) -> bool:
    """Claim this event exactly once. True = first sight, False = replay.

    The claim is a UNIQUE-constrained INSERT, so two concurrent replays cannot both win:
    the database, not application logic, decides. Wrapped in an atomic block because a
    caught IntegrityError otherwise poisons the surrounding transaction on Postgres.
    """
    from apps.integrations.models import WatiWebhookReceipt

    try:
        with transaction.atomic():
            WatiWebhookReceipt.objects.create(endpoint=endpoint, event_key=key)
        return True
    except IntegrityError:
        logger.warning("Wati webhook replay refused: endpoint=%s key=%s", endpoint, key)
        return False


def purge_expired_receipts() -> int:
    """Delete receipts past the retention window. Returns how many were removed.

    Safe to purge: a receipt older than the window can no longer prevent meaningful harm,
    because the 24h session window a replay would target has long closed.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.integrations.models import WatiWebhookReceipt

    cutoff = timezone.now() - timedelta(days=RECEIPT_RETENTION_DAYS)
    deleted, _ = WatiWebhookReceipt.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("Purged %d expired Wati webhook receipt(s)", deleted)
    return deleted
