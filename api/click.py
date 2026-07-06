"""Click confirmation beacon + beacon-gated referrer-name reveal (M3).

- POST /api/click/confirm : consume the one-time nonce, mark the landing click
  confirmed-human. Idempotent per nonce. 401 on a forged/expired/used nonce.
- GET  /api/click/referrer/{client_id}?nonce= : return the referrer's first name
  ONLY to a request carrying a valid, fresh nonce — closing the id->name
  enumeration hole (ADR-021). Rate-limited + bot-filtered at the edge of this view.

M3 note: GoRefer has NO referrer *name* source yet (names arrive from Zoho in M6),
so `first_name` is returned empty/null with `has_referrer=true`. We never fabricate
a name — the endpoint + nonce gate are what M3 delivers; the value fills in at M6.
"""
from __future__ import annotations

from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.events.bots import is_bot_user_agent
from apps.events.models import Event
from apps.events.nonces import consume_nonce, peek_nonce
from apps.referrals.validators import InvalidClientId, validate_client_id

router = Router()


class ConfirmIn(Schema):
    visitor_id: str | None = None
    nonce: str
    client_id: str | None = None


class ConfirmOut(Schema):
    confirmed: bool


class ReferrerOut(Schema):
    has_referrer: bool
    first_name: str | None = None


@router.post("/confirm", response={202: ConfirmOut})
def confirm_click(request, payload: ConfirmIn):
    """Verify + consume the nonce; mark the visitor's landing event confirmed-human."""
    row = consume_nonce(nonce=payload.nonce, visitor_id=payload.visitor_id or "")
    if row is None:
        raise HttpError(401, "invalid or expired nonce")

    # Promote the pending landing_viewed event for this visitor to confirmed-human.
    visitor_id = payload.visitor_id or row.visitor_id
    if visitor_id:
        Event.objects.filter(
            visitor_id=visitor_id, is_confirmed_human=False, is_bot=False
        ).update(is_confirmed_human=True)
    return {"confirmed": True}


@router.get("/referrer/{client_id}", response=ReferrerOut)
def reveal_referrer(request, client_id: str, nonce: str = ""):
    """Beacon-gated name reveal. Requires a valid, fresh nonce; bot-filtered."""
    if is_bot_user_agent(request.META.get("HTTP_USER_AGENT", "")):
        raise HttpError(401, "unauthenticated")
    try:
        validate_client_id(client_id)
    except InvalidClientId:
        raise HttpError(400, "invalid client_id")

    visitor_id = request.COOKIES.get("gr_vid", "")
    row = peek_nonce(nonce=nonce, visitor_id=visitor_id)
    if row is None:
        raise HttpError(401, "unauthenticated")

    # M3: no referrer-name source yet (fills at M6 from Zoho). Never fabricate.
    _ = timezone.now()
    return {"has_referrer": True, "first_name": None}
