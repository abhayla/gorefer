"""T-097 — advisor callback capture: POST /api/callback-request.

A chatbot flow POSTs here after a customer asks for a call and picks a slot. GoRefer
alerts a staff number IMMEDIATELY (via the messaging port) and schedules a reminder
for the slot's start via the existing followups engine. Mounted only when
`ENABLE_ADVISOR_CALLBACK` is on (see api/router.py) — Constitution §4, no dead route.

No customer message is ever sent from this path — the staff number is the only
recipient (apps.followups.advisor_callback).
"""
from __future__ import annotations

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.phone import normalize_phone
from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.followups.advisor_callback import request_and_schedule, send_alert
from apps.followups.models import AdvisorCallbackRequest
from apps.tenants.resolve import get_current_tenant

router = Router()

_VALID_SLOTS = {
    AdvisorCallbackRequest.SLOT_9_12,
    AdvisorCallbackRequest.SLOT_12_3,
    AdvisorCallbackRequest.SLOT_3_6,
}


class CallbackRequestIn(Schema):
    mobile: str
    slot: str
    name: str | None = ""


class CallbackRequestOut(Schema):
    status: str
    slot: str
    reminder_at: str


@router.post("/", response={200: CallbackRequestOut})
def create_callback_request(request, payload: CallbackRequestIn):
    try:
        check_rate(
            "callback_request", client_ip(request),
            limit=settings.RATELIMIT_CALLBACK_MAX, window=settings.RATELIMIT_API_WINDOW,
        )
    except RateLimited as exc:
        raise HttpError(429, f"too many requests; retry after {exc.retry_after}s")

    mobile = normalize_phone(payload.mobile)
    if not mobile:
        raise HttpError(422, "mobile is required")
    slot = (payload.slot or "").strip()
    if slot not in _VALID_SLOTS:
        raise HttpError(422, f"slot must be one of {sorted(_VALID_SLOTS)}")
    name = (payload.name or "").strip()[:80]

    tenant = get_current_tenant(request)
    req, created = request_and_schedule(tenant, mobile=mobile, name=name, slot=slot)
    if created:
        send_alert(tenant, req)

    return 200, {
        "status": "created" if created else "duplicate",
        "slot": req.slot,
        "reminder_at": req.reminder.fire_at.isoformat() if req.reminder else "",
    }
