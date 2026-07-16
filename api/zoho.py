"""Zoho status webhook endpoint (M6) — the sole conversion-mutation entry point.

POST /api/zoho/status-webhook — authenticate, then ingest one Zoho account/reward
status update. 401 if unauthenticated. Guardrail #2: no other route or internal path
sets conversion/account status, which is exactly why the auth here carries weight —
a forged request would fabricate a conversion and credit a referrer for an account
that never opened.

Auth modes (see apps/integrations/zoho/webhook.authenticate):
  - default: static shared key + Zoho server-IP allowlist;
  - ENABLE_ZOHO_WEBHOOK_HMAC: the DF-2 wax-seal (HMAC over payload+timestamp+nonce)
    + the same IP allowlist. The static key is NOT a fallback in this mode.

**Body handling is security-relevant.** The view takes NO schema parameter, so Django
Ninja does not eagerly parse/validate the body before the auth check — auth runs
first, and the HMAC is computed over the RAW request bytes. Re-serializing a parsed
dict (`json.dumps(json.loads(body))`) could reorder keys or renormalize spacing and
would verify a different byte string than the one Zoho signed. Same ordering fix the
WATI webhook already carries.
"""
from __future__ import annotations

import json

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
def status_webhook(request):
    # 1) Read the RAW bytes once — this exact byte string is what the seal signs.
    raw_body = request.body or b"{}"

    # 2) AUTH FIRST — before any parsing/validation/business logic. Fails CLOSED.
    #    A 401 here is flat and reason-free: telling an unauthenticated caller which
    #    check failed (signature vs stale vs replay) would hand them a probing oracle.
    if not authenticate(request, raw_body=raw_body):
        raise HttpError(401, "unauthenticated")

    # 3) Only an authenticated caller reaches parsing.
    try:
        parsed = json.loads(raw_body)
    except (ValueError, TypeError) as exc:
        raise HttpError(422, "malformed JSON body") from exc
    if not isinstance(parsed, dict):
        raise HttpError(422, "body must be a JSON object")

    # Validate/coerce through the same schema the endpoint has always contracted on,
    # so the ingest layer keeps receiving a normalized payload (defaults applied).
    try:
        payload = StatusIn(**parsed)
    except Exception as exc:
        raise HttpError(422, "invalid payload") from exc

    return process_webhook(request, payload.dict())
