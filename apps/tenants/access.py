"""S2-06 — the ONE admin-role resolver. Every staff gate calls this; none re-derives it.

Roles (spec S2-06 "Access"):
- super-admin: active staff superuser with NO tenant binding -> every AP.
- AP admin: active staff user with a StaffTenantBinding to an ACTIVE tenant -> that AP only.
  The binding wins even for a superuser (the narrower scope wins).
- anything else -> denied (fail closed: an unclassifiable state is never promoted).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test

SUPER_ADMIN = "super_admin"
AP_ADMIN = "ap_admin"
DENIED = "denied"


@dataclass(frozen=True)
class Role:
    kind: str
    tenant: object = None  # the bound Tenant for an AP admin; None otherwise

    @property
    def is_super_admin(self) -> bool:
        return self.kind == SUPER_ADMIN

    @property
    def is_ap_admin(self) -> bool:
        return self.kind == AP_ADMIN


_DENIED = Role(DENIED)


#: The roles a person can hold at once (owner decision 2026-11-28; see StaffAccess).
OWNER = "owner"
ADMIN = "admin"
MANAGER = "manager"
ROLE_ORDER = (OWNER, ADMIN, MANAGER)  # widest first: the default "View as"


@dataclass(frozen=True)
class Grant:
    """One role a person holds. `tenant` is set only for MANAGER (the one business)."""
    role: str
    tenant: object = None

    @property
    def sees_all_businesses(self) -> bool:
        return self.role in (OWNER, ADMIN)


def _staff_access_row(user):
    from .models import StaffAccess

    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return None
    row = (
        StaffAccess.objects.select_related("manager_tenant")
        .filter(email=email, revoked_at__isnull=True).first()
    )
    return row if row is not None and row.is_active_grant else None


def _legacy_role(user) -> Role:
    """The S2-06 one-role rule, unchanged, for staff with no StaffAccess row."""
    from .models import StaffTenantBinding

    binding = StaffTenantBinding.objects.select_related("tenant").filter(user_id=user.pk).first()
    if binding is not None:
        if binding.tenant is not None and binding.tenant.is_active:
            return Role(AP_ADMIN, binding.tenant)
        return _DENIED  # bound to an inactive AP: never fall back to super-admin
    if user.is_superuser is True:
        return Role(SUPER_ADMIN)
    return _DENIED


def resolve_grants(user) -> list[Grant]:
    """Every role this person holds, widest first. [] = no access (fail closed).

    A StaffAccess row (the owner-managed access list) decides alone when present.
    Without one, the S2-06 role maps over: super-admin -> owner + admin, AP admin ->
    manager of that business. An inactive business grants nothing.
    """
    try:
        if user is None or not user.is_authenticated or not user.is_active or not user.is_staff:
            return []
        row = _staff_access_row(user)
        if row is not None:
            grants = []
            if row.is_owner:
                grants.append(Grant(OWNER))
            if row.is_admin:
                grants.append(Grant(ADMIN))
            if row.manager_tenant is not None and row.manager_tenant.is_active:
                grants.append(Grant(MANAGER, row.manager_tenant))
            return grants
        legacy = _legacy_role(user)
        if legacy.kind == SUPER_ADMIN:
            return [Grant(OWNER), Grant(ADMIN)]
        if legacy.kind == AP_ADMIN:
            return [Grant(MANAGER, legacy.tenant)]
        return []
    except Exception:  # fail closed on anything unexpected
        return []


def resolve_role(user) -> Role:
    """The single S2-06 role every existing admin page gates on.

    Owner or admin -> super-admin; manager only -> that business's AP admin. For staff
    with no StaffAccess row this is exactly the S2-06 rule (binding wins)."""
    try:
        if user is None or not user.is_authenticated or not user.is_active or not user.is_staff:
            return _DENIED
        if _staff_access_row(user) is None:
            return _legacy_role(user)
        grants = resolve_grants(user)
        if any(g.sees_all_businesses for g in grants):
            return Role(SUPER_ADMIN)
        for g in grants:
            if g.role == MANAGER:
                return Role(AP_ADMIN, g.tenant)
        return _DENIED
    except Exception:  # fail closed on anything unexpected
        return _DENIED


def is_owner(user) -> bool:
    return any(g.role == OWNER for g in resolve_grants(user))


def is_super_admin(user) -> bool:
    return resolve_role(user).is_super_admin


def _gate(test):
    def deco(view):
        return login_required(
            user_passes_test(test, login_url="dashboard_login")(view),
            login_url="dashboard_login",
        )
    return deco


#: Every pre-existing admin page: super-admin only (they resolve the tenant from the domain).
super_admin_required = _gate(is_super_admin)

#: The access list (who may sign in, with which roles): owners only.
owner_required = _gate(is_owner)


def report_access_required(view):
    """S2-06 report pages: super-admin or AP admin; the view gets `request.admin_role`."""
    @_gate(lambda u: resolve_role(u).kind in (SUPER_ADMIN, AP_ADMIN))
    @wraps(view)
    def inner(request, *args, **kwargs):
        request.admin_role = resolve_role(request.user)
        if request.admin_role.kind not in (SUPER_ADMIN, AP_ADMIN):  # re-check, fail closed
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        return view(request, *args, **kwargs)
    return inner


#: The role-based report page: anyone holding at least one role.
any_role_required = _gate(lambda u: bool(resolve_grants(u)))
