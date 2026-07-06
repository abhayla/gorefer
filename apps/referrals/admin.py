"""Admin registrations — the base the M7 dashboard builds on.

Read-mostly views of the seeded program/partner so an admin can confirm the
foundation in demo mode. No client-facing surface here (admin-only, behind
ENABLE_ADMIN_DASHBOARD).
"""
from django.contrib import admin

from .models import (
    Lead,
    Partner,
    ProgramRedirectRule,
    Prospect,
    Referral,
    ReferralIdentity,
    ReferralProgram,
)


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


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "submitted_by", "consent", "referral", "created_at")
    list_filter = ("status", "submitted_by")
