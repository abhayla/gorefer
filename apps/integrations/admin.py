from django.contrib import admin

from .models import Conversion, Notification, ZohoDeadLetter, ZohoSyncIdempotency


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_role", "template", "status", "recipient_mobile",
        "meta_error_code", "failure_classification", "created_at",
    )
    list_filter = ("status", "recipient_role", "category")
    readonly_fields = ("idempotency_key", "provider_message_id")


@admin.register(Conversion)
class ConversionAdmin(admin.ModelAdmin):
    list_display = (
        "opener_zerodha_account_id", "referrer_client_id", "status",
        "account_opened_at", "is_reversed", "source_origin", "synced_at",
    )
    list_filter = ("status", "is_reversed", "source_origin")
    search_fields = ("opener_zerodha_account_id", "zoho_lead_id", "referrer_client_id")


@admin.register(ZohoSyncIdempotency)
class ZohoSyncIdempotencyAdmin(admin.ModelAdmin):
    list_display = ("dedupe_key", "processed_at", "result")


@admin.register(ZohoDeadLetter)
class ZohoDeadLetterAdmin(admin.ModelAdmin):
    list_display = ("dedupe_key", "attempts", "resolved_at", "created_at")
