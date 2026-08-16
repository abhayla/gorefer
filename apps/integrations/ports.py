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

import time
from typing import Protocol, runtime_checkable

from apps.integrations.computed_vars import assert_computed_vars_filled
from apps.integrations.wati.adapter import (
    TEMPLATE_STATUS_UNKNOWN,
    DeliveryResult,
    SendResult,
    TemplateStatus,
)
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
    "SendRefused",
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


class SendRefused(RuntimeError):
    """Raised when a send is refused by a RUN/PORT-LEVEL gate — never a per-recipient
    skip (those are recorded, not raised). Today: the resolved template is not
    APPROVED at the vendor, or the vendor cannot be asked at all.
    """


#: Approval-probe cache: template name -> (expires_at_monotonic, TemplateStatus).
#: Process-wide (not per-port-instance) because `get_messaging_port()` builds a FRESH
#: wrapped adapter on every call (T-073's factory), so instance-level caching would
#: cache nothing across the very sequence of many-recipients-in-one-sweep sends this
#: exists to protect Wati from. Short TTL bounds how stale an approval flip can be.
_APPROVAL_CACHE_TTL_SECONDS = 300
_approval_cache: dict[str, tuple[float, TemplateStatus]] = {}


def _clear_approval_cache() -> None:
    """Test-only: the process-wide cache must not leak approval state across tests
    that reuse the same template name with a different fake adapter."""
    _approval_cache.clear()


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

    def get_latest_inbound(self, mobile: str): ...

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
        self.assert_template_approved(template)
        return self._inner.send_template(to=to, template=template, params=params)

    def assert_template_approved(self, template: str) -> None:
        """Refuse the send unless the vendor itself says this template is APPROVED.

        Public so a caller that wants to fail a whole BATCH fast — before any
        per-recipient work — can probe once up front (see
        `records_link_send._run`); `send_template` above still calls this itself,
        so a caller that skips the up-front probe is still covered.

        Fails CLOSED in three directions: an adapter with no way to ask, a vendor
        call that errors, and a name the vendor has never heard of all refuse.
        Precedent for why this is not paranoia: prod's `otp_whatsapp_template` was a
        name Meta had never seen, and every WhatsApp OTP 400-ed silently while the
        flag read ON (CLAUDE.md §6c).

        Fitted at the PORT (T-161 pt 15) rather than in one sender's good manners, so
        EVERY send path (lead notifications, followups, congrats, campaigns, records
        link, invite) inherits it — not only the callers that remembered to ask. The
        log-only/demo adapter needs no special-case exemption: its own
        `get_template_status` already simulates an always-APPROVED answer (see
        `LogOnlyWatiAdapter.get_template_status`), so demo mode keeps working
        end-to-end without a network call, exactly as it did before this moved.
        """
        now = time.monotonic()
        cached = _approval_cache.get(template)
        if cached is not None and cached[0] > now:
            state = cached[1]
        else:
            probe = getattr(self._inner, "get_template_status", None)
            if probe is None:
                raise SendRefused(
                    f"refused: cannot verify that {template!r} is approved "
                    "(messaging port exposes no template-status check)"
                )
            try:
                state = probe(template=template)
            except Exception as exc:  # a vendor/transport error is UNKNOWN, never approval
                raise SendRefused(
                    f"refused: template-status check for {template!r} failed "
                    f"({exc.__class__.__name__})"
                ) from exc
            # Only a SUCCESSFUL probe is cached — an error above is never memoized, so
            # a transient vendor blip costs one refused send, not five minutes of them.
            _approval_cache[template] = (now + _APPROVAL_CACHE_TTL_SECONDS, state)
        if not getattr(state, "approved", False):
            raise SendRefused(
                f"refused: template {template!r} is not APPROVED at the vendor "
                f"(status={getattr(state, 'status', TEMPLATE_STATUS_UNKNOWN)})"
            )

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

    def get_latest_inbound(self, mobile: str):
        return self._inner.get_latest_inbound(mobile)

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
