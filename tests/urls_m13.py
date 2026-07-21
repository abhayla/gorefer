"""Test URLConf: the prod tree PLUS the ENABLE_CUSTOMER_LOGIN-mounted surfaces.

The root urls mount `apps.accounts.urls` + the dashboard verification queue at
IMPORT time from settings.FEATURE_FLAGS (no dead UI when off), so the flag can't be
flipped per-test. This module mirrors EXACTLY what the flag mounts — if the prod
mounting in `gorefer/urls.py` / `apps/dashboard/urls.py` changes, change it here too.
Used via `@pytest.mark.urls("tests.urls_m13")`.
"""
from django.urls import include, path

from apps.dashboard import views as dashboard_views
from gorefer.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    path("", include("apps.accounts.urls")),
    path(
        "admin-panel/verifications/",
        dashboard_views.verifications,
        name="dashboard_verifications",
    ),
    path(
        "admin-panel/verifications/<int:request_id>/evidence",
        dashboard_views.verification_evidence,
        name="dashboard_verification_evidence",
    ),
    path(
        "admin-panel/verifications/<int:request_id>/decide",
        dashboard_views.verification_decide,
        name="dashboard_verification_decide",
    ),
]
