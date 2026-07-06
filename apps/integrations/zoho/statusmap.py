"""Explicit Zoho-status → GoRefer-stage map (#12).

Past "Redirected", Zoho is the SOLE authority — GoRefer mirrors and never advances
a stage on its own. `account_opened` is the default terminal; `rewarded` is
reachable ONLY if Zoho supplies a reward signal (reward amounts live only in the
Zerodha Console — never computed/stored).
"""
from __future__ import annotations

from apps.events import vocab

# Zoho Lead/Contact status → GoRefer conversion stage (the mirror).
ZOHO_STATUS_TO_STAGE = {
    "new": "new",
    "contacted": "contacted",
    "interested": "interested",
    "kyc started": "kyc_started",
    "kyc_started": "kyc_started",
    "account opened": "account_opened",
    "account_opened": "account_opened",
    "rejected": "rejected",
}

# The stage that fires the account_opened event (default terminal).
TERMINAL_ACCOUNT_STAGE = "account_opened"

# GoRefer stage → the funnel/analytics event it produces (Zoho-sourced only).
STAGE_TO_EVENT = {
    "account_opened": vocab.ACCOUNT_OPENED,
    "rewarded": vocab.REWARD_STATUS_CHANGED,
}


def map_zoho_status(zoho_status: str) -> str:
    """Map a raw Zoho status string to a GoRefer stage (lowercased, trimmed)."""
    return ZOHO_STATUS_TO_STAGE.get((zoho_status or "").strip().lower(), "")
