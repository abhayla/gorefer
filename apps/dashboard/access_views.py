"""The access list: who may open the admin report, and with which roles (owners only).

Owner decision 2026-11-28 (approved mock-up "Access list"). An owner adds a Google
email and ticks Owner / Admin / <business> manager; access can be changed or removed
at any time; every change is written to StaffAccessLog. Rows are revoked, never deleted.
The last active owner cannot be removed or demoted, so the list can never lock itself.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.tenants.access import owner_required
from apps.tenants.models import StaffAccess, StaffAccessLog, Tenant


def _roles_of(row: StaffAccess) -> list[str]:
    roles = []
    if row.is_owner:
        roles.append("Owner")
    if row.is_admin:
        roles.append("Admin")
    if row.manager_tenant_id:
        roles.append(f"{row.manager_tenant.name} manager")
    return roles


def _active_owner_count(exclude_pk=None) -> int:
    qs = StaffAccess.objects.filter(is_owner=True, revoked_at__isnull=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count()


def _log(request, action: str, row: StaffAccess) -> None:
    StaffAccessLog.objects.create(
        actor_email=(request.user.email or request.user.get_username()).lower(),
        action=action, target_email=row.email, roles=_roles_of(row),
    )


@owner_required
@require_http_methods(["GET", "POST"])
def access_list(request):
    tenants = list(Tenant.objects.filter(is_active=True).order_by("name"))
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        is_owner = request.POST.get("owner") == "on"
        is_admin = request.POST.get("admin") == "on"
        tenant_id = request.POST.get("manager_tenant") or ""
        tenant = next((t for t in tenants if str(t.id) == tenant_id), None)
        try:
            validate_email(email)
        except Exception:
            messages.error(request, "Enter a full Google email address, like name@gmail.com.")
            return redirect("dashboard_access")
        if not (is_owner or is_admin or tenant):
            messages.error(request, "Tick at least one role.")
            return redirect("dashboard_access")
        with transaction.atomic():
            row = StaffAccess.objects.select_for_update().filter(email=email).first()
            if row is not None and row.revoked_at is None and row.is_owner and not is_owner \
                    and _active_owner_count(exclude_pk=row.pk) == 0:
                messages.error(request, "There must always be at least one owner.")
                return redirect("dashboard_access")
            action = "grant" if row is None or row.revoked_at is not None else "change"
            row = row or StaffAccess(email=email)
            row.is_owner, row.is_admin, row.manager_tenant = is_owner, is_admin, tenant
            row.revoked_at = None
            row.granted_by = (request.user.email or request.user.get_username()).lower()
            row.save()
            _log(request, action, row)
        messages.success(request, f"{email} can now sign in as: {', '.join(_roles_of(row))}.")
        return redirect("dashboard_access")

    rows = list(StaffAccess.objects.select_related("manager_tenant").filter(revoked_at__isnull=True)
                .order_by("-is_owner", "email"))
    me = (request.user.email or "").lower()
    people = [{
        "id": r.id, "email": r.email, "roles": " · ".join(_roles_of(r)), "added": r.created_at,
        "is_me": r.email == me,
        "removable": not (r.is_owner and _active_owner_count(exclude_pk=r.pk) == 0),
    } for r in rows]
    return render(request, "dashboard/access.html", {
        "people": people, "tenants": tenants,
        "log": StaffAccessLog.objects.all()[:20],
        "nav_active": "access",
    })


@owner_required
@require_POST
def access_revoke(request, access_id: int):
    with transaction.atomic():
        row = StaffAccess.objects.select_for_update().filter(pk=access_id, revoked_at__isnull=True).first()
        if row is None:
            messages.error(request, "That person no longer has access.")
            return redirect("dashboard_access")
        if row.is_owner and _active_owner_count(exclude_pk=row.pk) == 0:
            messages.error(request, "There must always be at least one owner.")
            return redirect("dashboard_access")
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at", "updated_at"])
        _log(request, "revoke", row)
    messages.success(request, f"Removed access for {row.email}. They are signed out at their next page.")
    return redirect("dashboard_access")
