"""Share tracking API (M3) — POST /api/share.

Records a share action + channel as an immutable event (share_clicked). The
"Share on WhatsApp" button is a client-side wa.me deep link to the WATI business
number (config-driven); tapping it fires this endpoint AND opens WhatsApp.
"""
from __future__ import annotations

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.events import vocab
from apps.events.models import Event
from apps.referrals.models import ReferralIdentity
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

router = Router()

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
    # Unauthenticated attribution write — rate-limit per IP so it can't be flooded to
    # inflate share_clicked counts (Fable5 H3 / L4).
    try:
        check_rate("share", client_ip(request),
                   limit=settings.RATELIMIT_SHARE_MAX, window=settings.RATELIMIT_API_WINDOW)
    except RateLimited as exc:
        raise HttpError(429, f"too many requests; retry after {exc.retry_after}s")

    try:
        client_id = validate_client_id(payload.client_id)
    except InvalidClientId:
        raise HttpError(400, "invalid client_id")
    if payload.channel not in _CHANNELS:
        raise HttpError(422, "invalid channel")

    tenant = get_current_tenant(request)
    identity = ReferralIdentity.objects.for_tenant(tenant).filter(
        client_id=client_id, id_source="native"
    ).first()
    referral = identity.referrals.filter(source="referral_link").first() if identity else None

    Event.objects.create(
        tenant=tenant,
        event_type=vocab.SHARE_CLICKED,
        source=vocab.SRC_SYSTEM,
        referral=referral,
        user_type="anonymous",
        metadata={"channel": payload.channel},  # channel is not PII
    )
    return {"recorded": True, "channel": payload.channel}
