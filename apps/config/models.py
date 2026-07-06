"""3-tier configuration cascade (ADR-022): central -> global -> user.

A read resolves config_user -> config_global -> config_central, first hit wins
(most-specific). Central is the product-wide baseline; global is a per-tenant
admin override; user is a per-user override.

Sprint 1: the **user tier is dormant** behind ENABLE_CUSTOMER_LOGIN — the table
exists and the resolver checks it, but nothing writes to it until customer login
ships. Compliance keys (e.g. the incentive claim) are baseline in central and are
NOT weakenable by lower tiers (ADR-014/ADR-022 compliance lock) — enforced by the
resolver's compliance-key guard.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import AuditedModel

# Keys that lower config tiers may never override (compliance lock, ADR-022).
COMPLIANCE_LOCKED_KEYS = frozenset({"referral_incentive_claim", "ap_disclosure_block", "nse_ap_no"})


class ConfigCentral(AuditedModel):
    """Product-wide baseline shipped with GoRefer (immutable to tenants)."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "config_central"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"central:{self.key}"


class ConfigGlobal(AuditedModel):
    """Per-tenant admin override of the central baseline."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="config_global")
    key = models.CharField(max_length=100)
    value = models.JSONField()

    class Meta:
        db_table = "config_global"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uq_config_global_tenant_key"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"global:{self.tenant_id}:{self.key}"


class ConfigUser(AuditedModel):
    """Per-user override of the global layer. DORMANT in Sprint 1 (no writers)."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="config_user")
    user_id = models.BigIntegerField()
    key = models.CharField(max_length=100)
    value = models.JSONField()

    class Meta:
        db_table = "config_user"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user_id", "key"], name="uq_config_user_tenant_user_key"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"user:{self.tenant_id}:{self.user_id}:{self.key}"
