"""Referral landing + redirect views (M3 evolves M2 per ADR-002).

- GET /r/{client_id}          -> render the PIFS-branded landing (200); log
  landing_viewed; mint a beacon nonce; the M2 gr_vid cookie/journey continues.
- GET /r/{client_id}/continue -> the "Continue to Zerodha" action: 302 to the
  server-side-assembled Zerodha URL (reuses the M2 engine; emits redirect_completed).
- GET /open                   -> partner-direct: stays a DIRECT 302 (no landing).

Guardrails: redirect only (never submit Zerodha's form); the raw URL / partner
code never appear in the rendered landing body (only in the 302 Location).
"""
from __future__ import annotations

import uuid
from urllib.parse import quote

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.config.cascade import resolve
from apps.events import vocab
from apps.events.bots import is_bot_user_agent
from apps.events.models import Event
from apps.referrals.og import render_preview
from apps.tenants.resolve import get_current_tenant
from gorefer import flags as flagmod
from gorefer.flags import flags, normalize_share_channel

from .landing_mode import LANDING_MODE_DIRECT, resolve_landing_mode
from .links import matches_program_prefix, referral_path, share_path
from .models import ProgramRedirectRule, ReferralIdentity, ReferralProgram
from .redirect_service import (
    build_continue_redirect,
    handle_direct_redirect,
    handle_landing_view,
    handle_partner_direct,
    handle_partner_referral_page_redirect,
    is_channel_code,
    is_reserved_open,
)
from .share_intent_service import handle_share_intent, handle_share_without_id, is_share_channel_served
from .validators import (
    DeletedClientId,
    InvalidClientId,
    active_partner_code,
    is_placeholder_id,
    resolve_client_id_length,
    validate_link_client_id,
)

VISITOR_COOKIE = "gr_vid"
# 60 days — matches the API spec (06 §4.1) AND Zerodha's 60-day attribution window, so
# a journey is stitched across exactly the eligible period, no longer (Fable5 M11 #6).
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 60

# Config-resolution failures that mean "destination can't be built" (06-API §4.1).
PartnerUnavailable = (ReferralProgram.DoesNotExist, ProgramRedirectRule.DoesNotExist)


def _partner_unavailable(request):
    """Branded 503 PARTNER_UNAVAILABLE — never a raw 500 (06-API §4.1)."""
    return render(request, "partner_unavailable.html", status=503)


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _share_channel(request, path_channel: str | None = None) -> str | None:
    """Resolve the visitor's share channel to a Channel label (M11 + B1/ADR-028).

    Two carriers, both normalized the same way (config-driven codes -> labels):
      - PATH PREFIX `/r/{channel}/{client_id}` (B1) — WhatsApp dynamic URL buttons
        require the template variable LAST, so `?s=wa` can't follow `{{client_id}}`;
        the channel therefore rides as a leading path segment. Takes precedence.
      - `?s=` query param (M11 legacy) — the param NAME is config
        (SHARE_CHANNEL_PARAM, default "s").

    Either way the value is captured for attribution ONLY, then never propagated to
    the 302 — the destination is assembled server-side from the program template, so
    the channel/`s` cannot leak into the Location.
    """
    if path_channel is not None:
        return normalize_share_channel(path_channel)
    raw = request.GET.get(flagmod.SHARE_CHANNEL_PARAM)
    return normalize_share_channel(raw)


def _ensure_visitor_id(request) -> tuple[str, bool]:
    existing = request.COOKIES.get(VISITOR_COOKIE)
    if existing:
        return existing, False
    return uuid.uuid4().hex, True


def _set_visitor_cookie(response, visitor_id: str, is_new: bool):
    if is_new:
        response.set_cookie(
            VISITOR_COOKIE, visitor_id, max_age=VISITOR_COOKIE_MAX_AGE, httponly=True, samesite="Lax"
        )


