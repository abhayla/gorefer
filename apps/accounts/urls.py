"""Referrer login + My Referrals URLs (M13). Mounted ONLY when ENABLE_CUSTOMER_LOGIN
is on (root urls) — the whole surface disappears when the flag is off (no dead UI)."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_entry, name="referrer_login"),
    path("login/otp/request", views.otp_request, name="referrer_otp_request"),
    path("login/otp/verify", views.otp_verify, name="referrer_otp_verify"),
    path("login/google/start", views.oauth_start, name="referrer_oauth_start"),
    path("login/google/callback", views.oauth_callback, name="referrer_oauth_callback"),
    path("login/bind", views.oauth_bind, name="referrer_oauth_bind"),
    path("login/verify-ownership", views.path_b, name="referrer_pathb"),
    path("my/referrals", views.my_referrals, name="my_referrals"),
    path("my/logout", views.my_logout, name="referrer_logout"),
]
