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
        "FEATURE_FLAGS": flags,
    }
