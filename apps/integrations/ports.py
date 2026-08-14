"""Vendor-neutral ports at the boundary's front door (ADR-045).

Domain code should import ONLY from here (or `.services` / `.delivery_status` /
`.models`) — never `apps.integrations.wati.*` / `apps.integrations.zoho.*` directly.
These Protocols formalize the shapes the existing adapters already have; this is
extraction, not redesign. Factories resolve to today's adapters unchanged (live vs
log-only still swaps by the same config flags) via LAZY imports inside the function
body — but the dataclass re-exports above (`SendResult`, `LeadWriteResult`, etc.) are
imported eagerly at module load, so importing this module DOES load the vendor adapter
modules; only the factory calls (which pick live vs log-only) are deferred.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from apps.integrations.computed_vars import assert_computed_vars_filled
from apps.integrations.wati.adapter import DeliveryResult, SendResult, TemplateStatus
from apps.integrations.zoho.adapter import (
    ContactWriteResult,
    LeadWriteResult,
    ReferrerHistory,
)
from apps.integrations.zoho.read import (
    ReferredPeople,
    ReferrerAudience,
    SendQueueCounts,
    ZohoContact,
    ZohoReferredPerson,
    ZohoReferrerRow,
)

__all__ = [
    "SendResult",
    "DeliveryResult",
    "TemplateStatus",
    "GuardedMessagingPort",
    "LeadWriteResult",
    "ReferrerHistory",
    "ContactWriteResult",
    "ZohoContact",
    "ZohoReferredPerson",
    "ReferredPeople",
    "ZohoReferrerRow",
    "ReferrerAudience",
    "SendQueueCounts",
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

    def get_template_status(self, *, template: str) -> TemplateStatus: ...


class GuardedMessagingPort:
    """The messaging port with the fail-closed computed-variable guard fitted (T-073).

    Every messaging adapter leaves this factory wrapped, so the guard is a property
    of the PORT rather than of any one caller's good manners. A template that needs
    a server-computed variable (today `{{token}}`) and is handed a missing or blank
    one raises `MissingComputedVar` here — before the adapter, before the network.
    Templates carrying no computed variable pass through untouched, so nothing that
    worked before changes.

    The rest of the port is delegated. The Protocol surface is delegated EXPLICITLY
    (not only through `__getattr__`) because `isinstance(x, MessagingPort)` uses
    `inspect.getattr_static`, which never fires `__getattr__` — a wrapper that
    delegated only dynamically would stop satisfying its own Protocol. `__getattr__`
    still covers vendor extras like `kind`.
    """

    def __init__(self, inner):
        self._inner = inner

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult:
        assert_computed_vars_filled(template, params)
        return self._inner.send_template(to=to, template=template, params=params)

    def send_session_text(self, *, to: str, message: str) -> SendResult:
        # A session message carries no template, so there is nothing to guard.
        return self._inner.send_session_text(to=to, message=message)

    def get_message_status(
        self, *, provider_message_id: str, recipient_mobile: str | None = None,
        template: str | None = None,
    ) -> DeliveryResult:
        return self._inner.get_message_status(
            provider_message_id=provider_message_id, recipient_mobile=recipient_mobile,
            template=template,
        )

    def get_latest_inbound_at(self, mobile: str):
        return self._inner.get_latest_inbound_at(mobile)

    def get_template_status(self, *, template: str) -> TemplateStatus:
        return self._inner.get_template_status(template=template)

    def __getattr__(self, item):
        return getattr(self._inner, item)


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

    def fetch_referrer_audience(self) -> ReferrerAudience: ...

    def fetch_send_queue_counts(self, *, date_ist) -> SendQueueCounts: ...


def get_messaging_port() -> MessagingPort:
    """Return the effective messaging port (live/log-only, unchanged by flag),
    wrapped in the fail-closed computed-variable guard (T-073)."""
    from apps.integrations.wati.adapter import get_wati_adapter

    return GuardedMessagingPort(get_wati_adapter())


def get_crm_port() -> CrmPort:
    """Return the effective CRM write port (live/log-only, unchanged by flag)."""
    from apps.integrations.zoho.adapter import get_zoho_adapter

    return get_zoho_adapter()


def get_crm_read_port() -> CrmReadPort:
    """Return the effective CRM read port (live/log-only, unchanged by flag)."""
    from apps.integrations.zoho.read import get_zoho_read_adapter

    return get_zoho_read_adapter()