def _og_context(request, client_id: str) -> dict:
    """Config-driven Open Graph / Twitter-Card meta for the forwarded /r/{id} card (M11).

    Absolute og:url / og:image (Open Graph requires absolute URLs), built from
    PUBLIC_BASE_URL. GUARDRAIL: carries NO partner code and NO raw Zerodha URL, and
    must not resemble/clone Zerodha — the copy is PIFS-branded and generic.
    """
    from django.conf import settings

    from apps.referrals import og
    from apps.referrals.og import absolute_image_url

    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    tenant = get_current_tenant(request)
    og_url = f"{base}{referral_path(client_id, tenant=tenant)}"
    tenant_id = getattr(tenant, "id", None)
    if og.v2_enabled(tenant_id):
        # v2 (owner 2026-11-03): the same generic card the crawler page serves, so the two
        # cards cannot drift. Never named here — only the crawler bot branch names.
        meta = og.v2_meta(tenant_id, tenant=tenant)
        return {key: meta[key] for key in ("og_title", "og_description", "og_image", "og_site_name")} | {
            "og_url": og_url}
    # ONE canonical absolute-OG-image builder, shared with the D2 crawler card — the
    # crawler card shipped with a relative og:image because it did not reuse this.
    image = absolute_image_url(settings.OG_IMAGE)
    return {
        "og_title": settings.OG_TITLE,
        "og_description": settings.OG_DESCRIPTION,
        "og_image": image,
        "og_url": f"{base}{referral_path(client_id, tenant=get_current_tenant(request))}",
        "og_site_name": settings.OG_SITE_NAME,
    }


def _landing_context(request, tenant, client_id: str, nonce: str | None):
    """Config-driven landing context (no referrer NAME in initial HTML — #1/#3).

    The WhatsApp deep link is built client-side (landing.js) at click time from the
    config-driven WATI business number + the referral id + whatever the prospect
    typed into the form (name/phone/email), so only the number is passed here.
    """
    from apps.config import preferences as prefkeys

    tenant_id = tenant.id if tenant is not None else None
    prefs = prefkeys.get_preferences(tenant_id)
    wa_number = prefs[prefkeys.WATI_BUSINESS_NUMBER]
    # Reward wording is tenant-configurable via the Preferences screen (Q-M-PREF): the
    # tenant's REFERRER_REWARD_CLAIM when "show referrer reward" is on, else hidden. The
    # compliance-LOCKED incentive claim (flags) remains the central fallback / audit copy.
    show_reward = prefs[prefkeys.SHARE_SHOW_REWARD]
    reward_claim = prefs[prefkeys.REFERRER_REWARD_CLAIM] or flags.REFERRAL_INCENTIVE_CLAIM
    ctx = {
        "client_id": client_id,
        "nonce": nonce or "",
        "wati_business_number": wa_number,
        # Override the context-processor globals with the tenant's configured helpline
        # (Preferences screen wins over the settings default). tel: form strips spaces.
        "SUPPORT_HELPLINE_PHONE": prefs[prefkeys.SUPPORT_HELPLINE_PHONE],
        "SUPPORT_HELPLINE_TEL": (prefs[prefkeys.SUPPORT_HELPLINE_PHONE] or "").replace(" ", ""),
        "privacy_policy_url": resolve("privacy_policy_url", tenant_id=tenant_id, default="/privacy"),
        "REFERRAL_INCENTIVE_CLAIM": reward_claim if show_reward else "",
        "show_incentive": show_reward,  # tenant may hide the referral-benefit panel
    }
    ctx.update(_og_context(request, client_id))
    return ctx


def _partner_referral_page_response(request, tenant, channel: str | None):
    """/r/open, and the referral pop-up's Skip: 302 to the partner's referral page (empty
    box, partner code server-side), no identity; crawlers get the PIFS card."""
    if is_bot_user_agent(request.META.get("HTTP_USER_AGENT", "")):
        return render_preview(request, tenant_id=getattr(tenant, "id", None))
    visitor_id, is_new = _ensure_visitor_id(request)
    try:
        destination, _human = handle_partner_referral_page_redirect(
            tenant=tenant, visitor_id=visitor_id,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            raw_ip=_client_ip(request), share_channel=_share_channel(request, channel),
        )
    except PartnerUnavailable:
        return _partner_unavailable(request)
    response = HttpResponseRedirect(destination)
    _set_visitor_cookie(response, visitor_id, is_new)
    return response


