"""Tenant + Domain models for the ADR-023 multi-tenant boundary.

Uses django-tenants' TenantMixin/DomainMixin so the schema-per-tenant router can
light up in PostgreSQL deploys. On SQLite these are plain models (no schema
routing); the boundary is scaffolded now, with one bootstrap tenant (PIFS).

Sprint 1 runs a single tenant. `tenant_id` discriminator columns on the referral
domain tables (05-Database-Design §2) coexist with this so attribution/uniqueness
stays per-tenant regardless of which physical isolation strategy is chosen at
multi-tenant-enable time (see COORDINATION Q-M1-1).
"""
from __future__ import annotations

from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Tenant(TenantMixin):
    """A GoRefer tenant (Sprint 1: PIFS only).

    `schema_name` comes from TenantMixin (the Postgres schema for this tenant).
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Auto-create/drop the Postgres schema on save/delete (no-op on SQLite).
    auto_create_schema = True

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    """A hostname routed to a tenant (e.g. gorefer.in -> PIFS)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.domain
