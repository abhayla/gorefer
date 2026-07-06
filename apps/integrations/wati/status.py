"""WATI/Meta message-status lifecycle + failure classification (doc-08 A3).

HTTP 200 from WATI means "accepted", NOT "delivered". Delivery is verified by the
TERMINAL message status (delivered/read/failed), and failures are classified by
Meta error code. This module holds the vocabulary + classifier only.
"""
from __future__ import annotations

# Message-status lifecycle (WATI/Meta).
STATUS_ACCEPTED = "accepted"   # HTTP 200 — NOT proof of delivery
STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_READ = "read"
STATUS_FAILED = "failed"

# A terminal status is one the message will not move past.
TERMINAL_STATUSES = frozenset({STATUS_DELIVERED, STATUS_READ, STATUS_FAILED})
# Delivery is only proven by one of these (read implies delivered).
DELIVERED_STATUSES = frozenset({STATUS_DELIVERED, STATUS_READ})

# Meta failure codes we classify (doc-08 A3/A4).
META_ERROR_MEANINGS = {
    131049: "per-user marketing cap (Meta 131049)",
    131048: "spam/quality rate limit (Meta 131048)",
    131026: "message undeliverable / not opted in (Meta 131026)",
    131047: "re-engagement required — 24h window closed (Meta 131047)",
    470: "template paused/disabled (Meta 470)",
}


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_delivered(status: str) -> bool:
    return status in DELIVERED_STATUSES


def classify_failure(meta_error_code: int | None) -> str:
    """Human-readable classification for a Meta error code (or 'unknown')."""
    if meta_error_code is None:
        return "unknown failure"
    return META_ERROR_MEANINGS.get(meta_error_code, f"unclassified Meta error {meta_error_code}")
