from django.contrib import admin

from .models import ClickNonce, DailyMetric, Event, MonthlyMetric, SyncHealth, VisitorPII


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type", "source", "referral", "visitor_id", "is_bot", "is_confirmed_human", "timestamp",
    )
    list_filter = ("event_type", "source", "is_bot", "is_confirmed_human")
    readonly_fields = tuple(f.name for f in Event._meta.fields)  # events are immutable


@admin.register(VisitorPII)
class VisitorPIIAdmin(admin.ModelAdmin):
    list_display = ("visitor_id", "raw_ip", "city", "created_at", "erased_at")


@admin.register(ClickNonce)
class ClickNonceAdmin(admin.ModelAdmin):
    list_display = ("nonce", "visitor_id", "client_id", "created_at", "expires_at", "consumed_at")


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "metric_date", "program", "clicks", "landing_views", "redirects", "leads", "accounts_opened",
    )
    list_filter = ("metric_date",)


@admin.register(MonthlyMetric)
class MonthlyMetricAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "program", "clicks", "leads", "accounts_opened")


@admin.register(SyncHealth)
class SyncHealthAdmin(admin.ModelAdmin):
    list_display = ("zoho_state", "last_successful_zoho_sync_at", "wati_state", "updated_at")
