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

from apps.config.cascade import resolve
from apps.events import vocab
from apps.events.bots import is_bot_user_agent
from apps.events.models import Event
from gorefer.flags import SHARE_CHANNEL_OTHER, SHARE_INTENT_CHANNELS, flags, normalize_share_channel

from .links import referral_path
from .redirect_service import get_active_program, lazy_get_or_create_referral

logger = logging.getLogger("gorefer.share_intent")


def build_whatsapp_target(message: str, link: str = "") -> str:
    """The WhatsApp share deep-link: a prefilled compose screen, no recipient."""
    return f"https://wa.me/?text={quote(message, safe='')}"


# Facebook, X, Telegram (owner decision 2026-11-02): plain web share intents, the SAME
# addresses the share hub's buttons already use (apps.accounts.hub._share_targets) — no
# SDK, no third-party script. Facebook takes only the link (it ignores prefilled text);
# X takes text only; Telegram takes both.
def build_facebook_target(message: str, link: str) -> str:
    return f"https://www.facebook.com/sharer/sharer.php?u={quote(link, safe='')}"


def build_x_target(message: str, link: str) -> str:
    return f"https://x.com/intent/post?text={quote(message, safe='')}"


def build_telegram_target(message: str, link: str) -> str:
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(message, safe='')}"


