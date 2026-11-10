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


def resolve_role(user) -> Role:
    try:
        if user is None or not user.is_authenticated or not user.is_active or not user.is_staff:
            return _DENIED
        from .models import StaffTenantBinding

        binding = (
            StaffTenantBinding.objects.select_related("tenant").filter(user_id=user.pk).first()
        )
        if binding is not None:
            if binding.tenant is not None and binding.tenant.is_active:
                return Role(AP_ADMIN, binding.tenant)
            return _DENIED  # bound to an inactive AP: never fall back to super-admin
        if user.is_superuser is True:
            return Role(SUPER_ADMIN)
        return _DENIED
    except Exception:  # fail closed on anything unexpected
        return _DENIED


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
