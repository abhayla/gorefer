"""Config cascade resolver (ADR-022).

resolve() returns the most-specific configured value for a key:
    config_user -> config_global -> config_central -> default

Compliance-locked keys (COMPLIANCE_LOCKED_KEYS) ignore the user/global tiers and
resolve straight from central, so lower tiers can never weaken a compliance claim.
The user tier is only consulted when ENABLE_CUSTOMER_LOGIN is on (dormant in
Sprint 1).
"""
from __future__ import annotations

from typing import Any

from gorefer.flags import flags

from .models import COMPLIANCE_LOCKED_KEYS, ConfigCentral, ConfigGlobal, ConfigUser

_UNSET = object()


def resolve(
    key: str,
    *,
    tenant_id: int | None = None,
    user_id: int | None = None,
    default: Any = _UNSET,
) -> Any:
    """Resolve a config key through the 3-tier cascade, most-specific wins."""
    locked = key in COMPLIANCE_LOCKED_KEYS

    if not locked and user_id is not None and flags.ENABLE_CUSTOMER_LOGIN and tenant_id is not None:
        row = ConfigUser.objects.for_tenant(tenant_id).filter(user_id=user_id, key=key).first()
        if row is not None:
            return row.value

    if not locked and tenant_id is not None:
        row = ConfigGlobal.objects.for_tenant(tenant_id).filter(key=key).first()
        if row is not None:
            return row.value

    row = ConfigCentral.objects.filter(key=key).first()
    if row is not None:
        return row.value

    if default is _UNSET:
        raise KeyError(f"config key not found and no default: {key!r}")
    return default


class ComplianceLockedKeyError(ValueError):
    """Raised when a write targets a compliance-locked key at a lower tier."""


def set_tenant(key: str, value: Any, *, tenant_id: int, user=None) -> None:
    """Persist a config value at the GLOBAL (tenant) tier — the user/tenant tier the
    Preferences screen writes to (ADR-022, ADR-034).

    Refuses a compliance-locked key: those resolve straight from central and can
    never be weakened by a lower tier, so persisting one here would be a silent no-op
    that misleads an operator — we fail loud instead. `user` (optional) stamps
    updated_by for the audit trail.
    """
    if key in COMPLIANCE_LOCKED_KEYS:
        raise ComplianceLockedKeyError(
            f"{key!r} is compliance-locked and cannot be set at the tenant tier "
            "(it resolves from central only)."
        )
    defaults: dict[str, Any] = {"value": value}
    if user is not None and getattr(user, "pk", None):
        defaults["updated_by"] = user.pk
    ConfigGlobal.objects.update_or_create(
        tenant_id=tenant_id, key=key, defaults=defaults
    )
