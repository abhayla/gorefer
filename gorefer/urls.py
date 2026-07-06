"""Root URL configuration.

M1 wires: the Django admin (M7 dashboard base; env-bootstrapped admin-only auth),
the Django Ninja API mount, and a minimal server-rendered health/home page. No
referral/redirect routes yet — those arrive in M2.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

from api.router import api

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("api/", api.urls),
]

if getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_ADMIN_DASHBOARD", True):
    urlpatterns.append(path("admin/", admin.site.urls))
