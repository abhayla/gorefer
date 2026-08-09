"""Admin dashboard URLs (M7). Mounted only when ENABLE_ADMIN_DASHBOARD is on."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.DashboardLoginView.as_view(), name="dashboard_login"),
    path("logout/", LogoutView.as_view(next_page="dashboard_login"), name="dashboard_logout"),
    path("", views.dashboard, name="dashboard"),
    path("explorer/", views.explorer, name="dashboard_explorer"),
    path("journey/<int:referral_id>/", views.journey, name="dashboard_journey"),
    # Referral Profile / User Referral Screen (M9).
    path("referrers/", views.referrer_search, name="dashboard_referrer_search"),
    path("referrer/<str:client_id>/", views.referrer_profile, name="dashboard_referrer"),
    # T-064: reset one referrer's personal share opener back to the official message.
    path(
        "referrer/<str:client_id>/opener/reset",
        views.referrer_opener_reset,
        name="dashboard_referrer_opener_reset",
    ),
    # Preferences / Settings screen (Q-M-PREF / ADR-034).
    path("preferences", views.preferences, name="dashboard_preferences"),
    path(
        "preferences/partnership",
        views.preferences_partnership,
        name="dashboard_preferences_partnership",
    ),
]

# Referrer verification queue (M13: ADR-027 mismatch + ADR-035 Path B evidence).
# Mounted only when the customer-login surface exists — a queue that can never
# receive a request is dead UI (Constitution §4), so it appears with the feature.
if getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_CUSTOMER_LOGIN", False):
    urlpatterns += [
        path("verifications/", views.verifications, name="dashboard_verifications"),
        path(
            "verifications/<int:request_id>/evidence",
            views.verification_evidence,
            name="dashboard_verification_evidence",
        ),
        path(
            "verifications/<int:request_id>/decide",
            views.verification_decide,
            name="dashboard_verification_decide",
        ),
    ]
