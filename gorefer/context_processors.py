"""Template context processors.

`compliance` injects the single swappable incentive claim + AP registration into
every rendered template, so compliance surfaces are available everywhere without a
view having to remember them (ADR-014). M1 only exposes the values; M3 renders the
full disclosure block from them.
"""
from __future__ import annotations

from django.conf import settings

from gorefer.flags import flags


def compliance(request):
    return {
        "REFERRAL_INCENTIVE_CLAIM": flags.REFERRAL_INCENTIVE_CLAIM,
        "NSE_AP_NO": getattr(settings, "NSE_AP_NO", ""),
        # Canonical, byte-exact compliance strings — single source (ADR-014), rendered
        # verbatim on every customer page so wording can never drift.
        "AP_DISCLOSURE_BLOCK": getattr(settings, "AP_DISCLOSURE_BLOCK", ""),
        "MARKET_RISK_WARNING": getattr(settings, "MARKET_RISK_WARNING", ""),
        "SUPPORT_HELPLINE_PHONE": getattr(settings, "SUPPORT_HELPLINE_PHONE", ""),
        # tel:-safe form of the helpline (strip spaces so it dials from the display value).
        "SUPPORT_HELPLINE_TEL": getattr(settings, "SUPPORT_HELPLINE_PHONE", "").replace(" ", ""),
        "FEATURE_FLAGS": flags,
    }
