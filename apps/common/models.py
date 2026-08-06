"""Shared abstract model mixins (audit, soft-delete, tenant scoping).

These encode the 05-Database-Design §2 conventions once, so every important table
gets the same audit/soft-delete columns and every tenant-scoped table gets a
`tenant_id` from day one (ADR-023). Abstract only — no tables of their own.
"""
from __future__ import annotations

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditedModel(TimestampedModel):
    """Audit columns per 05 §2 (created_by/updated_by resolved to admin users later)."""

    created_by = models.BigIntegerField(null=True, blank=True)
    updated_by = models.BigIntegerField(null=True, blank=True)
    version = models.IntegerField(default=1)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Soft-delete columns per 05 §2. A row is live when deleted_at IS NULL."""

    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.BigIntegerField(null=True, blank=True)
    delete_reason = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_live(self) -> bool:
        return self.deleted_at is None


class TenantQuerySet(models.QuerySet):
    """QuerySet for tenant-scoped tables — the single choke point for tenant filters.

    Every tenant-scoped read in production source goes through `for_tenant()`
    (T-049) — it is the one place hierarchy-aware visibility (doc 16 §3.1 "parent
    sees its subtree") will be implemented when Phase 4 lands. A raw
    `filter(tenant=...)` outside this method fails the E-7 rail
    (`tests/test_tenant_scoping_rail.py`), so the scope has exactly one
    implementation instead of ~90 remembered ones.

    Accepts a Tenant instance, a raw id, or None — identical semantics to the
    `filter(tenant=...)` it replaces (None means "rows with no tenant").
    """

    def for_tenant(self, tenant_or_id):
        tenant_id = getattr(tenant_or_id, "id", tenant_or_id)
        return self.filter(tenant_id=tenant_id)


class TenantScopedModel(models.Model):
    """Carries the ADR-023 `tenant_id` discriminator.

    FK to tenants.Tenant. Nullable in Sprint 1 only so the single bootstrap tenant
    can be backfilled cleanly; every tenant-scoped uniqueness constraint includes
    this column (per 05 §2). Physical isolation (schema-per-tenant vs discriminator)
    is decided at multi-tenant-enable time — see COORDINATION Q-M1-1.

    `objects.for_tenant(...)` is the scoped-query helper (see TenantQuerySet).
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True
