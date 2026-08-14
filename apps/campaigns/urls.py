"""Campaigns admin CRUD URLs (T-124 W1). Mounted at /admin-panel/campaigns by
gorefer/urls.py, under the same ENABLE_ADMIN_DASHBOARD gate as the rest of
/admin-panel/ (Constitution §4 — no route mounted when the surface is off)."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.campaign_list, name="campaigns_list"),
    path("<int:campaign_id>/", views.campaign_edit, name="campaigns_edit"),
    path("<int:campaign_id>/steps/add", views.step_add, name="campaigns_step_add"),
    path("<int:campaign_id>/steps/<int:step_id>/remove", views.step_remove, name="campaigns_step_remove"),
    path(
        "<int:campaign_id>/steps/<int:step_id>/move/<str:direction>",
        views.step_move,
        name="campaigns_step_move",
    ),
    path("<int:campaign_id>/steps/<int:step_id>/update", views.step_update, name="campaigns_step_update"),
]
