"""Neutral delivery-status vocabulary (ADR-045).

Re-exports the WATI status helpers so domain code can stop importing
`apps.integrations.wati.status` directly. The implementation stays in
`apps.integrations.wati.status` — this module is the vendor-neutral name for it.
"""
from __future__ import annotations

from apps.integrations.wati.status import (
    classify_failure,
    is_delivered,
    is_terminal,
    status_rank,
    supersedes,
)

__all__ = ["is_terminal", "is_delivered", "classify_failure", "supersedes", "status_rank"]
