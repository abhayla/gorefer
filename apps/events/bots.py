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
