from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_role", "template", "status", "recipient_mobile",
        "meta_error_code", "failure_classification", "created_at",
    )
    list_filter = ("status", "recipient_role", "category")
    readonly_fields = ("idempotency_key", "provider_message_id")
