"""Zoho adapter behind the doc-08 contract (M6).

create_lead(): write the Lead to Zoho on capture-first submit, stamping a GoRefer
journey-reference on the Zoho lead (#10) for best-effort opener→journey linking.
fetch_referrer_history(): lazy per-referrer history pull on first appearance (#9).

ENABLE_ZOHO_WRITE gates real calls:
  - false (default): LogOnlyZohoAdapter logs the intended call + returns a fake
    zoho_lead_id, so the flow works offline. Conversions are exercised via fixtures
    fed through the SAME webhook ingest path (never an internal fabrication).
  - true: LiveZohoAdapter reads ZOHO_* config; real HTTP wiring lands with Zoho
    sandbox verification. Refuses to run without config.

Guardrail #2: this adapter NEVER sets account/conversion status internally — status
comes back ONLY through the webhook ingest path.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from gorefer.flags import flags

logger = logging.getLogger("gorefer.zoho")


@dataclass
class LeadWriteResult:
    zoho_lead_id: str
    gorefer_reference: str


@dataclass
class ReferrerHistory:
    referrer_client_id: str
    conversions: list = field(default_factory=list)  # list of conversion dicts (Zoho-shaped)


def gorefer_reference_for(referral) -> str:
    """The reference stamped on the Zoho lead + echoed back on conversion (#10)."""
    return f"GR-{referral.pk}" if referral is not None else ""


class LogOnlyZohoAdapter:
    """Demo/dev adapter: logs the intended Zoho write, returns a fake lead id."""

    def create_lead(self, *, payload: dict, gorefer_reference: str) -> LeadWriteResult:
        logger.info("[demo] Zoho create_lead suppressed: ref=%s payload=%s", gorefer_reference, payload)
        # Deterministic fake id so tests can key on it.
        fake_id = f"demo-zoho-{payload.get('mobile', 'x')}"
        return LeadWriteResult(zoho_lead_id=fake_id, gorefer_reference=gorefer_reference)

    def fetch_referrer_history(self, *, referrer_client_id: str) -> ReferrerHistory:
        logger.info("[demo] Zoho fetch_referrer_history suppressed: %s", referrer_client_id)
        return ReferrerHistory(referrer_client_id=referrer_client_id, conversions=[])


class LiveZohoAdapter:  # pragma: no cover - exercised only with ENABLE_ZOHO_WRITE=true
    def __init__(self):
        self.client_id = os.environ.get("ZOHO_CLIENT_ID", "")
        self.client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN", "")
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise RuntimeError("ZOHO_* credentials not configured — cannot run live.")

    def create_lead(self, *, payload: dict, gorefer_reference: str) -> LeadWriteResult:
        raise NotImplementedError("Live Zoho lead write is wired during sandbox verification.")

    def fetch_referrer_history(self, *, referrer_client_id: str) -> ReferrerHistory:
        raise NotImplementedError("Live Zoho history fetch is wired during sandbox verification.")


def get_zoho_adapter():
    if flags.ENABLE_ZOHO_WRITE:
        return LiveZohoAdapter()
    return LogOnlyZohoAdapter()
