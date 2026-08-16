"""Click confirmation beacon + beacon-gated referrer-name reveal (M3).

- POST /api/click/confirm : consume the one-time nonce, mark the landing click
  confirmed-human. Idempotent per nonce. 401 on a forged/expired/used nonce.
- GET  /api/click/referrer/{client_id}?nonce= : return the referrer's first name
  ONLY to a request carrying a valid, fresh nonce — closing the id->name
  enumeration hole (ADR-021). Rate-limited (per-IP, apps.common.ratelimit) +
  bot-filtered + nonce-gated at the edge of this view.

The referrer's first name is resolved from `Customer` (kept current by the daily
`sync_referrer_names` job, apps/integrations/zoho/tasks.py) by `client_id`, same
lookup pattern as the referrer-nudge copy in apps/followups/tasks.py. Only the
FIRST name is ever returned — never the surname — and null when no Customer is on
file. Owner-approved: anyone holding a public client_id can see the referrer's
first name (eight-lens review pt 5, 2026-08-16).
"""
from __future__ import annotations

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.events import vocab
from apps.events.bots import is_bot_user_agent
from apps.events.models import Event
from apps.events.nonces import consume_nonce, peek_nonce
from apps.referrals.models import Customer
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
    try:
        check_rate("click", client_ip(request),
                   limit=settings.RATELIMIT_CLICK_MAX, window=settings.RATELIMIT_API_WINDOW)
    except RateLimited as exc:
        raise HttpError(429, f"too many requests; retry after {exc.retry_after}s")
    row = consume_nonce(nonce=payload.nonce, visitor_id=payload.visitor_id or "")
    if row is None:
        raise HttpError(401, "invalid or expired nonce")

    # Promote this visitor's pending events to confirmed-human, and record an
    # explicit human_confirmed event (source: beacon) for the funnel/timeline.
    visitor_id = payload.visitor_id or row.visitor_id
    if visitor_id:
        Event.objects.filter(
            visitor_id=visitor_id, is_confirmed_human=False, is_bot=False
        ).update(is_confirmed_human=True)
        Event.objects.create(
            tenant=row.tenant,
            event_type=vocab.HUMAN_CONFIRMED,
            source=vocab.SRC_BEACON,
            referral=row.referral,
            user_type="anonymous",
            visitor_id=visitor_id,
            is_confirmed_human=True,
            metadata={},
        )
    return {"confirmed": True}


@router.get("/referrer/{client_id}", response=ReferrerOut)
def reveal_referrer(request, client_id: str, nonce: str = ""):
    """Beacon-gated name reveal. Requires a valid, fresh nonce; bot-filtered + rate-limited."""
    try:
        check_rate("click", client_ip(request),
                   limit=settings.RATELIMIT_CLICK_MAX, window=settings.RATELIMIT_API_WINDOW)
    except RateLimited as exc:
        raise HttpError(429, f"too many requests; retry after {exc.retry_after}s")
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

    cust = (
        Customer.objects.for_tenant(row.tenant)
        .filter(client_id=client_id, deleted_at__isnull=True)
        .exclude(first_name="")
        .first()
    )
    first_name = cust.first_name if cust else None
    return {"has_referrer": True, "first_name": first_name}
