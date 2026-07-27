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
