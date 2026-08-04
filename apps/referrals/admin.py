"""Admin registrations — the base the M7 dashboard builds on.

Read-mostly views of the seeded program/partner so an admin can confirm the
foundation in demo mode. No client-facing surface here (admin-only, behind
ENABLE_ADMIN_DASHBOARD).
"""
from django.contrib import admin

from .models import (
    Customer,
    Lead,
    Partner,
    ProgramRedirectRule,
    Prospect,
    Referral,
    ReferralIdentity,
    ReferralProgram,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("client_id", "first_name", "last_name", "mobile", "status")
    search_fields = ("client_id", "mobile", "email")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "status")
    search_fields = ("name", "code")


@admin.register(ReferralProgram)
class ReferralProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "partner", "status", "reward_description")
    list_filter = ("status",)
    search_fields = ("name",)


@admin.register(ProgramRedirectRule)
class ProgramRedirectRuleAdmin(admin.ModelAdmin):
    list_display = ("program", "priority", "is_active")


@admin.register(ReferralIdentity)
class ReferralIdentityAdmin(admin.ModelAdmin):
    list_display = ("client_id", "program", "id_source", "status", "created_at")
    list_filter = ("status", "id_source")
    search_fields = ("client_id",)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "status", "referral_identity", "first_click_at", "created_at")
    list_filter = ("source", "status")


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display = ("mobile", "name", "email", "city", "created_at")
    search_fields = ("mobile", "email", "name")


class UnsyncedZohoFilter(admin.SimpleListFilter):
    """Surface leads that never reached Zoho, so a stuck one is never silent.

    `needs_attention` = attempts exhausted -> the backfill sweep has given up and a
    human must look. `awaiting_retry` = still within the retry budget (a transient
    outage) -> expected to self-heal on the next sweep.
    """

    title = "Zoho sync"
    parameter_name = "zoho_unsynced"

    def lookups(self, request, model_admin):
        return [
            ("unsynced", "Unsynced (pending or failed)"),
            ("needs_attention", "Needs attention (retries exhausted)"),
            ("awaiting_retry", "Awaiting retry"),
        ]

    def queryset(self, request, queryset):
        from apps.integrations import services

        unsynced = [Lead.SYNC_PENDING, Lead.SYNC_FAILED]
        if self.value() == "unsynced":
            return queryset.filter(zoho_sync_status__in=unsynced)
        if self.value() == "needs_attention":
            return queryset.filter(
                zoho_sync_status__in=unsynced, zoho_sync_attempts__gte=services.MAX_SYNC_ATTEMPTS
            )
        if self.value() == "awaiting_retry":
            return queryset.filter(
                zoho_sync_status__in=unsynced, zoho_sync_attempts__lt=services.MAX_SYNC_ATTEMPTS
            )
        return queryset


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "id", "status", "submitted_by", "consent", "referral",
        "zoho_sync_status", "zoho_sync_attempts", "zoho_lead_id", "created_at",
    )
    list_filter = ("status", "submitted_by", "zoho_sync_status", UnsyncedZohoFilter)
    readonly_fields = ("zoho_last_error", "zoho_synced_at")
    actions = ["retry_zoho_sync"]

    @admin.action(description="Retry Zoho sync (re-enqueue selected leads)")
    def retry_zoho_sync(self, request, queryset):
        """Manual re-enqueue — the operator's escape hatch for an exhausted lead.

        Resets attempts so a lead the sweep gave up on can be retried after the
        underlying cause is fixed. Safe: the upsert dedups on mobile, never twins.
        """
        from apps.integrations import services

        eligible = queryset.exclude(zoho_sync_status=Lead.SYNC_SYNCED)
        count = 0
        for lead in eligible:
            lead.zoho_sync_attempts = 0
            lead.zoho_sync_status = Lead.SYNC_PENDING
            lead.save(update_fields=["zoho_sync_attempts", "zoho_sync_status", "updated_at"])
            services.enqueue_lead_upsert(lead.pk)
            count += 1
        self.message_user(request, f"Re-enqueued {count} lead(s) for Zoho sync.")