@require_GET
def referral_redirect(request, client_id: str, channel: str | None = None):
    """GET /r/{client_id} (or /r/{channel}/{client_id}) — render the branded landing.

    `channel` (B1) is an optional path prefix carrying the share channel (e.g.
    /r/wa/RJ4521) for WhatsApp URL buttons where `?s=` can't trail the id. Legacy
    /r/{client_id}?s= still works — see _share_channel.
    """
    tenant = get_current_tenant(request)
    if is_reserved_open(client_id):  # /r/open - checked BEFORE validation (T-574)
        # Owner 2026-11-02: NO pop-up here — /r/open is the deliberate no-referrer link
        # (the live prospect-invite template sends people to it), so it stays a direct 302
        # to the partner referral page, exactly as before.
        return _partner_referral_page_response(request, tenant, channel)
    if channel is None and is_channel_code(client_id):
        # /r/wa, /r/yt (owner 2026-10-29): a bare channel code is a channel-only link, not a
        # referrer id - same as /r/{channel}/open, recording the channel.
        return _kite_prompt_response(request, tenant, mode=PROMPT_REFERRAL, channel=client_id)
    try:
        # STRICT, per-partner (owner decision 2026-07-27): this path CREATES an identity,
        # so a leaked chatbot label like `TALK` — or the partner code `ZMPHZC` itself —
        # must never become a referrer. Lookup paths keep the loose spec rule.
        normalized = validate_link_client_id(tenant, client_id)
    except InvalidClientId:
        # Owner 2026-11-02 (replaces the T-574 pass-through): a missing, malformed or
        # placeholder id asks for the real Kite ID instead; Skip keeps the old /r/open path.
        return _kite_prompt_response(request, tenant, mode=PROMPT_REFERRAL, channel=channel)

    # D2 — a CRAWLER gets a PIFS link-preview card, never a 302.
    #
    # A forwarded link used to redirect the crawler too, so WhatsApp built its preview from
    # the partner's page and every shared link showed the partner's branding instead of
    # PIFS's — on the one surface a friend sees before tapping. Checked BEFORE visitor-cookie
    # issuance and before any journey work, so a preview fetch still creates nothing.
    if is_bot_user_agent(request.META.get("HTTP_USER_AGENT", "")):
        # v2 (owner 2026-11-03): the ONLY caller that passes the id, so only a referral
        # link can carry the referrer's first name; every other preview is generic.
        return render_preview(request, tenant_id=getattr(tenant, "id", None),
                              client_id=normalized, tenant=tenant)

    visitor_id, is_new = _ensure_visitor_id(request)

    # LANDING_MODE=direct (B3): log the click on-commit, then 302 straight to
    # Zerodha — skip the landing page. Channel/?s stripped, code server-side.
    if resolve_landing_mode(tenant.id if tenant is not None else None) == LANDING_MODE_DIRECT:
        try:
            destination, _is_human = handle_direct_redirect(
                tenant=tenant,
                client_id=normalized,
                visitor_id=visitor_id,
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                raw_ip=_client_ip(request),
                share_channel=_share_channel(request, channel),
            )
        except PartnerUnavailable:
            return _partner_unavailable(request)
        response = HttpResponseRedirect(destination)
        _set_visitor_cookie(response, visitor_id, is_new)
        return response

    try:
        _referral, _event, nonce = handle_landing_view(
            tenant=tenant,
            client_id=normalized,
            visitor_id=visitor_id,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            raw_ip=_client_ip(request),
            share_channel=_share_channel(request, channel),
        )
    except PartnerUnavailable:
        return _partner_unavailable(request)
    context = _landing_context(request, tenant, normalized, nonce)
    response = render(request, "landing.html", context)
    _set_visitor_cookie(response, visitor_id, is_new)
    return response


@require_GET
def channel_only_redirect(request, channel: str):
    """GET /r/{channel}/ (owner 2026-10-29) - a channel link with no client id. Since
    2026-11-02 it shows the Kite ID pop-up (Skip = the /r/open destination)."""
    if not is_channel_code(channel):  # converter takes any 1-8 letters; only KNOWN codes act
        raise Http404("unknown channel")
    return _kite_prompt_response(request, get_current_tenant(request), mode=PROMPT_REFERRAL, channel=channel)


@require_GET
def referral_continue(request, client_id: str, channel: str | None = None):
    """GET /r/{client_id}/continue (or /r/{channel}/{client_id}/continue) — the
    Continue-to-Zerodha 302 (reuses M2 engine). `channel` is the optional B1 path
    prefix; captured for attribution, NEVER added to the Location."""
    tenant = get_current_tenant(request)
    if is_reserved_open(client_id):  # no pop-up on /r/open (owner 2026-11-02)
        return _partner_referral_page_response(request, tenant, channel)
    try:
        # STRICT, per-partner — this path lazily creates the identity too.
        normalized = validate_link_client_id(tenant, client_id)
    except InvalidClientId:
        return _kite_prompt_response(request, tenant, mode=PROMPT_REFERRAL, channel=channel)
    identity = ReferralIdentity.objects.for_tenant(tenant).filter(
        client_id=normalized, id_source="native"
    ).first()
    referral = identity.referrals.filter(source="referral_link").order_by("id").first() if identity else None
    try:
        destination = build_continue_redirect(
            tenant=tenant, client_id=normalized, referral=referral,
            share_channel=_share_channel(request, channel),
        )
    except PartnerUnavailable:
        return _partner_unavailable(request)
    # Guardrail (M11): the destination is assembled server-side from the program
    # template — the inbound ?s= is captured for attribution but NEVER appears here.
    return HttpResponseRedirect(destination)


