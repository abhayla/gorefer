"""Resolve a referrer's ON-FILE OTP channel from their Zerodha client_id (Q-M-OTP).

S2-03 §15 Path A is emphatic: OTP goes to the channel ALREADY ON RECORD for the
client_id — NEVER a number the user types (the client_id is public; a typed number
would let anyone hijack a referrer's analytics). So the login flow resolves the
recipient here and the user never supplies it.

Sources, most-authoritative first:
  1. `Customer` (Abhay's own customers, `client_id -> mobile`) — present today.
  2. Zoho Contact/Lead (`ClientId -> Mobile/Phone`, verified live 2026-07-11,
     e.g. QPJ023 -> 9999900004) via the M9 Zoho READ adapter — gated by
     ENABLE_ZOHO_READ. **OPEN (see COORDINATION Q-M-OTP-2): the exact Zoho-read
     module/method for the client_id->contact lookup is stubbed here** and returns
     "" until wired, so the flow falls back cleanly (no channel -> caller shows the
     Path-B assisted route). No number is ever guessed.

Returns a canonical 91-prefixed phone or "" (unknown -> assisted / Path B).
"""
from __future__ import annotations

import logging

from apps.common.phone import normalize_phone

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


def resolve_onfile_email(tenant, identity: str) -> str:
    """Return the canonical on-file EMAIL for a client_id, or "" if none known (T-078).

    The exact mirror of `resolve_onfile_recipient` above, for the second (email) OTP
    leg: same two sources, same order, same fail-closed contract. A user-supplied
    address NEVER reaches this function — the login view resolves the address here
    from the client_id alone, so a typed email cannot redirect anyone's OTP.

    "" means "no email on file" -> the email leg skips cleanly and WhatsApp still
    carries the code. An address is never guessed or derived.
    """
    client_id = (identity or "").strip()
    if not client_id:
        return ""

    email = _email_from_customer(tenant, client_id)
    if email:
        return email

    email = _email_from_zoho(tenant, client_id)
    if email:
        return email

    logger.info("OTP on-file email unknown for client_id=%s — email leg will skip", client_id)
    return ""


def _email_from_customer(tenant, client_id: str) -> str:
    from apps.referrals.models import Customer

    customer = (
        Customer.objects.for_tenant(tenant).filter(client_id=client_id, deleted_at__isnull=True)
        .exclude(email="")
        .first()
    )
    return (customer.email or "").strip().lower() if customer else ""


def _email_from_zoho(tenant, client_id: str) -> str:
    """Zoho Contact `Email` via the M9 READ adapter (already in the field set).

    Gated by the RESOLVED ENABLE_ZOHO_READ exactly like the phone lookup, and any
    failure degrades to "" — a Zoho outage must never 500 a login.
    """
    from apps.config.integration_flags import ENABLE_ZOHO_READ, resolve_flag

    if not resolve_flag(ENABLE_ZOHO_READ, tenant_id=getattr(tenant, "id", None)):
        return ""
    from apps.integrations.ports import get_crm_read_port

    try:
        contact = get_crm_read_port().fetch_contact_by_client_id(client_id=client_id)
    except Exception:  # noqa: BLE001 — degrade, never 500 a login
        logger.warning(
            "Zoho on-file email lookup failed for client_id=%s — degrading", client_id,
            exc_info=True,
        )
        return ""
    if not contact.matched:
        return ""
    return (contact.email or "").strip().lower()


def _from_customer(tenant, client_id: str) -> str:
    from apps.referrals.models import Customer

    customer = (
        Customer.objects.for_tenant(tenant).filter(client_id=client_id, deleted_at__isnull=True)
        .exclude(mobile="")
        .first()
    )
    return normalize_phone(customer.mobile) if customer else ""


def _from_zoho(tenant, client_id: str) -> str:
    """Zoho on-file channel lookup (Q-M-OTP-2, wired M13).

    Reads the referrer's Zoho Contact by ClientId through the M9 READ adapter and
    returns the on-file Mobile (Phone as fallback), normalized. Gated by the RESOLVED
    ENABLE_ZOHO_READ flag (admin override -> env default) so the Settings checkbox
    governs this exactly like the profile enrichment. Any failure degrades to "" —
    the caller falls back to Path B; a number is never guessed.
    """
    from apps.config.integration_flags import ENABLE_ZOHO_READ, resolve_flag

    if not resolve_flag(ENABLE_ZOHO_READ, tenant_id=getattr(tenant, "id", None)):
        return ""
    from apps.integrations.ports import get_crm_read_port

    try:
        contact = get_crm_read_port().fetch_contact_by_client_id(client_id=client_id)
    except Exception:  # noqa: BLE001 — a Zoho outage must degrade to Path B, never 500 a login
        logger.warning(
            "Zoho on-file OTP lookup failed for client_id=%s — degrading", client_id, exc_info=True
        )
        return ""
    if not contact.matched:
        return ""
    raw = contact.mobile or contact.phone or ""
    return normalize_phone(raw) if raw else ""
