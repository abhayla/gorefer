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
        row = ConfigUser.objects.filter(tenant_id=tenant_id, user_id=user_id, key=key).first()
        if row is not None:
            return row.value

    if not locked and tenant_id is not None:
        row = ConfigGlobal.objects.filter(tenant_id=tenant_id, key=key).first()
        if row is not None:
            return row.value

    row = ConfigCentral.objects.filter(key=key).first()
    if row is not None:
        return row.value

    if default is _UNSET:
        raise KeyError(f"config key not found and no default: {key!r}")
    return default
