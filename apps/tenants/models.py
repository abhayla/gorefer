"""Tenant + Domain registry for the ADR-023 multi-tenant boundary.

Multi-tenancy is SINGLE-SCHEMA `tenant_id` discriminator (COORDINATION Q-M1-1):
these are PLAIN models — a lightweight registry — with NO django-tenants schema
routing. Isolation is enforced by TenantResolutionMiddleware + composite unique
constraints + per-call-site `tenant=` filters (05-Database-Design §2);
`TenantQuerySet.for_tenant()` (apps/common/models.py) is the scoped-query helper
new code should use (doc 16 D-4 — this docstring previously claimed tenant-scoped
managers that did not exist). Sprint 1 runs one tenant (PIFS). Schema-per-tenant
physical isolation is deferred to backlog DF-7.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Tenant(models.Model):
    """A GoRefer tenant (Sprint 1: PIFS only)."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.slug})"


class Domain(models.Model):
    """A hostname mapped to a tenant (e.g. gorefer.in -> PIFS)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    domain = models.CharField(max_length=253, unique=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "tenant_domains"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.domain


class StaffTenantBinding(models.Model):
    """S2-06: binds one staff user to one tenant (AP) — that user is an AP admin.

    One-to-one: an AP admin sees exactly one AP. The role is resolved ONLY by
    `apps.tenants.access.resolve_role`; never read this table to decide access directly.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_tenant_binding"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="staff_bindings")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_tenant_bindings"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.user} -> {self.tenant}"


class StaffAccess(models.Model):
    """Who may open the admin report, and with which roles (owner decision 2026-11-28).

    One row per Google email, managed by an owner on /admin-panel/access/. A person may
    hold several roles at once and switch with "View as" on the report page:
      * owner   — every business, plus platform health and the access list;
      * admin   — every business's referral numbers and messages (operations);
      * manager — one business only (`manager_tenant`), e.g. the PIFS manager.
    This supersedes the S2-06 one-role rule for anyone with a row here (owner-approved
    2026-11-28); users with no row keep the S2-06 behaviour exactly. Roles are resolved
    ONLY by `apps.tenants.access`; never read this table to decide access directly.
    A revoked row (`revoked_at` set) grants nothing; rows are never deleted (audit).
    """

    email = models.EmailField(unique=True)  # stored lower-case
    is_owner = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    manager_tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.PROTECT, related_name="staff_managers"
    )
    granted_by = models.CharField(max_length=254, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "staff_access"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_active_grant(self) -> bool:
        has_role = self.is_owner or self.is_admin or self.manager_tenant_id is not None
        return self.revoked_at is None and has_role

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.email


class StaffAccessLog(models.Model):
    """Append-only record of every access-list change: who, what, when."""

    actor_email = models.CharField(max_length=254)
    action = models.CharField(max_length=20)  # grant | change | revoke
    target_email = models.CharField(max_length=254)
    roles = models.JSONField(default=list)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_access_log"
        ordering = ["-at"]
