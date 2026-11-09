"""Django admin: a super-admin creates AP admins here (S2-06) — no new user screen."""
from django.contrib import admin

from .models import StaffTenantBinding


@admin.register(StaffTenantBinding)
class StaffTenantBindingAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "created_at")
    list_filter = ("tenant",)
    raw_id_fields = ("user",)
