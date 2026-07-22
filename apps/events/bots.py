"""Bot / preview user-agent detection (Gap 16).

The instant a link is shared, messaging/preview bots fetch the URL to render a
preview. Such hits are logged but EXCLUDED from human counts, and — critically —
a bot preview NEVER creates a referral identity/referral and NEVER 302s as a human
click. This module only classifies; the redirect service enforces the behaviour.
"""
from __future__ import annotations

# Substrings matched case-insensitively against the User-Agent header.
BOT_UA_MARKERS = (
    "whatsapp",
    "facebookexternalhit",
    # Meta's WhatsApp link-preview crawler observed live on 2026-07-20 hitting
    # /r/{id} with UA "facebookexternalua" (not caught by "facebookexternalhit").
    "facebookexternalua",
    # Meta's newer documented crawler UAs (meta-externalagent / meta-externalfetcher).
    "meta-external",
    "telegrambot",
    "slackbot",
    "twitterbot",
    "linkedinbot",
    "googlebot",
    "bingbot",
    "embedly",
    "quora link preview",
    "pinterest",
    "redditbot",
    "discordbot",
    "prefetch",
    "preview",
)


def is_bot_user_agent(user_agent: str | None) -> bool:
    """True if the UA looks like a preview/prefetch bot (not a real human browser)."""
    if not user_agent:
        # A missing UA on a redirect is treated as non-human (never credit a click).
        return True
    ua = user_agent.lower()
    return any(marker in ua for marker in BOT_UA_MARKERS)


# SYNTHETIC traffic (owner decision 2026-07-22): our own test/ops tooling. Unlike
# bots it MUST exercise the real capture flow (golive_smoke exists to prove the
# whole loop), so it is never blocked at capture — it is excluded at COUNT time so
# smoke runs stop inflating real referrer analytics (live finding: EKU497's clicks
# were entirely GoLiveSmoke/curl traffic rendered as "Human").
SYNTHETIC_UA_MARKERS = (
    "gorefergolivesmoke",
    "curl/",
)


def is_synthetic_user_agent(user_agent: str | None) -> bool:
    """True if the UA is our own test/ops tooling (counted nowhere, never blocked)."""
    ua = (user_agent or "").lower()
    return any(marker in ua for marker in SYNTHETIC_UA_MARKERS)


def exclude_synthetic(qs):
    """Filter an Event queryset down to non-synthetic rows (count-time exclusion)."""
    from django.db.models import Q

    cond = Q()
    for marker in SYNTHETIC_UA_MARKERS:
        cond |= Q(user_agent__icontains=marker)
    return qs.exclude(cond)