_CHANNEL_TARGET_BUILDERS = {
    "wa": build_whatsapp_target,
    "fb": build_facebook_target,
    "x": build_x_target,
    "tg": build_telegram_target,
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


def tracked_link(channel: str, client_id: str, *, tenant_id: int | None = None) -> str:
    # Full https URL, matching the selfview share builder. A scheme-less link is
    # not linkified by every client, and — observed live 2026-07-28 — it loses the
    # WhatsApp preview card to the disclosure URL (the message's only full URL),
    # so recipients saw a "Disclosures" headline instead of the referral landing.
    # The tracked link must be the FIRST full URL in the kit so the preview is the
    # PIFS-branded landing page. The path comes from the ONE link builder, so it
    # carries the program's link word (/zerodha/r/wa/{id}) when one is configured.
    return f"https://{_public_host()}{referral_path(client_id, channel=channel, tenant=tenant_id)}"


SHARE_KIT_MESSAGE_KEY = "share_kit_message_template"


def kit_message(
    channel: str,
    client_id: str,
    tenant_id: int | None,
    *,
    program=None,
    lang: str = "en",
    opener: str | None = None,
    link: str | None = None,
    en_template: str | None = None,
    anchor: str | None = None,
) -> str:
    """The share prefill, resolved through the config cascade (CLAUDE.md §6d).

    Five things fixed together here:

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
    5. T-064. `opener` is the referrer's OWN opening line (apps.accounts.opener),
       edited on the share hub. When set it REPLACES the official template — and only
       the template. See `_compose_with_opener` for why that can never cost the
       referrer their link or the reader their disclosure line.

    Callers that pass no `opener` (every non-web caller, and any referrer who has not
    personalized) get byte-identical output to the pre-T-064 build.

    `en_template` (EN only) and `anchor` let ONE caller — the one-tap WhatsApp link — use its
    own text and disclosure tail (owner 2026-11-04, see onetap_whatsapp_message). Every
    other caller omits both and gets exactly the output it got before.
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
    # A channel may carry its own English message (owner 2026-11-02: X allows 280
    # characters, so it gets a shorter one). Cascade key `share_kit_message_template__{ch}`;
    # blank/unset = the shared message above.
    if lang == "en" and str(en_template or "").strip():
        template = str(en_template)
    elif lang == "en":
        try:
            key = f"{SHARE_KIT_MESSAGE_KEY}__{channel}"
            override = str(resolve(key, tenant_id=tenant_id, default="") or "")
        except Exception:
            override = ""
        template = override.strip() or template
    brand = brand_for_program(program) if program is not None else brand_for_tenant_id(tenant_id)
    # `link` overrides the sharer's own credit link — only the Kite ID pop-up's "share
    # without my ID" path passes one (the no-referrer link); every other caller omits it.
    link = link or tracked_link(channel, client_id, tenant_id=tenant_id)
    anchor = anchor or disclosure_anchor()

    personal = str(opener or "").strip()
    if personal:
        return _compose_with_opener(personal, link, anchor)

    message = template.format(link=link, program_brand=brand)
    if anchor in message:
        return message
    return message + "\n\n" + anchor


def disclosure_url() -> str:
    """The public disclosure page every share message points at (§4.4 / ADR-031)."""
    return f"https://{_public_host()}/d/pifs"


def disclosure_anchor() -> str:
    """The compliance tail line appended to every share message (§4.4 / ADR-031).

    Named and exported so the T-064 composition and its tests refer to ONE definition
    of "the locked tail" rather than each restating the literal.
    """
    return f"Disclosures: {disclosure_url()}"


def _compose_with_opener(opener: str, link: str, anchor: str) -> str:
    """THE LOCKED COMPOSITION (T-064). Read this before changing anything about it.

        [ the referrer's own words ] + [ their credit link ] + [ the disclosure line ]

    The two trailing parts are CONCATENATED ON, unconditionally, in this order. They
    are never searched for inside the opener, never de-duplicated against it, and
    never templated through it. That is the whole security argument:

      * removal is impossible — there is no code path where a property of `opener`
        decides whether `link` or `anchor` is emitted;
      * reordering is impossible — position is fixed by this expression, not by
        anything parsed out of the text;
      * `{link}`-style format tricks are inert — `.format()` is applied to the
        OFFICIAL template only, never to referrer-supplied text;
      * newline flooding is already capped upstream (`apps.accounts.opener.sanitize`
        collapses blank runs), so the tail cannot be pushed behind a "Read more".

    Deliberately NOT reusing the official path's `if anchor in message` shortcut: that
    check exists so an operator who typed the disclosure into the template does not get
    it twice, and it is safe there because the template is operator-authored. Applied
    to referrer text it would become a control the referrer holds — type the anchor
    early, and the real tail stops being appended last. A duplicated line in the rare
    case someone pastes it is a cosmetic cost worth paying for an invariant that has no
    exceptions.
    """
    return f"{opener}\n{link}\n\n{anchor}"


# Back-compat aliases. Both builders were module-private until the T-053 share hub
# needed the SAME prefill text and the SAME link form; a second copy in another module
# is exactly the drift `_tracked_link`'s own docstring warns about.
_tracked_link = tracked_link
_kit_message = kit_message


def share_message_for(tenant, channel: str, client_id: str, *, program=None, lang: str = "en") -> str:
    """THE share message a referrer forwards for `channel` — the one-tap /share/ link and
    the My Referrals page both read it from here, so they can never disagree (found
    2026-11-02: My Referrals built its own text and ignored the owner's edited message).
    `program` defaults to the tenant's active program."""
    tenant_id = getattr(tenant, "id", None)
    return kit_message(
        channel, client_id, tenant_id,
        program=program if program is not None else get_active_program(tenant),
        lang=lang, opener=_opener_for(tenant_id, client_id),
    )


def _opener_for(tenant_id: int | None, client_id: str) -> str:
    """This client_id's saved personal opener, or "" — for the /share/ endpoint.

    Tenant-scoped (rail E-7) and read-only: an identity that does not exist yet simply
    has no opener. Imported lazily because `apps.accounts` imports this module for its
    share builders, and a module-level import would close that cycle.
    """
    from apps.accounts.opener import get_opener

    from .models import ReferralIdentity

    identity = (
        ReferralIdentity.objects.for_tenant(tenant_id)
        .filter(client_id=client_id, status="active", deleted_at__isnull=True)
        .first()
    )
    return get_opener(identity) if identity is not None else ""


def onetap_whatsapp_link(tenant) -> str | None:
    """The link the one-tap WhatsApp message carries, or None for the referrer's own link.

    Owner 2026-11-04: by default the program's plain no-referrer link, /{prefix}/open — the
    friend goes straight to the partner's sign-up page; PIFS is credited, the referrer is
    NOT (the owner assumes the lead was registered through the referral form first).
    Cascade key `share_onetap_wa_link` = "referrer" puts the referrer's own link back.
    """
    from apps.config.preferences import SHARE_ONETAP_WA_LINK_OPEN, resolve_onetap_wa_link

    from .links import partner_direct_path

    if resolve_onetap_wa_link(getattr(tenant, "id", None)) != SHARE_ONETAP_WA_LINK_OPEN:
        return None
    return f"https://{_public_host()}{partner_direct_path(tenant=tenant)}"


def onetap_whatsapp_disclosure(tenant_id: int | None) -> str:
    """The one-tap WhatsApp message's disclosure tail (default: bold heading, link on the
    next line). Falls back to the standard line if the configured text has no {url} or
    can't be filled — the disclosure link can never be configured away."""
    from apps.config.preferences import SHARE_ONETAP_WA_DISCLOSURE, SHARE_ONETAP_WA_DISCLOSURE_DEFAULT

    try:
        raw = str(resolve(SHARE_ONETAP_WA_DISCLOSURE, tenant_id=tenant_id,
                          default=SHARE_ONETAP_WA_DISCLOSURE_DEFAULT) or "")
        if "{url}" in raw:
            return raw.replace("{url}", disclosure_url())
    except Exception:
        pass
    return disclosure_anchor()


def _onetap_template(tenant_id: int | None, lang: str) -> str:
    """The configured one-tap text for `lang`. Hindi uses its own key; a blank or missing
    Hindi value falls back to the English text (the apps.config.i18n contract)."""
    from apps.config.preferences import (
        SHARE_ONETAP_WA_MESSAGE,
        SHARE_ONETAP_WA_MESSAGE_DEFAULT,
        SHARE_ONETAP_WA_MESSAGE_HI,
        SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT,
    )

    # The approved text is the built-in default, so it applies even before seed_program runs.
    def _get(key, default):
        try:
            return str(resolve(key, tenant_id=tenant_id, default=default) or "")
        except Exception:
            return default

    if lang == "hi":
        hi = _get(SHARE_ONETAP_WA_MESSAGE_HI, SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT)
        if hi.strip():
            return hi
    return _get(SHARE_ONETAP_WA_MESSAGE, SHARE_ONETAP_WA_MESSAGE_DEFAULT) or SHARE_ONETAP_WA_MESSAGE_DEFAULT


def onetap_register_link(tenant, client_id: str) -> str:
    """Step 1 of the one-tap message: the referrer's own wa link, or (no ID, "Share without
    my ID") the no-referrer register link whose path is the cascade key
    `share_onetap_wa_register_path` (default /r/wa)."""
    from apps.config.preferences import SHARE_ONETAP_WA_REGISTER_PATH, SHARE_ONETAP_WA_REGISTER_PATH_DEFAULT

    tenant_id = getattr(tenant, "id", None)
    if client_id:
        return tracked_link("wa", client_id, tenant_id=tenant_id)
    try:
        path = str(resolve(SHARE_ONETAP_WA_REGISTER_PATH, tenant_id=tenant_id,
                           default=SHARE_ONETAP_WA_REGISTER_PATH_DEFAULT) or "").strip()
    except Exception:
        path = ""
    path = path or SHARE_ONETAP_WA_REGISTER_PATH_DEFAULT
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{_public_host()}{path}"


def onetap_open_link(tenant) -> str:
    """Step 2 of the one-tap message: the program's plain partner-direct link."""
    from .links import partner_direct_path

    return f"https://{_public_host()}{partner_direct_path(tenant=tenant)}"


def onetap_whatsapp_message(
    tenant, client_id: str, *, program=None, lang: str = "en", opener: str | None = None,
    link: str | None = None,
) -> str:
    """THE message the one-tap WhatsApp link (/{prefix}/share/wa/{id}) pre-types (owner
    2026-11-04, two steps): step 1 = the register link, step 2 = the open link, then the
    risk line and the disclosure tail. English and Hindi have their own cascade texts; the
    shared message that My Referrals, the share hub and Telegram send is untouched. The
    referrer's own opening line still replaces the text (decision D2). `{link}` keeps
    working for a rollback to the single-link text: it is `link`, else the open link
    (or the referrer's own link when share_onetap_wa_link = "referrer"). An empty
    `client_id` is "Share without my ID"."""
    from .branding import brand_for_program, brand_for_tenant_id

    tenant_id = getattr(tenant, "id", None)
    program = program if program is not None else get_active_program(tenant)
    anchor = onetap_whatsapp_disclosure(tenant_id)
    single = link or onetap_whatsapp_link(tenant)
    if opener is not None and str(opener).strip():
        return kit_message(
            "wa", client_id, tenant_id, program=program, lang=lang, opener=opener,
            link=single, anchor=anchor,
        )
    brand = brand_for_program(program) if program is not None else brand_for_tenant_id(tenant_id)
    template = _onetap_template(tenant_id, lang)
    fields = {
        "link": single or tracked_link("wa", client_id, tenant_id=tenant_id),
        "register_link": onetap_register_link(tenant, client_id),
        "open_link": onetap_open_link(tenant),
        "program_brand": brand,
    }
    try:
        message = template.format(**fields)
    except (KeyError, ValueError, IndexError):
        # A bad value written outside the Preferences validator (e.g. Django admin) must
        # never 500 the share link: fall back to the built-in text for this language.
        from apps.config.preferences import (
            SHARE_ONETAP_WA_MESSAGE_DEFAULT,
            SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT,
        )

        logger.warning("one-tap WhatsApp template not renderable; using built-in default (lang=%s)", lang)
        default = SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT if lang == "hi" else SHARE_ONETAP_WA_MESSAGE_DEFAULT
        message = default.format(**fields)
    if anchor in message:
        return message
    return message + "\n\n" + anchor


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
    tenant_id = getattr(tenant, "id", None)

    # T-064: the one-tap endpoint must forward the SAME message the hub shows, so it
    # reads the referrer's personal opener too. Resolved from the already-existing
    # identity only — this lookup never creates one, so a bot hit (handled below) and
    # a first-ever share still behave exactly as they did before.
    if channel == "wa":
        # The one-tap WhatsApp link has its own message and link (owner 2026-11-04).
        link = onetap_whatsapp_link(tenant) or tracked_link(channel, client_id, tenant_id=tenant_id)
        message = onetap_whatsapp_message(
            tenant, client_id, program=program, lang=lang,
            opener=_opener_for(tenant_id, client_id), link=link,
        )
    else:
        message = share_message_for(tenant, channel, client_id, program=program, lang=lang)
        link = tracked_link(channel, client_id, tenant_id=tenant_id)
    destination = _CHANNEL_TARGET_BUILDERS[channel](message, link)

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


def is_share_channel_served(channel: str) -> bool:
    """True when /share/{channel}/... actually serves `channel` (same gate as below)."""
    return channel in SHARE_INTENT_CHANNELS and channel in _CHANNEL_TARGET_BUILDERS


def handle_share_without_id(*, tenant, channel: str, user_agent: str | None, lang: str = "en"):
    """The Kite ID pop-up's "Share without my ID" (owner 2026-11-02). Returns the destination.

    Same share message as /share/{channel}/{client_id}, but the link inside is the
    program's no-referrer link (/{prefix}/r/open), so the friend still gets a working link
    and nobody is credited. Records a PII-free share_intent on the partner-direct journey;
    creates NO referrer identity. Raises Http404 for a channel the endpoint doesn't serve.
    """
    if not is_share_channel_served(channel):
        raise Http404(f"unsupported share channel: {channel!r}")

    from .links import referral_path
    from .redirect_service import RESERVED_OPEN, _get_or_create_partner_direct_referral

    program = get_active_program(tenant)
    tenant_id = getattr(tenant, "id", None)
    if channel == "wa":
        # Decision D1 (owner 2026-11-04): the one-tap WhatsApp message and link, as with an ID.
        link = (onetap_whatsapp_link(tenant)
                or f"https://{_public_host()}{referral_path(RESERVED_OPEN, tenant=tenant)}")
        message = onetap_whatsapp_message(tenant, "", program=program, lang=lang, link=link)
    else:
        link = f"https://{_public_host()}{referral_path(RESERVED_OPEN, tenant=tenant)}"
        message = kit_message(channel, "", tenant_id, program=program, lang=lang, link=link)
    destination = _CHANNEL_TARGET_BUILDERS[channel](message, link)

    if is_bot_user_agent(user_agent):
        return destination

    referral = _get_or_create_partner_direct_referral(tenant, program)
    transaction.on_commit(
        lambda: Event.objects.create(
            tenant=tenant,
            event_type=vocab.SHARE_INTENT,
            source=vocab.SRC_WATI,
            referral=referral,
            user_type="anonymous",
            user_agent=user_agent or "",
            is_bot=False,
            person_ref_id=None,
            metadata={"channel": normalize_share_channel(channel) or SHARE_CHANNEL_OTHER, "without_id": True},
        )
    )
    return destination
