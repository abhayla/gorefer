"""WATI adapter behind the doc-08 contract (M5).

Two responsibilities:
  - send_template(): submit an approved template to a recipient. Returns an
    ACCEPTED acknowledgement (HTTP-200-equivalent) with a message id — NEVER
    treated as delivery.
  - get_message_status(): fetch the TERMINAL delivery status (delivered/read/failed)
    + any Meta error code. This is the ONLY proof of delivery (doc-08 A3).

ENABLE_WATI_SEND gates real sending:
  - false (default, dev/CI/demo): LogOnlyWatiAdapter logs the intended call + payload
    and simulates a delivered terminal status, so the whole flow is testable offline.
  - true: LiveWatiAdapter reads WATI_* config from env/secret store (never inline)
    and calls the real API. Full HTTP wiring is completed alongside Meta template
    approval (parallel workstream); until then it refuses to run without config.

Secrets (WATI bearer JWT etc.) come from env/secret store — never inline (A7).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from . import status

logger = logging.getLogger("gorefer.wati")


@dataclass
class SendResult:
    accepted: bool
    provider_message_id: str | None
    raw_status: str  # 'accepted' on submit — NOT delivery


@dataclass
class DeliveryResult:
    status: str                 # terminal status: delivered/read/failed
    meta_error_code: int | None
    classification: str | None


class LogOnlyWatiAdapter:
    """Demo/dev adapter: logs the intended send, simulates a delivered terminal status.

    Performs NO network call. The notification service still verifies the terminal
    status via get_message_status — proving the "assert on terminal status, not
    HTTP 200" discipline works end-to-end offline.
    """

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult:
        logger.info("[demo] WATI send suppressed: to=%s template=%s params=%s", to, template, params)
        return SendResult(
            accepted=True,
            provider_message_id=f"demo-{template}-{to}",
            raw_status=status.STATUS_ACCEPTED,
        )

    def get_message_status(self, *, provider_message_id: str) -> DeliveryResult:
        # Demo simulates a successful terminal delivery so the flow completes.
        return DeliveryResult(status=status.STATUS_DELIVERED, meta_error_code=None, classification=None)


class LiveWatiAdapter:  # pragma: no cover - exercised only with ENABLE_WATI_SEND=true
    """Real WATI adapter. Reads secrets from env/secret store (never inline)."""

    def __init__(self):
        self.base_url = os.environ.get("WATI_BASE_URL", "")
        self.token = os.environ.get("WATI_API_TOKEN", "")
        self.tenant_id = os.environ.get("WATI_TENANT_ID", "")
        if not (self.base_url and self.token):
            raise RuntimeError("WATI_BASE_URL / WATI_API_TOKEN not configured — cannot send live.")

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult:
        # Full HTTP wiring lands with Meta template approval (parallel workstream).
        # It must POST sendTemplateMessage with the bearer JWT and return the
        # provider message id — but NEVER treat HTTP 200 as delivery.
        raise NotImplementedError("Live WATI HTTP send is wired during Meta template approval.")

    def get_message_status(self, *, provider_message_id: str) -> DeliveryResult:
        raise NotImplementedError("Live WATI status polling is wired during Meta template approval.")


def get_wati_adapter():
    """Return the adapter for the EFFECTIVE flag state (log-only unless sending is on).

    Reads the resolved flag (admin override -> env default), not `flags.ENABLE_WATI_SEND`
    directly: the Settings checkbox must actually change behaviour. Reading raw env here
    would let the checkbox show "on" while the code kept sending nothing — or worse, show
    "off" while it kept sending.
    """
    from apps.config.integration_flags import ENABLE_WATI_SEND, resolve_flag

    if resolve_flag(ENABLE_WATI_SEND):
        return LiveWatiAdapter()
    return LogOnlyWatiAdapter()
