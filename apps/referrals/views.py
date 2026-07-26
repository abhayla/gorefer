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

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.config.cascade import resolve
from apps.events.bots import is_bot_user_agent
from apps.referrals.og import render_preview
from apps.tenants.resolve import get_current_tenant
from gorefer import flags as flagmod
from gorefer.flags import flags, normalize_share_channel

from .landing_mode import LANDING_MODE_DIRECT, resolve_landing_mode
from .models import ProgramRedirectRule, ReferralIdentity, ReferralProgram
from .redirect_service import (
    build_continue_redirect,
    handle_direct_redirect,
    handle_landing_view,
    handle_partner_direct,
)
from .share_intent_service import handle_share_intent
from .validators import InvalidClientId, validate_client_id

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

    from apps.referrals.og import absolute_image_url

    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    # ONE canonical absolute-OG-image builder, shared with the D2 crawler card — the
    # crawler card shipped with a relative og:image because it did not reuse this.
    image = absolute_image_url(settings.OG_IMAGE)
    return {
        "og_title": settings.OG_TITLE,
        "og_description": settings.OG_DESCRIPTION,
        "og_image": image,
        "og_url": f"{base}/r/{client_id}",
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
        "privacy_policy_url": resolve("privacy_policy_url", tenant_id=tenant_id, default="#"),
        "REFERRAL_INCENTIVE_CLAIM": reward_claim if show_reward else "",
        "show_incentive": show_reward,  # tenant may hide the referral-benefit panel
    }
    ctx.update(_og_context(request, client_id))
    return ctx


@require_GET
def referral_redirect(request, client_id: str, channel: str | None = None):
    """GET /r/{client_id} (or /r/{channel}/{client_id}) — render the branded landing.

    `channel` (B1) is an optional path prefix carrying the share channel (e.g.
    /r/wa/RJ4521) for WhatsApp URL buttons where `?s=` can't trail the id. Legacy
    /r/{client_id}?s= still works — see _share_channel.
    """
    try:
        normalized = validate_client_id(client_id)
    except InvalidClientId:
        # Friendly branded fallback — never a raw error, no journey created.
        return render(request, "landing_invalid.html", status=400)

    tenant = get_current_tenant(request)

    # D2 — a CRAWLER gets a PIFS link-preview card, never a 302.
    #
    # A forwarded link used to redirect the crawler too, so WhatsApp built its preview from
    # the partner's page and every shared link showed the partner's branding instead of
    # PIFS's — on the one surface a friend sees before tapping. Checked BEFORE visitor-cookie
    # issuance and before any journey work, so a preview fetch still creates nothing.
    if is_bot_user_agent(request.META.get("HTTP_USER_AGENT", "")):
        return render_preview(request, tenant_id=getattr(tenant, "id", None))

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
def referral_continue(request, client_id: str, channel: str | None = None):
    """GET /r/{client_id}/continue (or /r/{channel}/{client_id}/continue) — the
    Continue-to-Zerodha 302 (reuses M2 engine). `channel` is the optional B1 path
    prefix; captured for attribution, NEVER added to the Location."""
    try:
        normalized = validate_client_id(client_id)
    except InvalidClientId:
        return render(request, "landing_invalid.html", status=400)

    tenant = get_current_tenant(request)
    identity = ReferralIdentity.objects.filter(
        tenant=tenant, client_id=normalized, id_source="native"
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
    `share_intent` event, then 302s. Unsupported channel -> 404; invalid
    client_id -> the same branded 400 as `/r/`; unresolvable partner config -> the
    same branded 503 as `/r/`.
    """
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseNotFound

    try:
        check_rate("share", client_ip(request),
                   limit=settings.RATELIMIT_SHARE_MAX, window=settings.RATELIMIT_API_WINDOW)
    except RateLimited as exc:
        return HttpResponse(status=429, headers={"Retry-After": str(exc.retry_after)})

    try:
        normalized = validate_client_id(client_id)
    except InvalidClientId:
        return render(request, "landing_invalid.html", status=400)

    tenant = get_current_tenant(request)
    try:
        destination = handle_share_intent(
            tenant=tenant,
            channel=channel,
            client_id=normalized,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
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
