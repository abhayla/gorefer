"""Adapter interfaces for external systems (WATI, Zoho) — doc-08 contract.

M1 provides only the interfaces + a log-only default so demo mode works end-to-end
with ENABLE_WATI_SEND / ENABLE_ZOHO_WRITE off (the adapter LOGS its intended call
instead of sending). Real HTTP adapters land in M5 (WATI) and M6 (Zoho).

Guardrail: no adapter here writes account/reward status — that is Zoho-inbound only
(M6), never fabricated by GoRefer.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("gorefer.integrations")


class WatiAdapter(Protocol):
    def send_template(self, *, to: str, template: str, params: dict) -> dict: ...


class ZohoAdapter(Protocol):
    def create_lead(self, *, payload: dict) -> dict: ...


class LogOnlyWatiAdapter:
    """Demo/dev adapter: logs the intended WATI send, performs no network call."""

    def send_template(self, *, to: str, template: str, params: dict) -> dict:
        logger.info("[demo] WATI send suppressed: to=%s template=%s params=%s", to, template, params)
        return {"status": "suppressed", "reason": "ENABLE_WATI_SEND=false"}


class LogOnlyZohoAdapter:
    """Demo/dev adapter: logs the intended Zoho write, performs no network call."""

    def create_lead(self, *, payload: dict) -> dict:
        logger.info("[demo] Zoho create_lead suppressed: payload=%s", payload)
        return {"status": "suppressed", "reason": "ENABLE_ZOHO_WRITE=false"}
