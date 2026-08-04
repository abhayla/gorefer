"""Vendor-neutral aggregation of the boundary's inbound HTTP routers (ADR-046).

`api/router.py` mounts `wati_router` / `zoho_router` from here rather than importing
`apps.integrations.wati.api` / `apps.integrations.zoho.api` directly — the webhook
routers are part of the vendor boundary (they parse vendor-shaped payloads by
definition), and this module is the front door domain code (and `api/router.py`)
reaches them through. URL paths, auth ordering, and response shapes are unchanged
by this move.
"""
from __future__ import annotations

from apps.integrations.wati.api import router as wati_router
from apps.integrations.zoho.api import router as zoho_router

__all__ = ["wati_router", "zoho_router"]