@require_GET
def disclosure_page(request, slug: str):
    """GET /d/{slug} — the public per-sub-broker disclosure page (B2 / ADR-031).

    Composes each active partner's regulator-mandated disclosure block for the tenant
    identified by `slug` (e.g. /d/pifs), in regulator order (SEBI/NSE → IRDAI → RBI).
    The canonical §4.4 host: a light WhatsApp message / `direct` bypass link points
    here for the full disclosures. NO PII; NO partner code / raw Zerodha URL; creates
    no event, so a crawler hit is inherently excluded from human counts.
    """
    from apps.referrals.disclosure_service import compose_disclosures, resolve_tenant_by_slug

    tenant = resolve_tenant_by_slug(slug)
    if tenant is None:
        return render(request, "disclosure_unknown.html", {"slug": slug}, status=404)
    blocks = compose_disclosures(tenant)
    context = {
        "slug": slug,
        "sub_broker_name": tenant.name,
        "disclosure_blocks": blocks,
    }
    return render(request, "disclosure.html", context)


@require_GET
def share_intent_redirect(request, channel: str, client_id: str):
    """GET /share/{channel}/{client_id} — the one-tap share endpoint (M-WATI-1).

    Only reachable when `ENABLE_SHARE_INTENT` is on (gorefer/urls.py registers the
    route conditionally, per Constitution §4 — no dead UI when off). Builds the
    channel's share deep-link (launch: WhatsApp) with a prefilled kit message
    carrying the tracked `/r/{channel}/{client_id}` link, records a PII-free
    `share_intent` event, then 302s. Unsupported channel -> 404; a missing, malformed
    or placeholder client_id -> the Kite ID pop-up; unresolvable partner config -> the
    same branded 503 as `/r/`.
    """
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseNotFound

    try:
        check_rate("share", client_ip(request),
                   limit=settings.RATELIMIT_SHARE_MAX, window=settings.RATELIMIT_API_WINDOW)
    except RateLimited as exc:
        return HttpResponse(status=429, headers={"Retry-After": str(exc.retry_after)})

    from apps.config.i18n import resolve_lang_or_stored

    tenant = get_current_tenant(request)
    if not is_share_channel_served(channel):
        return HttpResponseNotFound()  # unsupported channel stays a 404, before any prompt
    try:
        # STRICT, per-partner — this path lazily creates the identity too.
        normalized = validate_link_client_id(tenant, client_id)
    except InvalidClientId:
        # Owner 2026-11-02: a malformed or placeholder id asks the sharer for their Kite ID.
        return _kite_prompt_response(request, tenant, mode=PROMPT_SHARE, channel=channel)
    # T-062: explicit ?lang= always wins; otherwise the referrer's stored language.
    lang = resolve_lang_or_stored(request, getattr(tenant, "id", None))
    try:
        destination = handle_share_intent(
            tenant=tenant,
            channel=channel,
            client_id=normalized,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            lang=lang,
        )
    except Http404:
        return HttpResponseNotFound()
    except PartnerUnavailable:
        return _partner_unavailable(request)
    return HttpResponseRedirect(destination)


@require_GET
def partner_direct_redirect(request):
    """GET /open — partner-direct 302 (no r=); stays a direct redirect (no landing)."""
    tenant = get_current_tenant(request)
    # D2 — crawlers get the PIFS card here too; /open is shared as often as a referral link.
    if is_bot_user_agent(request.META.get("HTTP_USER_AGENT", "")):
        return render_preview(request, tenant_id=getattr(tenant, "id", None))
    visitor_id, is_new = _ensure_visitor_id(request)
    try:
        destination, _is_human = handle_partner_direct(
            tenant=tenant,
            visitor_id=visitor_id,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            raw_ip=_client_ip(request),
            share_channel=_share_channel(request),
        )
    except PartnerUnavailable:
        return _partner_unavailable(request)
    response = HttpResponseRedirect(destination)
    _set_visitor_cookie(response, visitor_id, is_new)
    return response


