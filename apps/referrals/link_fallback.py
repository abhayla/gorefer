"""A broken public link never shows an error page (owner decision 2026-11-10).

Any public GET that would answer 404 - a mistyped link, an unknown program word, a
channel or route that is not served - is redirected to the default account-opening
link (`/{program}/open`, or bare `/open`), which records the click and sends the
visitor on to the partner as usual. This middleware only redirects to that link; it
writes nothing and builds no partner URL itself.

Before giving up on the link as typed it tries the same path lower-cased and without a
trailing slash, so `/Zerodha/Open/YT/HI/` still reaches `/zerodha/open/yt/hi` and keeps
its channel and language tags.

What stays a real 404 (structural, not behaviour):
  - non-GET requests;
  - the signed-in and machine surfaces in `EXCLUDED_PREFIXES` - sending an admin, a
    referrer's own page or an API caller to a signup page would hide a real fault;
  - file-like paths (`/wp-login.php`, `/.env`, `/favicon.ico`): scanners, not people,
    and redirecting them would count as partner-link clicks.

Switch: cascade key `link_fallback_enabled` (default on).
"""
from __future__ import annotations

import logging

from django.http import HttpResponseRedirect
from django.urls import Resolver404, resolve

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve as resolve_config
from apps.tenants.resolve import get_current_tenant

from .links import partner_direct_path

logger = logging.getLogger("gorefer.redirect")

EXCLUDED_PREFIXES = (
    "api", "admin-panel", "django-admin", "static", "media", "og", "d", "privacy",
    "login", "my", "hub", "rr",
)


def _is_public_link_path(path: str) -> bool:
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False
    if segments[0].lower() in EXCLUDED_PREFIXES:
        return False
    return "." not in segments[-1]


def _repaired_path(path: str) -> str | None:
    """The same link lower-cased, without a trailing slash - when that is a real route."""
    try:
        resolve(path)
        return None  # a real route answered 404 itself; re-spelling the link cannot help
    except Resolver404:
        pass
    candidate = path.rstrip("/").lower() or "/"
    if candidate == path:
        return None
    try:
        resolve(candidate)
    except Resolver404:
        return None
    return candidate


class LinkFallbackMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 404 or request.method != "GET":
            return response
        if not _is_public_link_path(request.path):
            return response
        tenant = get_current_tenant(request)
        tenant_id = getattr(tenant, "id", None)
        if not resolve_config(prefkeys.LINK_FALLBACK_ENABLED, tenant_id=tenant_id, default=True):
            return response

        query = request.META.get("QUERY_STRING", "")
        target = _repaired_path(request.path)
        if target is not None:
            if query:
                target = f"{target}?{query}"
        else:
            target = partner_direct_path(tenant=tenant)
        if target == request.path:  # the default link itself is missing: nothing to fall back to
            return response
        logger.warning("broken link %s -> %s", request.path, target)
        return HttpResponseRedirect(target)
