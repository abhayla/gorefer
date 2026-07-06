"""Tenant resolution helpers (single-schema discriminator, Q-M1-1).

`resolve_tenant_for_host` maps a hostname to a Tenant via the Domain registry,
falling back to the single bootstrap tenant (PIFS). `get_current_tenant` is the
convenience used off-request (management commands, background writes).

Sprint 1: exactly one tenant, so resolution effectively always returns PIFS — but
the seam is real so a second tenant is a data addition, not a rewrite.
"""
from __future__ import annotations

from .models import Domain, Tenant

BOOTSTRAP_TENANT_SLUG = "pifs"


def get_bootstrap_tenant() -> Tenant | None:
    return Tenant.objects.filter(slug=BOOTSTRAP_TENANT_SLUG, is_active=True).first()


def resolve_tenant_for_host(host: str) -> Tenant | None:
    """Resolve the tenant for a hostname; fall back to the bootstrap tenant."""
    if host:
        domain = Domain.objects.select_related("tenant").filter(domain=host).first()
        if domain is not None and domain.tenant.is_active:
            return domain.tenant
    return get_bootstrap_tenant()


def get_current_tenant(request=None) -> Tenant | None:
    """Return the request's resolved tenant, or the bootstrap tenant off-request."""
    if request is not None and getattr(request, "tenant", None) is not None:
        return request.tenant
    return get_bootstrap_tenant()
