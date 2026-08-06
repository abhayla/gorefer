"""On-file identity record for a client_id (M13) — the ONLY thing binding trusts.

ADR-027 auto-binds when the Google email OR the entered mobile matches what is
already ON FILE for the Client ID; ADR-035 sends the OTP only to the on-file
channel. Both read from the same two sources, most-authoritative first:

  1. `Customer` (GoRefer's own record: client_id -> mobile/email/name)
  2. Zoho Contact via the M9 READ adapter (gated by the resolved ENABLE_ZOHO_READ)

Nothing here ever trusts a value the user typed — typed values are only COMPARED
against this record.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from apps.common.phone import normalize_phone

logger = logging.getLogger("gorefer.accounts.onfile")


@dataclass
class OnFileRecord:
    client_id: str
    mobile: str = ""   # canonical 91-prefixed, or ""
    email: str = ""    # lowercased, or ""
    name: str = ""
    source: str = ""   # "customer" | "zoho" | ""

    @property
    def known(self) -> bool:
        return bool(self.mobile or self.email)


def resolve_onfile(tenant, client_id: str) -> OnFileRecord:
    """The on-file record for a client_id, or an empty record (→ Path B)."""
    client_id = (client_id or "").strip()
    if not client_id:
        return OnFileRecord(client_id="")

    from apps.referrals.models import Customer

    customer = (
        Customer.objects.for_tenant(tenant).filter(client_id=client_id, deleted_at__isnull=True)
        .exclude(mobile="", email="")
        .first()
    )
    if customer is not None:
        name = f"{customer.first_name} {customer.last_name}".strip()
        return OnFileRecord(
            client_id=client_id,
            mobile=normalize_phone(customer.mobile) if customer.mobile else "",
            email=(customer.email or "").strip().lower(),
            name=name,
            source="customer",
        )

    return _from_zoho(tenant, client_id)


def _from_zoho(tenant, client_id: str) -> OnFileRecord:
    from apps.config.integration_flags import ENABLE_ZOHO_READ, resolve_flag

    if not resolve_flag(ENABLE_ZOHO_READ, tenant_id=getattr(tenant, "id", None)):
        return OnFileRecord(client_id=client_id)
    from apps.integrations.ports import get_crm_read_port

    try:
        contact = get_crm_read_port().fetch_contact_by_client_id(client_id=client_id)
    except Exception:  # noqa: BLE001 — a Zoho outage degrades to "unknown", never a 500
        logger.warning("Zoho on-file lookup failed for %s — degrading", client_id, exc_info=True)
        return OnFileRecord(client_id=client_id)
    if not contact.matched:
        return OnFileRecord(client_id=client_id)
    raw_mobile = contact.mobile or contact.phone or ""
    return OnFileRecord(
        client_id=client_id,
        mobile=normalize_phone(raw_mobile) if raw_mobile else "",
        email=(contact.email or "").strip().lower(),
        name=contact.full_name or "",
        source="zoho",
    )


def auto_bind_matches(onfile: OnFileRecord, *, google_email: str, entered_mobile: str) -> bool:
    """ADR-027: auto-bind iff the Google email OR the entered mobile matches on-file.

    Both sides normalized (email lowercase; mobile through the ONE canonical phone
    normalizer). Empty on-file values never match anything.
    """
    email = (google_email or "").strip().lower()
    if email and onfile.email and email == onfile.email:
        return True
    mobile = normalize_phone(entered_mobile) if entered_mobile else ""
    if mobile and onfile.mobile and mobile == onfile.mobile:
        return True
    return False
