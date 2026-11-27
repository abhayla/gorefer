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
SHARE_INTENT = "share_intent"          # one-tap share endpoint hit (M-WATI-1)
SHARE_RECOVERY_VIEWED = "share_recovery_viewed"  # soft-landing recovery page viewed (T-122)
DISCLOSURE_VIEWED = "disclosure_viewed"  # public /d/{slug} disclosure page viewed (T-link-tracking)
KITE_PROMPT_ACTION = "kite_prompt_action"  # a button on the Kite ID pop-up was used (T-link-tracking)
NOTIFICATION = "notification"          # a WATI transactional message reached a terminal status

# Kite ID pop-up: which mode it ran in (metadata["prompt"]) and what the person did
# (metadata["action"]). A WRONG entry records only its reason, never the typed text
# (it may be a mobile number — PII, #16); an ENTERED one records the validated, public
# client_id (ADR-001: the id is already public).
PROMPT_MODE_SHARE = "share"
PROMPT_MODE_REFERRAL = "referral"
PROMPT_ACTION_ENTERED = "entered"
PROMPT_ACTION_SKIP = "skip"
PROMPT_ACTION_WRONG = "wrong"
PROMPT_WRONG_EMPTY = "empty"
PROMPT_WRONG_SHAPE = "shape"
PROMPT_WRONG_PLACEHOLDER = "placeholder"
PROMPT_WRONG_DELETED = "deleted"

# Where a partner-direct (no-referrer) click came from — metadata["origin"]. Every one of
# these lands on the same partner-direct referral row, so only this tag tells them apart.
ORIGIN_OPEN = "open"              # /open, /open/{channel}[/{lang}]
ORIGIN_R_OPEN = "r_open"          # /r/open — the reserved no-referrer link
ORIGIN_POPUP_SKIP = "popup_skip"  # "I don't have one, continue" on the referral pop-up
ORIGIN_FALLBACK = "fallback"      # a broken public link redirected to the default open link

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
SRC_WATI = "wati"

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
