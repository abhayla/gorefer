from django.contrib import admin

from .models import Event, VisitorPII


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "referral", "visitor_id", "is_bot", "is_confirmed_human", "timestamp")
    list_filter = ("event_type", "is_bot", "is_confirmed_human")
    readonly_fields = tuple(f.name for f in Event._meta.fields)  # events are immutable


@admin.register(VisitorPII)
class VisitorPIIAdmin(admin.ModelAdmin):
    list_display = ("visitor_id", "raw_ip", "city", "created_at", "erased_at")
