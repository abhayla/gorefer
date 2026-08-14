"""Test URLConf: the prod tree with ENABLE_SHARE_HUB **and** ENABLE_CUSTOMER_LOGIN on.

The root urls mount every flagged route at IMPORT time from settings.FEATURE_FLAGS (no
dead route when off), so neither flag can be flipped per-test. This module mirrors
EXACTLY what those two flags mount together in `gorefer/urls.py` — including the
ORDER: the token-free `/hub` and `/hub/opener` come first, because `hub/<str:token>`
would otherwise match `/hub/opener` with token="opener".

Used via `@pytest.mark.urls("tests.urls_hub_login")`.
"""
from django.urls import include, path

from apps.accounts.hub import hub_me_opener_view, hub_me_view, hub_opener_view, hub_view
from apps.accounts.records import records_view
from gorefer.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    # T-075 — the login-gated hub. Listed before the tokened routes (see above).
    path("hub", hub_me_view, name="share_hub_me"),
    path("hub/opener", hub_me_opener_view, name="share_hub_me_opener"),
    # The still-live token routes (Phase 3 deletes them).
    path("hub/<str:token>", hub_view, name="share_hub"),
    path("hub/<str:token>/opener", hub_opener_view, name="share_hub_opener"),
    path("rr/<str:value>", records_view, name="records_link"),
    # The M13 login surface the gate redirects to.
    path("", include("apps.accounts.urls")),
]
