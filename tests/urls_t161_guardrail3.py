"""Test URLConf: the prod tree PLUS every flagged client-facing surface mounted
TOGETHER (T-161 pt 17 — guardrail-3 expansion).

The root urls mount each of these at IMPORT time from settings.FEATURE_FLAGS (no dead
route when off), so no single flag combination in the real env can be relied on to
exercise all of them in one test run. This module mirrors EXACTLY what
ENABLE_SHARE_HUB + ENABLE_RECORDS_LINK + ENABLE_CUSTOMER_LOGIN + ENABLE_SHARE_INTENT
mount together in `gorefer/urls.py` — if that mounting changes, change it here too.

Used via `@pytest.mark.urls("tests.urls_t161_guardrail3")`.
"""
from django.urls import include, path

from apps.accounts.hub import hub_me_opener_view, hub_me_view, hub_opener_view, hub_view
from apps.accounts.records import records_view
from apps.referrals.views import share_intent_redirect, share_recovery_view
from gorefer.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    path("hub", hub_me_view, name="share_hub_me"),
    path("hub/opener", hub_me_opener_view, name="share_hub_me_opener"),
    path("hub/<str:token>", hub_view, name="share_hub"),
    path("hub/<str:token>/opener", hub_opener_view, name="share_hub_opener"),
    path("rr/", share_recovery_view, name="records_recovery_slash"),
    path("rr", share_recovery_view, name="records_recovery_bare"),
    path("rr/<str:value>", records_view, name="records_link"),
    path("", include("apps.accounts.urls")),
    path("share/<channel:channel>/<str:client_id>", share_intent_redirect, name="share_intent"),
    path("share/<channel:channel>/", share_recovery_view, name="share_recovery_slash"),
    path("share/<channel:channel>", share_recovery_view, name="share_recovery_bare"),
]
