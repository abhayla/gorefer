"""One-tap share endpoint service (M-WATI-1 — Wati conversation-map integration).

GET /share/{channel}/{client_id} lets a referrer forward their tracked link with
one tap, from inside a WATI-delivered message, straight into a channel's native
share/compose surface (launch: WhatsApp). This module builds that destination and
records a PII-free `share_intent` event — never the redirect itself (the tracked
link embedded in the kit message still resolves through the existing /r/ engine,
so ADR-008 lazy-creation + attribution behave exactly as they do for any other
share channel).

Guardrails enforced here (mirrors redirect_service.py):
  - REDIRECT ONLY. This module assembles a `wa.me` URL and returns it for a 302;
    it never calls out to WhatsApp or Zerodha itself.
  - A bot/preview hit returns the destination but creates NO identity/referral and
    writes NO event (same contract as the /r/ redirect service).
  - No PII is ever written — the share_intent event carries no VisitorPII record
    (there is no raw IP to attribute; the tracked link itself carries attribution).
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from django.db import transaction
from django.http import Http404

from apps.events import vocab
from apps.events.bots import is_bot_user_agent
from apps.events.models import Event
from gorefer.flags import SHARE_CHANNEL_OTHER, SHARE_INTENT_CHANNELS, flags, normalize_share_channel

from .redirect_service import get_active_program, lazy_get_or_create_referral

logger = logging.getLogger("gorefer.share_intent")


def build_whatsapp_target(message: str) -> str:
    """The WhatsApp share deep-link: a prefilled compose screen, no recipient."""
    return f"https://wa.me/?text={quote(message, safe='')}"


_CHANNEL_TARGET_BUILDERS = {
    "wa": build_whatsapp_target,
}


def _public_host() -> str:
    """The configured public host, scheme stripped (matches the bare-host form
    already used in kit messages elsewhere — the tracked link is shown as plain
    text, not a clickable URL with a scheme prefix)."""
    from django.conf import settings

    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    for prefix in ("https://", "http://"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def _tracked_link(channel: str, client_id: str) -> str:
    return f"{_public_host()}/r/{channel}/{client_id}"


def handle_share_intent(*, tenant, channel: str, client_id: str, user_agent: str | None):
    """Resolve a /share/{channel}/{client_id} hit. Returns the destination URL.

    Raises Http404 for an unsupported/unlisted channel (never a silent "other"
    fallback — unlike the /r/ attribution tag, this gates which channels the
    endpoint actually SERVES). May raise the redirect_service PartnerUnavailable
    tuple (ReferralProgram.DoesNotExist / ProgramRedirectRule.DoesNotExist) when
    config resolution fails — the caller renders the branded 503, same as /r/.
    """
    if channel not in SHARE_INTENT_CHANNELS or channel not in _CHANNEL_TARGET_BUILDERS:
        raise Http404(f"unsupported share channel: {channel!r}")

    program = get_active_program(tenant)
    message = flags.SHARE_KIT_MESSAGE_TEMPLATE.format(link=_tracked_link(channel, client_id))
    destination = _CHANNEL_TARGET_BUILDERS[channel](message)

    if is_bot_user_agent(user_agent):
        logger.info("bot/preview hit on /share/%s/%s — no journey created", channel, client_id)
        return destination

    referral = lazy_get_or_create_referral(tenant, program, client_id)
    transaction.on_commit(
        lambda: Event.objects.create(
            tenant=tenant,
            event_type=vocab.SHARE_INTENT,
            source=vocab.SRC_WATI,
            referral=referral,
            user_type="anonymous",
            user_agent=user_agent or "",
            is_bot=False,
            person_ref_id=None,  # PII-FREE — no VisitorPII write for this endpoint
            metadata={"channel": normalize_share_channel(channel) or SHARE_CHANNEL_OTHER},
        )
    )
    return destination
