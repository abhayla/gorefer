"""Canonical event vocabulary (DA decision, M3 review → M4).

snake_case names are canonical; doc-06's UPPER_CASE names are superseded. Every
event carries a source/origin tag + timestamp (#18). Keep all event-type strings
here so producers and the analytics read models agree.
"""
from __future__ import annotations

# Observed on-platform events (real-time, from the click/landing/redirect/form path).
LINK_CREATED = "link_created"          # a link exists (lazy: first observed activity)
CLICK = "click"                        # a referral link / partner-direct hit
LANDING_VIEWED = "landing_viewed"      # branded landing rendered
HUMAN_CONFIRMED = "human_confirmed"    # JS confirmation beacon cleared (real human)
LEAD_CAPTURED = "lead_captured"        # capture-first form submit saved a lead
REDIRECT_COMPLETED = "redirect_completed"  # user tapped Continue -> 302 to Zerodha
SHARE_CLICKED = "share_clicked"        # referrer shared the link on a channel

# Downstream events — ONLY ever produced from Zoho (M6). Never fabricated here.
ACCOUNT_OPENED = "account_opened"
REWARD_STATUS_CHANGED = "reward_status_changed"
CONVERSION_REMOVED = "conversion_removed"

# Source/origin tags (#18).
SRC_SYSTEM = "system"
SRC_CLICK = "click"
SRC_FORM = "form"
SRC_REDIRECT = "redirect"
SRC_BEACON = "beacon"
SRC_ZOHO = "zoho"

# The ordered funnel stages the journey timeline + funnel aggregation report on.
# account_opened is source-only (Zoho, M6) and stays 0 / "pending Zoho" until then.
FUNNEL_STAGES = [
    ("link_created", "Link created"),
    ("click", "Clicked"),
    ("landing_viewed", "Landing viewed"),
    ("redirect_completed", "Redirected"),
    ("lead_captured", "Lead captured"),
    ("account_opened", "Account opened"),
]

# Events whose truth may ONLY originate in Zoho — an internal write of any of these
# is a never-fabricate violation (asserted by tests; formal guardrail #2 at M6).
ZOHO_ONLY_EVENTS = frozenset({ACCOUNT_OPENED, REWARD_STATUS_CHANGED, CONVERSION_REMOVED})
