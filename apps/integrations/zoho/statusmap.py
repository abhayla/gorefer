"""Explicit Zoho-status → GoRefer-stage map (#12).

Past "Redirected", Zoho is the SOLE authority — GoRefer mirrors and never advances
a stage on its own. `account_opened` is the default terminal; `rewarded` is
reachable ONLY if Zoho supplies a reward signal (reward amounts live only in the
Zerodha Console — never computed/stored).
"""
from __future__ import annotations

from apps.events import vocab

# Zoho Lead/Contact status → GoRefer conversion stage (the mirror). Keys are matched
# lowercased+trimmed. Includes the REAL PIFS Leads picklist values (verified against the
# live Zoho Leads layout) alongside the generic ones — so a real "Account Opened with Us"
# is mapped EXPLICITLY, not merely caught by the account_opened fallback in ingest.
ZOHO_STATUS_TO_STAGE = {
    "new": "new",
    "not contacted": "new",
    "contacted": "contacted",
    "attempted to contact": "contacted",
    "call not picked": "contacted",
    "contact in future": "contacted",
    "interested": "interested",
    "pre-qualified": "interested",
    "in-progress": "kyc_started",
    "kyc started": "kyc_started",
    "kyc_started": "kyc_started",
    "account opened": "account_opened",
    "account_opened": "account_opened",
    # Real PIFS "opened" picklist value that credits PIFS (verified from the live Leads
    # layout). "Opened with Other Broker/Partner" is deliberately NOT mapped to a PIFS
    # conversion — those accounts weren't opened with us; if the workflow ever fires on
    # them, ingest's `or "account_opened"` fallback still records the journey, but they
    # are not asserted here as a PIFS conversion.
    "account opened with us": "account_opened",
    "rejected": "rejected",
    "not interested": "rejected",
    "junk lead": "rejected",
    "lost lead": "rejected",
    "not qualified": "rejected",
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
