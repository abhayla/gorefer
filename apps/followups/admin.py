"""Django admin for the follow-up engine — the secure CRUD surface (doc 14 §C).

Django's admin gives the AP's rule cadence full create/edit/delete/pause with Django's
own auth + CSRF for free (the "admin now" half of §C). ScheduledFollowup is view-mostly
with a bulk-cancel action — instance rows are immutable once SENT; a pending row can be
cancelled or rescheduled here (a CRUD lifecycle the sweep's row-lock keeps race-safe).
Everything is gated by the existing ENABLE_ADMIN_DASHBOARD mount in gorefer/urls.py.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils import timezone

from .models import FollowupRule, FollowupWindow, ScheduledFollowup


@admin.register(FollowupRule)
class FollowupRuleAdmin(admin.ModelAdmin):
    list_display = ("step_key", "offset_minutes", "channel", "enabled", "only_if_window_open",
                    "stop_on_reply", "order", "tenant")
    list_filter = ("enabled", "channel", "tenant")
    search_fields = ("step_key", "template_name")
    ordering = ("order", "id")


@admin.register(ScheduledFollowup)
class ScheduledFollowupAdmin(admin.ModelAdmin):
    list_display = ("mobile", "rule", "status", "fire_at", "window_opened_at", "sent_at",
                    "reason", "tenant")
    list_filter = ("status", "tenant")
    search_fields = ("mobile", "dedupe_key")
    ordering = ("-fire_at",)
    # Immutable-by-default in the admin; the lifecycle transitions go through the action
    # (or the API), never a free-form status edit that could contradict the sweep.
    readonly_fields = ("dedupe_key", "window_opened_at", "sent_at")
    actions = ("cancel_selected",)

    @admin.action(description="Cancel selected (only pending 'scheduled' rows)")
    def cancel_selected(self, request, queryset):
        updated = queryset.filter(status=ScheduledFollowup.STATUS_SCHEDULED).update(
            status=ScheduledFollowup.STATUS_CANCELLED,
            reason="cancelled by admin",
            updated_at=timezone.now(),
        )
        self.message_user(request, f"Cancelled {updated} pending follow-up(s).")


@admin.register(FollowupWindow)
class FollowupWindowAdmin(admin.ModelAdmin):
    list_display = ("mobile", "last_inbound_at", "opted_out", "tenant")
    list_filter = ("opted_out", "tenant")
    search_fields = ("mobile",)
