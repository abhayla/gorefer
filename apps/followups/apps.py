from __future__ import annotations

from django.apps import AppConfig


class FollowupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.followups"
    label = "followups"
    verbose_name = "24h-window follow-up engine"