def _share_recovery_context(tenant_id: int | None) -> dict:
    """Config-driven copy + wa.me CTA for the soft-landing recovery page (T-122).

    Reuses `WATI_BUSINESS_NUMBER` (already a cascade key) rather than duplicating
    the business number under a new key. Every other string is its own cascade key
    (rail E-6 / §6d) so the copy can be reworded without a deploy; defaults equal
    the shipped literals, so an unseeded database renders identically.
    """
    from django.conf import settings

    from apps.config import preferences as prefkeys

    wa_number = resolve(
        prefkeys.WATI_BUSINESS_NUMBER, tenant_id=tenant_id, default=settings.WATI_BUSINESS_NUMBER
    )
    return {
        "headline": resolve(
            prefkeys.SHARE_RECOVERY_HEADLINE,
            tenant_id=tenant_id,
            default=prefkeys.SHARE_RECOVERY_HEADLINE_DEFAULT,
        ),
        "body": resolve(
            prefkeys.SHARE_RECOVERY_BODY, tenant_id=tenant_id, default=prefkeys.SHARE_RECOVERY_BODY_DEFAULT
        ),
        "button_label": resolve(
            prefkeys.SHARE_RECOVERY_BUTTON_LABEL,
            tenant_id=tenant_id,
            default=prefkeys.SHARE_RECOVERY_BUTTON_LABEL_DEFAULT,
        ),
        "wa_link": _share_recovery_wa_link(wa_number, tenant_id),
    }


def _share_recovery_wa_link(wa_number: str, tenant_id: int | None) -> str:
    """The `https://wa.me/{number}?text=...` deep link — the page's ONE primary CTA."""
    from apps.config import preferences as prefkeys

    prefill = resolve(
        prefkeys.SHARE_RECOVERY_PREFILL, tenant_id=tenant_id, default=prefkeys.SHARE_RECOVERY_PREFILL_DEFAULT
    )
    digits = "".join(ch for ch in (wa_number or "") if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(prefill, safe='')}"


@require_GET
def share_recovery_view(request, channel: str | None = None):
    """GET /share/{channel}/ (or bare), GET /r/, GET /r — the soft-landing recovery
    page (T-122) for a share/acquisition link whose `client_id` fell out (a Zoho
    field-mapping bug sent WhatsApp URL buttons with a blank `{{client_id}}`).

    Always HTTP 200 (never a 404) so an already-delivered broken link keeps working
    for as long as it sits in someone's chat history. NO login, NO form, NO journey/
    identity created — this is a pure informational page whose ONE action is a
    `wa.me` deep link back to the WATI business number. Query strings (fbclid etc.)
    never reach here at all — Django path matching ignores them.
    """
    tenant = get_current_tenant(request)
    tenant_id = tenant.id if tenant is not None else None
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if not is_bot_user_agent(user_agent):
        Event.objects.create(
            tenant=tenant,
            event_type=vocab.SHARE_RECOVERY_VIEWED,
            source=vocab.SRC_SYSTEM,
            referral=None,
            user_type="anonymous",
            user_agent=user_agent,
            is_bot=False,
            person_ref_id=None,
            metadata={"channel": normalize_share_channel(channel) if channel else ""},
        )
    context = _share_recovery_context(tenant_id)
    return render(request, "share_recovery.html", context, status=200)


@require_GET
def privacy_policy_view(request):
    """GET /privacy — public, no-login DPDP privacy policy (T-148).

    The landing form's consent checkbox links here (`privacy_policy_url`, a
    cascade-resolved config key — rail E-6). Extends `landing_base.html` so the
    AP disclosure block + market-risk warning auto-inject like every other
    customer-facing page. Every claim on the page is grounded in code that
    actually runs: `apps/common/privacy.py` (erase/purge), `VisitorPII` as the
    separate erasable IP/city record, and the PII-free immutable event log.
    """
    from django.conf import settings

    from apps.config import preferences as prefkeys

    tenant = get_current_tenant(request)
    tenant_id = tenant.id if tenant is not None else None
    wa_number = resolve(
        prefkeys.WATI_BUSINESS_NUMBER, tenant_id=tenant_id, default=settings.WATI_BUSINESS_NUMBER
    )
    digits = "".join(ch for ch in (wa_number or "") if ch.isdigit())
    wa_display = f"+91 {digits[-10:-5]} {digits[-5:]}" if len(digits) >= 10 else wa_number
    context = {
        "wati_business_number_display": wa_display,
        "wati_business_number_digits": digits,
    }
    return render(request, "privacy_policy.html", context)


