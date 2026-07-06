"""Share tracking API (M3) — POST /api/share.

Records a share action + channel as an immutable event (share_clicked). The
"Share on WhatsApp" button is a client-side wa.me deep link to the WATI business
number (config-driven); tapping it fires this endpoint AND opens WhatsApp.
"""
from __future__ import annotations

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.events.models import Event
from apps.referrals.models import ReferralIdentity
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

router = Router()

SHARE_CLICKED_EVENT = "share_clicked"
_CHANNELS = {
    "whatsapp", "whatsapp_status", "facebook", "instagram",
    "linkedin", "x", "email", "copy_link", "qr",
}


class ShareIn(Schema):
    client_id: str
    channel: str


class ShareOut(Schema):
    recorded: bool
    channel: str


@router.post("/", response={202: ShareOut})
def record_share(request, payload: ShareIn):
    try:
        client_id = validate_client_id(payload.client_id)
    except InvalidClientId:
        raise HttpError(400, "invalid client_id")
    if payload.channel not in _CHANNELS:
        raise HttpError(422, "invalid channel")

    tenant = get_current_tenant(request)
    identity = ReferralIdentity.objects.filter(
        tenant=tenant, client_id=client_id, id_source="native"
    ).first()
    referral = identity.referrals.filter(source="referral_link").first() if identity else None

    Event.objects.create(
        tenant=tenant,
        event_type=SHARE_CLICKED_EVENT,
        referral=referral,
        user_type="anonymous",
        metadata={"channel": payload.channel},  # channel is not PII
    )
    return {"recorded": True, "channel": payload.channel}
