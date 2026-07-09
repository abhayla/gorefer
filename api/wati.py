"""WATI assisted-referral webhook endpoint (B4 / ADR-033).

POST /api/wati/webhook — auth (static key + IP allowlist) then create ONE Zoho lead
from an assisted capture {client_id (referrer), name, mobile, email?, consent?}.
401 if unauthenticated; 422 on a malformed payload. Behind ENABLE_ZOHO_WRITE
(log-only when off). Never stores a password; deduped.
"""
from __future__ import annotations

import json

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.integrations.wati.webhook import (
    FORBIDDEN_KEYS,
    AssistedCaptureError,
    authenticate,
    process_assisted_capture,
)

router = Router()


def _reject_credential_fields(request) -> None:
    """Defense-in-depth: refuse the raw request if it carries any credential-shaped
    field (Ninja would silently drop unknown keys, so check the raw body). Never a
    password (B4 / S2-04)."""
    try:
        raw = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return  # malformed JSON is handled by schema parsing / downstream 422
    if isinstance(raw, dict):
        for key in raw:
            if str(key).lower() in FORBIDDEN_KEYS:
                raise HttpError(422, f"forbidden field in assisted capture: {key}")


class AssistedIn(Schema):
    client_id: str          # the REFERRER's Zerodha client id
    name: str               # prospect name
    mobile: str             # prospect mobile
    email: str | None = ""
    consent: bool | None = True


class AssistedOut(Schema):
    status: str
    lead_id: int
    lead_source: str
    consent: bool


@router.post("/webhook", response=AssistedOut)
def assisted_webhook(request, payload: AssistedIn):
    if not authenticate(request):
        raise HttpError(401, "unauthenticated")
    _reject_credential_fields(request)
    try:
        result = process_assisted_capture(request, payload.dict())
    except AssistedCaptureError as exc:
        raise HttpError(422, str(exc)) from exc
    return result
