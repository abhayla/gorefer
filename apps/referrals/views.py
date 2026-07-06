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
from gorefer.flags import flags

from .models import ReferralIdentity
from .redirect_service import build_continue_redirect, handle_landing_view, handle_partner_direct
from .validators import InvalidClientId, validate_client_id

VISITOR_COOKIE = "gr_vid"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


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


def _landing_context(request, tenant, client_id: str, nonce: str | None):
    """Config-driven landing context (no referrer NAME in initial HTML — #1/#3)."""
    tenant_id = tenant.id if tenant is not None else None
    wa_number = resolve("wati_business_number", tenant_id=tenant_id, default="")
    wa_text = f"Hi, I'd like to refer someone for a Zerodha account. Referral ID: {client_id}"
    return {
        "client_id": client_id,
        "nonce": nonce or "",
        "wati_business_number": wa_number,
        "whatsapp_share_url": f"https://wa.me/{wa_number}?text={wa_text}",
        "privacy_policy_url": resolve("privacy_policy_url", tenant_id=tenant_id, default="#"),
        "REFERRAL_INCENTIVE_CLAIM": flags.REFERRAL_INCENTIVE_CLAIM,
        "show_incentive": True,  # a valid referrer -> show the referral-benefit panel
    }


@require_GET
def referral_redirect(request, client_id: str):
    """GET /r/{client_id} — render the branded landing (200), NOT an immediate 302."""
    try:
        normalized = validate_client_id(client_id)
    except InvalidClientId:
        # Friendly branded fallback — never a raw error, no journey created.
        return render(request, "landing_invalid.html", status=400)

    tenant = get_current_tenant(request)
    visitor_id, is_new = _ensure_visitor_id(request)
    _referral, _event, nonce = handle_landing_view(
        tenant=tenant,
        client_id=normalized,
        visitor_id=visitor_id,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        raw_ip=_client_ip(request),
    )
    context = _landing_context(request, tenant, normalized, nonce)
    response = render(request, "landing.html", context)
    _set_visitor_cookie(response, visitor_id, is_new)
    return response


@require_GET
def referral_continue(request, client_id: str):
    """GET /r/{client_id}/continue — the Continue-to-Zerodha 302 (reuses M2 engine)."""
    try:
        normalized = validate_client_id(client_id)
    except InvalidClientId:
        return render(request, "landing_invalid.html", status=400)

    tenant = get_current_tenant(request)
    identity = ReferralIdentity.objects.filter(
        tenant=tenant, client_id=normalized, id_source="native"
    ).first()
    referral = identity.referrals.filter(source="referral_link").order_by("id").first() if identity else None
    destination = build_continue_redirect(tenant=tenant, client_id=normalized, referral=referral)
    return HttpResponseRedirect(destination)


@require_GET
def partner_direct_redirect(request):
    """GET /open — partner-direct 302 (no r=); stays a direct redirect (no landing)."""
    tenant = get_current_tenant(request)
    visitor_id, is_new = _ensure_visitor_id(request)
    destination, _is_human = handle_partner_direct(
        tenant=tenant,
        visitor_id=visitor_id,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        raw_ip=_client_ip(request),
    )
    response = HttpResponseRedirect(destination)
    _set_visitor_cookie(response, visitor_id, is_new)
    return response
