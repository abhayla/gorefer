"""Resolve a referrer's ON-FILE OTP channel from their Zerodha client_id (Q-M-OTP).

S2-03 §15 Path A is emphatic: OTP goes to the channel ALREADY ON RECORD for the
client_id — NEVER a number the user types (the client_id is public; a typed number
would let anyone hijack a referrer's analytics). So the login flow resolves the
recipient here and the user never supplies it.

Sources, most-authoritative first:
  1. `Customer` (Abhay's own customers, `client_id -> mobile`) — present today.
  2. Zoho Contact/Lead (`ClientId -> Mobile/Phone`, verified live 2026-07-11,
     e.g. QPJ023 -> 9335138774) via the M9 Zoho READ adapter — gated by
     ENABLE_ZOHO_READ. **OPEN (see COORDINATION Q-M-OTP-2): the exact Zoho-read
     module/method for the client_id->contact lookup is stubbed here** and returns
     "" until wired, so the flow falls back cleanly (no channel -> caller shows the
     Path-B assisted route). No number is ever guessed.

Returns a canonical 91-prefixed phone or "" (unknown -> assisted / Path B).
"""
from __future__ import annotations

import logging

from apps.common.phone import normalize_phone
from gorefer.flags import flags

logger = logging.getLogger("gorefer.otp.recipient")


def resolve_onfile_recipient(tenant, identity: str) -> str:
    """Return the canonical on-file phone for a client_id, or "" if none known."""
    client_id = (identity or "").strip()
    if not client_id:
        return ""

    phone = _from_customer(tenant, client_id)
    if phone:
        return phone

    phone = _from_zoho(tenant, client_id)
    if phone:
        return phone

    logger.info("OTP recipient unknown for client_id=%s — fall back to assisted (Path B)", client_id)
    return ""


def _from_customer(tenant, client_id: str) -> str:
    from apps.referrals.models import Customer

    customer = (
        Customer.objects.filter(tenant=tenant, client_id=client_id, deleted_at__isnull=True)
        .exclude(mobile="")
        .first()
    )
    return normalize_phone(customer.mobile) if customer else ""


def _from_zoho(tenant, client_id: str) -> str:
    """Zoho on-file channel lookup — STUB (Q-M-OTP-2 OPEN).

    Wire this to the M9 Zoho READ adapter's client_id->Contact lookup once the exact
    module/method is confirmed. Until then, return "" so the flow falls back to the
    assisted path (never guesses a number). Gated by ENABLE_ZOHO_READ.
    """
    if not flags.ENABLE_ZOHO_READ:
        return ""
    # TODO(Q-M-OTP-2): call the M9 Zoho READ adapter, read Contact.Mobile/Phone for
    # ClientId == client_id, normalize_phone(...) and return it.
    logger.info("Zoho on-file OTP lookup not yet wired (Q-M-OTP-2); client_id=%s", client_id)
    return ""