# ---------------------------------------------------------------------------
# Kite ID pop-up (owner decision 2026-11-02). Every referral or share link whose id is
# missing, malformed or an obvious placeholder (/r/wa/KITEID, /r/wa/, /r/,
# /share/wa/YOUR_KITE_ID, /share/wa/ and every /{program}/ twin) renders ONE page: a
# PIFS-branded pop-up asking for the Kite ID. It is a plain GET form posting back to the
# SAME URL, so it works with no JavaScript and every link shape keeps its own address:
#   ?kite_id=AB1234 -> validated with the same strict rule as the link itself, then a 302
#                      to the canonical link (/{program}/r/[ch/]AB1234 or
#                      /{program}/share/{ch}/AB1234), which records the click as before;
#   ?skip=1         -> referral links: the old /r/open path (partner referral page, empty
#                      box, partner code server-side, no referrer); share links: the share
#                      message carrying the no-referrer link.
# Crawlers still get the PIFS preview card and nothing is recorded for them.
# ---------------------------------------------------------------------------
PROMPT_REFERRAL = "referral"
PROMPT_SHARE = "share"
KITE_ID_PARAM = "kite_id"
SKIP_PARAM = "skip"
# Server-side bound on what is ECHOED back into the box after a bad entry. It is NOT the
# box's length: that is the partner's id length from config (resolve_client_id_length),
# and the server never truncates an id to it — a too-long id is rejected, not shortened.
KITE_ID_INPUT_MAX = 32


def _kite_prompt_copy(tenant_id: int | None, mode: str, channel: str | None = None) -> dict:
    """Config-driven pop-up wording (rail E-6 / §6d). `{program_brand}` and `{channel}` (the
    share platform's name) are substituted by plain replacement, so a stray brace in
    operator copy can never break the page."""
    from apps.config import preferences as prefkeys

    from .branding import brand_for_tenant_id

    brand = brand_for_tenant_id(tenant_id) or ""
    channel_name = normalize_share_channel(channel) or ""

    def text(key, default):
        value = resolve(key, tenant_id=tenant_id, default=default)
        return str(value or default).replace("{program_brand}", brand).replace("{channel}", channel_name)

    if mode == PROMPT_SHARE:
        keys = {
            "title": (prefkeys.KITE_PROMPT_SHARE_TITLE, prefkeys.KITE_PROMPT_SHARE_TITLE_DEFAULT),
            "text": (prefkeys.KITE_PROMPT_SHARE_TEXT, prefkeys.KITE_PROMPT_SHARE_TEXT_DEFAULT),
            "label": (prefkeys.KITE_PROMPT_SHARE_LABEL, prefkeys.KITE_PROMPT_SHARE_LABEL_DEFAULT),
            "button": (prefkeys.KITE_PROMPT_SHARE_BUTTON, prefkeys.KITE_PROMPT_SHARE_BUTTON_DEFAULT),
            "skip": (prefkeys.KITE_PROMPT_SHARE_SKIP, prefkeys.KITE_PROMPT_SHARE_SKIP_DEFAULT),
            "foot": (prefkeys.KITE_PROMPT_SHARE_FOOT, prefkeys.KITE_PROMPT_SHARE_FOOT_DEFAULT),
        }
    else:
        keys = {
            "title": (prefkeys.KITE_PROMPT_REF_TITLE, prefkeys.KITE_PROMPT_REF_TITLE_DEFAULT),
            "text": (prefkeys.KITE_PROMPT_REF_TEXT, prefkeys.KITE_PROMPT_REF_TEXT_DEFAULT),
            "label": (prefkeys.KITE_PROMPT_REF_LABEL, prefkeys.KITE_PROMPT_REF_LABEL_DEFAULT),
            "button": (prefkeys.KITE_PROMPT_REF_BUTTON, prefkeys.KITE_PROMPT_REF_BUTTON_DEFAULT),
            "skip": (prefkeys.KITE_PROMPT_REF_SKIP, prefkeys.KITE_PROMPT_REF_SKIP_DEFAULT),
            "foot": (prefkeys.KITE_PROMPT_REF_FOOT, prefkeys.KITE_PROMPT_REF_FOOT_DEFAULT),
        }
    keys.update({
        "hint": (prefkeys.KITE_PROMPT_HINT, prefkeys.KITE_PROMPT_HINT_DEFAULT),
        "error_empty": (prefkeys.KITE_PROMPT_ERROR_EMPTY, prefkeys.KITE_PROMPT_ERROR_EMPTY_DEFAULT),
        "error_shape": (prefkeys.KITE_PROMPT_ERROR_SHAPE, prefkeys.KITE_PROMPT_ERROR_SHAPE_DEFAULT),
        "error_placeholder": (
            prefkeys.KITE_PROMPT_ERROR_PLACEHOLDER, prefkeys.KITE_PROMPT_ERROR_PLACEHOLDER_DEFAULT
        ),
    })
    return {name: text(key, default) for name, (key, default) in keys.items()}


