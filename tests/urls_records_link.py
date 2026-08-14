"""Test URLConf: the prod tree PLUS the ENABLE_RECORDS_LINK-gated /rr/ route.

The root urls mount `records_view` at IMPORT time from settings.FEATURE_FLAGS (no dead
route when off), so the flag can't be flipped per-test. This module mirrors EXACTLY what
the flag mounts in `gorefer/urls.py` — if that mounting changes, change it here too.
Used via `@pytest.mark.urls("tests.urls_records_link")`.
"""
from django.urls import path

from apps.accounts.records import records_view
from apps.referrals.views import share_recovery_view
from gorefer.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    path("rr/", share_recovery_view, name="records_recovery_slash"),
    path("rr", share_recovery_view, name="records_recovery_bare"),
    path("rr/<str:value>", records_view, name="records_link"),
]
