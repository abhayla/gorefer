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
    # Model 2 (DA 2026-07-15): the lead write is an idempotent UPSERT keyed on the
    # normalized mobile — never a blind create. See apps/integrations/zoho/adapter.py
    # for the implementations selected by ENABLE_ZOHO_WRITE.
    def upsert_lead(self, *, payload: dict, gorefer_reference: str) -> dict: ...


class LogOnlyWatiAdapter:
    """Demo/dev adapter: logs the intended WATI send, performs no network call."""

    def send_template(self, *, to: str, template: str, params: dict) -> dict:
        logger.info("[demo] WATI send suppressed: to=%s template=%s params=%s", to, template, params)
        return {"status": "suppressed", "reason": "ENABLE_WATI_SEND=false"}


class LogOnlyZohoAdapter:
    """Demo/dev adapter: logs the intended Zoho write, performs no network call.

    NOTE: the adapter actually used by the lead pipeline is the one in
    apps/integrations/zoho/adapter.py (which carries the Model 2 upsert + fixtures).
    This M1-skeleton stub remains only as the doc-08 interface reference.
    """

    def upsert_lead(self, *, payload: dict, gorefer_reference: str = "") -> dict:
        logger.info("[demo] Zoho upsert_lead suppressed: payload=%s", payload)
        return {"status": "suppressed", "reason": "ENABLE_ZOHO_WRITE=false"}