def _kite_prompt_response(request, tenant, *, mode: str, channel: str | None = None):
    """Render (or act on) the Kite ID pop-up for a link whose id is unusable."""
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseNotFound

    user_agent = request.META.get("HTTP_USER_AGENT", "")
    tenant_id = getattr(tenant, "id", None)
    if is_bot_user_agent(user_agent):  # preview fetch: the PIFS card, never the pop-up
        return render_preview(request, tenant_id=tenant_id)

    if SKIP_PARAM in request.GET:
        if mode == PROMPT_REFERRAL:
            # Exactly the old /r/open path: partner referral page, empty box, partner code
            # injected server-side, click on the partner-direct journey, no referrer.
            return _partner_referral_page_response(request, tenant, channel)
        try:
            check_rate("share", client_ip(request),
                       limit=settings.RATELIMIT_SHARE_MAX, window=settings.RATELIMIT_API_WINDOW)
        except RateLimited as exc:
            return HttpResponse(status=429, headers={"Retry-After": str(exc.retry_after)})
        from apps.config.i18n import resolve_lang_or_stored

        try:
            destination = handle_share_without_id(
                tenant=tenant, channel=channel or "", user_agent=user_agent,
                lang=resolve_lang_or_stored(request, tenant_id),
            )
        except Http404:
            return HttpResponseNotFound()
        except PartnerUnavailable:
            return _partner_unavailable(request)
        return HttpResponseRedirect(destination)

    copy = _kite_prompt_copy(tenant_id, mode, channel)
    error = ""
    entered = ""
    if KITE_ID_PARAM in request.GET:
        entered = "".join((request.GET.get(KITE_ID_PARAM) or "").split())[:KITE_ID_INPUT_MAX]
        if not entered:
            error = copy["error_empty"]
        else:
            try:
                normalized = validate_link_client_id(tenant, entered)
            except DeletedClientId:
                # A soft-deleted (junk/test) id: same message as a placeholder word.
                error = copy["error_placeholder"]
            except InvalidClientId:
                cleaned = "".join(ch for ch in entered if ch.isalnum()).upper()
                placeholder = is_placeholder_id(tenant_id, cleaned)
                error = copy["error_placeholder"] if placeholder else copy["error_shape"]
            else:
                if mode == PROMPT_SHARE:
                    return HttpResponseRedirect(share_path(channel, normalized, tenant=tenant))
                return HttpResponseRedirect(referral_path(normalized, channel=channel, tenant=tenant))
    else:
        # First view only (not each retry). Reuses the T-122 recovery event, which the
        # daily digest counts: this pop-up is now where an id-less link lands.
        Event.objects.create(
            tenant=tenant,
            event_type=vocab.SHARE_RECOVERY_VIEWED,
            source=vocab.SRC_SYSTEM,
            referral=None,
            user_type="anonymous",
            user_agent=user_agent,
            is_bot=False,
            person_ref_id=None,
            metadata={"channel": normalize_share_channel(channel) if channel else "", "prompt": mode},
        )
    context = {
        "copy": copy,
        "mode": mode,
        "channel": channel or "",
        "error": error,
        "entered": entered,
        "kite_id_param": KITE_ID_PARAM,
        "skip_url": f"{request.path}?{SKIP_PARAM}=1",
        "input_max": resolve_client_id_length(tenant_id, active_partner_code(tenant)),
    }
    return render(request, "kite_prompt.html", context, status=200)


