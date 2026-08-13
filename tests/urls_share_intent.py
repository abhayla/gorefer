"""Test URLConf: the prod tree PLUS the ENABLE_SHARE_INTENT-gated /share/ route.

The root urls mount `share_intent_redirect` at IMPORT time from
settings.FEATURE_FLAGS (no dead route when off), so the flag can't be flipped
per-test. This module mirrors EXACTLY what the flag mounts in `gorefer/urls.py` —
if that mounting changes, change it here too. Used via
`@pytest.mark.urls("tests.urls_share_intent")`.
"""
from django.urls import path

from apps.referrals.views import share_intent_redirect, share_recovery_view
from gorefer.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    path("share/<channel:channel>/<str:client_id>", share_intent_redirect, name="share_intent"),
    path("share/<channel:channel>/", share_recovery_view, name="share_recovery_slash"),
    path("share/<channel:channel>", share_recovery_view, name="share_recovery_bare"),
]
