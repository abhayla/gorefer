"""Root URL configuration.

Wires: the server-rendered home page, the Django Ninja API mount, the Django admin
(M7 base), and the redirect routes:
  - GET /r/{client_id}                     -> referral redirect (lazy journey + click)
  - GET /r/{channel}/{client_id}           -> same, channel carried as a PATH PREFIX
    (B1/ADR-028) so a WhatsApp dynamic URL button can keep the client_id LAST
  - GET /open                              -> partner-direct redirect (302, no r=)

Ordering note: the `{channel}` converter matches only 1–8 lowercase letters, and
the two-segment `/r/X/Y` form is what selects the channel route — so it can never
shadow the single-segment legacy `/r/{client_id}` (or its `/continue`). Within each
form the more specific `/continue` pattern is listed before the bare landing.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, register_converter
from django.urls.converters import get_converters
from django.views.generic import TemplateView

from api.router import api
from apps.referrals.views import (
    disclosure_page,
    partner_direct_redirect,
    referral_continue,
    referral_redirect,
    share_intent_redirect,
)
from gorefer.converters import ChannelConverter

# Register the {channel} path converter once. Guarded because this module can be
# imported more than once in a process (test reloads), and re-registering warns
# (RemovedInDjango60Warning) under Django 5.x.
if "channel" not in get_converters():
    register_converter(ChannelConverter, "channel")

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("open", partner_direct_redirect, name="partner_direct"),
    # Per-sub-broker disclosure page (B2 / ADR-031) — the canonical §4.4 host.
    path("d/<slug:slug>", disclosure_page, name="disclosure_page"),
    # Channel-path form (B1): /r/{channel}/{client_id}[/continue]. Listed first; the
    # narrow {channel} converter keeps these from ever matching a legacy single id.
    path("r/<channel:channel>/<str:client_id>/continue", referral_continue, name="referral_continue_channel"),
    path("r/<channel:channel>/<str:client_id>", referral_redirect, name="referral_redirect_channel"),
    # Legacy single-segment form (M2/M3) — unchanged; still honours ?s=.
    path("r/<str:client_id>/continue", referral_continue, name="referral_continue"),
    path("r/<str:client_id>", referral_redirect, name="referral_redirect"),
    path("api/", api.urls),
]

# One-tap share endpoint (M-WATI-1). The ENTIRE route exists only when
# ENABLE_SHARE_INTENT is on (Constitution §4 — no dead UI/route when off).
if getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_SHARE_INTENT", False):
    urlpatterns.append(
        path("share/<channel:channel>/<str:client_id>", share_intent_redirect, name="share_intent")
    )

# The M7 admin dashboard (custom, built from the mockups) + Django admin base,
# both gated by the feature flag (no dead UI when off).
if getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_ADMIN_DASHBOARD", True):
    urlpatterns.append(path("django-admin/", admin.site.urls))
    urlpatterns.append(path("admin-panel/", include("apps.dashboard.urls")))

# Referrer self-service login + My Referrals (M13). The ENTIRE surface exists only
# when ENABLE_CUSTOMER_LOGIN is on (Constitution §4 — no dead UI when off).
if getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_CUSTOMER_LOGIN", False):
    urlpatterns.append(path("", include("apps.accounts.urls")))
