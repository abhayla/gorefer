"""Zoho status webhook endpoint (M6) — the sole conversion-mutation entry point.

POST /api/zoho/status-webhook  — auth (static key + IP allowlist) then ingest one
Zoho account/reward status update. 401 if unauthenticated. Guardrail #2: no other
route or internal path sets conversion/account status.
"""
from __future__ import annotations

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.integrations.zoho.webhook import authenticate, process_webhook

router = Router()


class StatusIn(Schema):
    event_id: str | None = None
    opener_zerodha_account_id: str | None = None
    zoho_lead_id: str | None = None
    opener_name: str | None = None
    referrer_client_id: str | None = None
    status: str | None = "account opened"
    account_opened_at: str | None = None
    reward_status: str | None = None
    reversed: bool = False


class StatusOut(Schema):
    status: str
    applied: bool
    conversion_id: int | None = None


@router.post("/status-webhook", response=StatusOut)
def status_webhook(request, payload: StatusIn):
    if not authenticate(request):
        raise HttpError(401, "unauthenticated")
    result = process_webhook(request, payload.dict())
    return result
