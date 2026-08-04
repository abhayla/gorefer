"""Vendor-neutral ports at the boundary's front door (ADR-045).

Domain code should import ONLY from here (or `.services` / `.delivery_status` /
`.models`) — never `apps.integrations.wati.*` / `apps.integrations.zoho.*` directly.
These Protocols formalize the shapes the existing adapters already have; this is
extraction, not redesign. Factories resolve to today's adapters unchanged (live vs
log-only still swaps by the same config flags) via LAZY imports inside the function
body, so importing this module never triggers app-loading of the vendor packages.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from apps.integrations.wati.adapter import DeliveryResult, SendResult
from apps.integrations.zoho.adapter import (
    ContactWriteResult,
    LeadWriteResult,
    ReferrerHistory,
)
from apps.integrations.zoho.read import ReferredPeople, ZohoContact, ZohoReferredPerson

__all__ = [
    "SendResult",
    "DeliveryResult",
    "LeadWriteResult",
    "ReferrerHistory",
    "ContactWriteResult",
    "ZohoContact",
    "ZohoReferredPerson",
    "ReferredPeople",
    "MessagingPort",
    "CrmPort",
    "CrmReadPort",
    "get_messaging_port",
    "get_crm_port",
    "get_crm_read_port",
]


@runtime_checkable
class MessagingPort(Protocol):
    """Vendor-neutral messaging surface (today: WATI)."""

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult: ...

    def send_session_text(self, *, to: str, message: str) -> SendResult: ...

    def get_message_status(
        self, *, provider_message_id: str, recipient_mobile: str | None = None,
        template: str | None = None,
    ) -> DeliveryResult: ...

    def get_latest_inbound_at(self, mobile: str): ...


@runtime_checkable
class CrmPort(Protocol):
    """Vendor-neutral CRM write surface (today: Zoho)."""

    def upsert_lead(self, *, payload: dict, gorefer_reference: str) -> LeadWriteResult: ...

    def fetch_referrer_history(self, *, referrer_client_id: str) -> ReferrerHistory: ...

    def upsert_referrer_contact(
        self, *, client_id: str, name: str, mobile: str, email: str = "",
    ) -> ContactWriteResult: ...


@runtime_checkable
class CrmReadPort(Protocol):
    """Vendor-neutral CRM read/enrichment surface (today: Zoho)."""

    def fetch_contact_by_client_id(self, *, client_id: str) -> ZohoContact: ...

    def fetch_referred_people(self, *, referrer_client_id: str) -> ReferredPeople: ...


def get_messaging_port() -> MessagingPort:
    """Return the effective messaging port (live/log-only, unchanged by flag)."""
    from apps.integrations.wati.adapter import get_wati_adapter

    return get_wati_adapter()


def get_crm_port() -> CrmPort:
    """Return the effective CRM write port (live/log-only, unchanged by flag)."""
    from apps.integrations.zoho.adapter import get_zoho_adapter

    return get_zoho_adapter()


def get_crm_read_port() -> CrmReadPort:
    """Return the effective CRM read port (live/log-only, unchanged by flag)."""
    from apps.integrations.zoho.read import get_zoho_read_adapter

    return get_zoho_read_adapter()
