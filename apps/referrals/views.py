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

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.config.cascade import resolve
from apps.tenants.resolve import get_current_tenant
from gorefer import flags as flagmod
from gorefer.flags import flags, normalize_share_channel

from .models import ProgramRedirectRule, ReferralIdentity, ReferralProgram
from .redirect_service import build_continue_redirect, handle_landing_view, handle_partner_direct
from .validators import InvalidClientId, validate_client_id

VISITOR_COOKIE = "gr_vid"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

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
    from django.templatetags.static import static

    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    image = settings.OG_IMAGE
    if not image.startswith(("http://", "https://")):
        # Resolve a static path to an absolute URL for crawlers.
        image = base + static(image)
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
    tenant_id = tenant.id if tenant is not None else None
    wa_number = resolve("wati_business_number", tenant_id=tenant_id, default="")
    ctx = {
        "client_id": client_id,
        "nonce": nonce or "",
        "wati_business_number": wa_number,
        "privacy_policy_url": resolve("privacy_policy_url", tenant_id=tenant_id, default="#"),
        "REFERRAL_INCENTIVE_CLAIM": flags.REFERRAL_INCENTIVE_CLAIM,
        "show_incentive": True,  # a valid referrer -> show the referral-benefit panel
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
    visitor_id, is_new = _ensure_visitor_id(request)
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
def partner_direct_redirect(request):
    """GET /open — partner-direct 302 (no r=); stays a direct redirect (no landing)."""
    tenant = get_current_tenant(request)
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
