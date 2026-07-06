"""Root URL configuration.

Wires: the server-rendered home page, the Django Ninja API mount, the Django admin
(M7 base), and the M2 redirect routes:
  - GET /r/{client_id}  -> referral redirect (lazy journey + click + 302)
  - GET /open           -> partner-direct redirect (302, no r=)
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

from api.router import api
from apps.referrals.views import partner_direct_redirect, referral_continue, referral_redirect

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("open", partner_direct_redirect, name="partner_direct"),
    path("r/<str:client_id>/continue", referral_continue, name="referral_continue"),
    path("r/<str:client_id>", referral_redirect, name="referral_redirect"),
    path("api/", api.urls),
]

if getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_ADMIN_DASHBOARD", True):
    urlpatterns.append(path("admin/", admin.site.urls))
