"""Test URLConf: the prod tree PLUS both token-gated routes (/hub/ and /rr/).

The root urls mount each view at IMPORT time from settings.FEATURE_FLAGS (no dead route
when off), so neither flag can be flipped per-test. This module mirrors EXACTLY what the
two flags mount in `gorefer/urls.py` — if that mounting changes, change it here too.

Both are mounted together because the T-053 cross-link tests need each page to be able
to point at the other. Used via `@pytest.mark.urls("tests.urls_share_hub")`.
"""
from django.urls import path

from apps.accounts.hub import hub_view
from apps.accounts.records import records_view
from gorefer.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    path("rr/<str:token>", records_view, name="records_link"),
    path("hub/<str:token>", hub_view, name="share_hub"),
]
