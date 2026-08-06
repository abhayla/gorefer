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
STATUS_BLOCKED = "blocked"     # refused by the fail-closed recipient allowlist — never sent
# Demo/log-only "delivery": the LogOnlyWatiAdapter made NO network call, so this is a
# SIMULATED terminal status, not a real one (Fable5 M7). Kept distinct from
# STATUS_DELIVERED so a demo/degraded send is never counted as a real delivery.
STATUS_SIMULATED_DELIVERED = "simulated_delivered"

# A terminal status is one the message will not move past. simulated_delivered is
# terminal for the demo path (nothing further will happen) but excluded from the
# real-delivery sets below.
TERMINAL_STATUSES = frozenset(
    {STATUS_DELIVERED, STATUS_READ, STATUS_FAILED, STATUS_SIMULATED_DELIVERED}
)
# Delivery is only proven by one of these (read implies delivered). simulated_delivered
# is deliberately NOT here — a demo send must never register as a real delivery.
DELIVERED_STATUSES = frozenset({STATUS_DELIVERED, STATUS_READ})

# Meta failure codes we classify (doc-08 A3/A4).
META_ERROR_MEANINGS = {
    131049: "per-user marketing cap (Meta 131049)",
    131048: "spam/quality rate limit (Meta 131048)",
    131026: "message undeliverable / not opted in (Meta 131026)",
    131047: "re-engagement required — 24h window closed (Meta 131047)",
    470: "template paused/disabled (Meta 470)",
}


# --- status ordering / stale-status guard (T-048) ---------------------------
#
# Delivery status only ever moves FORWARD. Nothing that arrives later — a replayed
# webhook, a reconcile sweep re-reading an old getMessages page, a duplicate task —
# may walk a message BACKWARDS from a status it has already reached.
#
# Ranks encode "how far along" a message is, not how good the news is:
#   accepted(1) < sent(2) < {delivered, failed, blocked, simulated_delivered}(3) < read(4)
# `failed` shares rank 3 with `delivered` deliberately: they are mutually exclusive
# OUTCOMES of the same step, so neither may overwrite the other. Whichever terminal
# outcome we observed first is the one we keep — we never flip a recorded delivery into
# a failure (or the reverse) on a late re-read.
_STATUS_RANK = {
    STATUS_ACCEPTED: 1,
    STATUS_SENT: 2,
    STATUS_DELIVERED: 3,
    STATUS_FAILED: 3,
    STATUS_BLOCKED: 3,
    STATUS_SIMULATED_DELIVERED: 3,
    STATUS_READ: 4,
}
# An unknown/queued status ranks below everything known, so it can never displace a
# recorded outcome — and a known status always beats it.
_UNKNOWN_RANK = 0


def status_rank(status: str) -> int:
    return _STATUS_RANK.get(status, _UNKNOWN_RANK)


def supersedes(current: str, incoming: str) -> bool:
    """May `incoming` replace `current`? Only if it is strictly further along.

    This is THE guard against a stale status overwriting a newer one. Examples:
      supersedes("accepted", "delivered") -> True   (normal progression)
      supersedes("delivered", "read")     -> True   (read implies delivered)
      supersedes("delivered", "sent")     -> False  (a replayed older status)
      supersedes("delivered", "failed")   -> False  (never flip a recorded outcome)
      supersedes("read", "read")          -> False  (a duplicate is a no-op)
    """
    return status_rank(incoming) > status_rank(current)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_delivered(status: str) -> bool:
    return status in DELIVERED_STATUSES


def classify_failure(meta_error_code: int | None) -> str:
    """Human-readable classification for a Meta error code (or 'unknown')."""
    if meta_error_code is None:
        return "unknown failure"
    return META_ERROR_MEANINGS.get(meta_error_code, f"unclassified Meta error {meta_error_code}")
