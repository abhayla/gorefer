"""Sync redirect views (ADR-021, ADR-024): validate -> log click on-commit -> 302.

These are the hot path. They must be fast and MUST NOT block on the click write
(handled via transaction.on_commit in the service). They return a 302 to a
real browser only — they NEVER submit Zerodha's form.
"""
from __future__ import annotations

import uuid

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.tenants.resolve import get_current_tenant

from .redirect_service import handle_partner_direct, handle_referral_click
from .validators import InvalidClientId, validate_client_id

VISITOR_COOKIE = "gr_vid"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _ensure_visitor_id(request) -> tuple[str, bool]:
    """Return (visitor_id, is_new). Reuse the cookie so repeat hits share a journey."""
    existing = request.COOKIES.get(VISITOR_COOKIE)
    if existing:
        return existing, False
    return uuid.uuid4().hex, True


def _set_visitor_cookie(response, visitor_id: str, is_new: bool):
    if is_new:
        response.set_cookie(
            VISITOR_COOKIE,
            visitor_id,
            max_age=VISITOR_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
        )


@require_GET
def referral_redirect(request, client_id: str):
    """GET /r/{client_id} — validate, lazily record the click, 302 to Zerodha."""
    try:
        normalized = validate_client_id(client_id)
    except InvalidClientId:
        # Malformed id: show a light branded error, never redirect or create a journey.
        return render(request, "redirect_invalid.html", status=400)

    tenant = get_current_tenant(request)
    visitor_id, is_new = _ensure_visitor_id(request)
    destination, _is_human = handle_referral_click(
        tenant=tenant,
        client_id=normalized,
        visitor_id=visitor_id,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        raw_ip=_client_ip(request),
    )
    response = HttpResponseRedirect(destination)
    _set_visitor_cookie(response, visitor_id, is_new)
    return response


@require_GET
def partner_direct_redirect(request):
    """GET /open — partner-direct 302 (no r=); journey referrer=NONE/partner_direct."""
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
