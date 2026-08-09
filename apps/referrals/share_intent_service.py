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
    """The configured public host, scheme stripped (used to compose full https URLs
    and the disclosure anchor from one canonical host value)."""
    from django.conf import settings

    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    for prefix in ("https://", "http://"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def tracked_link(channel: str, client_id: str) -> str:
    # Full https URL, matching the selfview share builder. A scheme-less link is
    # not linkified by every client, and — observed live 2026-07-28 — it loses the
    # WhatsApp preview card to the disclosure URL (the message's only full URL),
    # so recipients saw a "Disclosures" headline instead of the referral landing.
    # The tracked link must be the FIRST full URL in the kit so the preview is the
    # PIFS-branded landing page.
    return f"https://{_public_host()}/r/{channel}/{client_id}"


SHARE_KIT_MESSAGE_KEY = "share_kit_message_template"


def kit_message(
    channel: str, client_id: str, tenant_id: int | None, *, program=None, lang: str = "en"
) -> str:
    """The share prefill, resolved through the config cascade (CLAUDE.md §6d).

    Four things fixed together here:

    1. COMPLIANCE (found 2026-07-27). This prefill is a generated asset a referrer
       forwards to prospects, so §4 requires the disclosure anchor on it — and the
       sibling builder in `apps/accounts/selfview.py` already appends
       `· Disclosures: …`. This one did not, so the same product shipped two share
       messages that disagreed on compliance. The disclosure host is appended here
       rather than baked into the template string, so an operator editing the copy
       cannot accidentally drop it.
    2. §6d. The copy lived only in `flags.SHARE_KIT_MESSAGE_TEMPLATE`, an env-level flag —
       "message settings are CONFIGURATION, not code". It is now a cascade key with the
       flag as its default, so the owner can reword it without a deploy.
    3. T-059. `{program_brand}` is resolved here at BUILD time via the T-056 fallback
       chain (apps.referrals.branding). `program` is the caller's already-resolved
       program when it has one in scope (e.g. handle_share_intent); with no identity
       context the tenant's single active program is used instead — never a literal.
    4. T-061. `lang="hi"` resolves the `share_kit_message_template_hi` cascade twin
       (falling back to the EN template when unset/blank — apps.config.i18n contract)
       so a referrer sharing from the Hindi hub forwards a Hindi prefill.
    """
    from apps.config.i18n import bi_text
    from apps.config.preferences import SHARE_KIT_MESSAGE_TEMPLATE_HI_DEFAULT

    from .branding import brand_for_program, brand_for_tenant_id

    default = flags.SHARE_KIT_MESSAGE_TEMPLATE
    try:
        template = str(
            bi_text(
                SHARE_KIT_MESSAGE_KEY, default, lang=lang, tenant_id=tenant_id,
                default_hi=SHARE_KIT_MESSAGE_TEMPLATE_HI_DEFAULT,
            ) or default
        )
    except Exception:
        template = default
    brand = brand_for_program(program) if program is not None else brand_for_tenant_id(tenant_id)
    message = template.format(link=tracked_link(channel, client_id), program_brand=brand)
    anchor = f"Disclosures: https://{_public_host()}/d/pifs"
    if anchor in message:
        return message
    return message + "\n\n" + anchor


# Back-compat aliases. Both builders were module-private until the T-053 share hub
# needed the SAME prefill text and the SAME link form; a second copy in another module
# is exactly the drift `_tracked_link`'s own docstring warns about.
_tracked_link = tracked_link
_kit_message = kit_message


def handle_share_intent(
    *, tenant, channel: str, client_id: str, user_agent: str | None, lang: str = "en"
):
    """Resolve a /share/{channel}/{client_id} hit. Returns the destination URL.

    Raises Http404 for an unsupported/unlisted channel (never a silent "other"
    fallback — unlike the /r/ attribution tag, this gates which channels the
    endpoint actually SERVES). May raise the redirect_service PartnerUnavailable
    tuple (ReferralProgram.DoesNotExist / ProgramRedirectRule.DoesNotExist) when
    config resolution fails — the caller renders the branded 503, same as /r/.

    `lang` (T-062) selects the prefill's language twin; defaults to EN so every
    caller that omits it (tests, any future non-web caller) keeps behaving exactly
    as before. The view resolves the effective language (explicit `?lang=` else the
    referrer's stored language) and passes it in — this function does no resolution
    of its own.
    """
    if channel not in SHARE_INTENT_CHANNELS or channel not in _CHANNEL_TARGET_BUILDERS:
        raise Http404(f"unsupported share channel: {channel!r}")

    program = get_active_program(tenant)
    message = kit_message(channel, client_id, getattr(tenant, "id", None), program=program, lang=lang)
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