@require_GET
def referral_prompt_view(request):
    """GET /r/ and /r (no id at all) — the Kite ID pop-up (replaced the T-122 help page)."""
    return _kite_prompt_response(request, get_current_tenant(request), mode=PROMPT_REFERRAL)


@require_GET
def share_prompt_view(request, channel: str):
    """GET /share/{channel}/ and /share/{channel} — the sharer's Kite ID pop-up. A channel
    the share endpoint doesn't serve keeps the T-122 help page (the pop-up would lead to a
    404 once an id is entered)."""
    if not is_share_channel_served(channel):
        return share_recovery_view(request, channel=channel)
    return _kite_prompt_response(request, get_current_tenant(request), mode=PROMPT_SHARE, channel=channel)


# ---------------------------------------------------------------------------
# Program-prefixed twins (owner decision 2026-10-29): /{url_prefix}/open,
# /{url_prefix}/r/[{channel}/]{client_id}[/continue], /{url_prefix}/r[/]. Each one
# checks that the prefix is the active program's link word (data on ReferralProgram,
# e.g. `zerodha`) and then hands off to the SAME view as its bare twin — so landing,
# redirect, attribution and every guardrail are shared, not copied. An unknown word
# is a 404. The bare routes are untouched.
# ---------------------------------------------------------------------------
def _require_program_prefix(request, program_prefix: str) -> None:
    if not matches_program_prefix(get_current_tenant(request), program_prefix):
        raise Http404("unknown program link prefix")


@require_GET
def prefixed_partner_direct_redirect(request, program_prefix: str):
    _require_program_prefix(request, program_prefix)
    return partner_direct_redirect(request)


@require_GET
def prefixed_referral_redirect(request, program_prefix: str, client_id: str, channel: str | None = None):
    _require_program_prefix(request, program_prefix)
    return referral_redirect(request, client_id, channel=channel)


@require_GET
def prefixed_channel_only_redirect(request, program_prefix: str, channel: str):
    _require_program_prefix(request, program_prefix)  # 404 before any write
    return channel_only_redirect(request, channel)


@require_GET
def prefixed_referral_continue(request, program_prefix: str, client_id: str, channel: str | None = None):
    _require_program_prefix(request, program_prefix)
    return referral_continue(request, client_id, channel=channel)


@require_GET
def prefixed_referral_prompt_view(request, program_prefix: str):
    _require_program_prefix(request, program_prefix)
    return referral_prompt_view(request)


@require_GET
def prefixed_share_intent_redirect(request, program_prefix: str, channel: str, client_id: str):
    # Fails closed (404) on a non-matching prefix BEFORE the delegate can write anything.
    _require_program_prefix(request, program_prefix)
    return share_intent_redirect(request, channel, client_id)


@require_GET
def prefixed_share_prompt_view(request, program_prefix: str, channel: str):
    _require_program_prefix(request, program_prefix)
    return share_prompt_view(request, channel)


# --- Preview card v2 image routes (owner 2026-11-03) -------------------------------------
# Public, no login. 404 while `preview_card_v2_enabled` is off. The named route NEVER fails:
# any ineligible id (switch off, unknown, deleted, placeholder, no/invalid name, opted out)
# gets the GENERIC card bytes, because a broken image kills the whole preview.

def _card_response(request, tenant, client_id: str | None):
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseNotFound

    from apps.referrals import og

    tenant_id = getattr(tenant, "id", None)
    if not og.v2_enabled(tenant_id):
        return HttpResponseNotFound()
    try:
        check_rate("og_card", client_ip(request),
                   limit=settings.RATELIMIT_CLICK_MAX, window=settings.RATELIMIT_API_WINDOW)
    except RateLimited as exc:
        resp = HttpResponse("Too many requests", status=429, content_type="text/plain")
        resp["Retry-After"] = str(exc.retry_after)
        return resp
    try:
        first_name = og.named_first_name(tenant, client_id) if client_id else None
    except Exception:  # any lookup failure -> the generic card, never a 500
        first_name = None
    png = og.card_png(og.v2_card_text(tenant_id, first_name))
    resp = HttpResponse(png, content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


@require_GET
def og_card(request):
    """GET /og/card.png — the generic v2 preview card."""
    return _card_response(request, get_current_tenant(request), None)


@require_GET
def og_card_named(request, client_id: str):
    """GET /og/card/<client_id>.png — the referrer's named card, or the generic one."""
    return _card_response(request, get_current_tenant(request), client_id)
