"""Admin dashboard URLs (M7). Mounted only when ENABLE_ADMIN_DASHBOARD is on."""
from __future__ import annotations

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
]
