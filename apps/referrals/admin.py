"""Admin registrations — the base the M7 dashboard builds on.

Read-mostly views of the seeded program/partner so an admin can confirm the
foundation in demo mode. No client-facing surface here (admin-only, behind
ENABLE_ADMIN_DASHBOARD).
"""
from django.contrib import admin

from .models import Partner, ProgramRedirectRule, ReferralProgram


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
