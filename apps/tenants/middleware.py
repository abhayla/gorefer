"""Tenant-resolution middleware (single-schema discriminator, Q-M1-1).

Resolves the active tenant per request and stashes it on `request.tenant`, so
tenant-scoped writes (M2 lazy journey/click) stamp the correct `tenant_id`.

Sprint 1 runs ONE tenant (PIFS). Resolution order:
  1. hostname match against the Domain registry (future multi-tenant),
  2. fall back to the single bootstrap tenant.
Resolution is cached per process to avoid a DB hit on the hot redirect path.
"""
from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from .resolve import resolve_tenant_for_host


class TenantResolutionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(":")[0] if request.get_host() else ""
        request.tenant = resolve_tenant_for_host(host)
        return None
