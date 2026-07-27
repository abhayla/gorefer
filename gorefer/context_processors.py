"""Template context processors.

`compliance` injects the single swappable incentive claim + AP registration into
every rendered template, so compliance surfaces are available everywhere without a
view having to remember them (ADR-014). M1 only exposes the values; M3 renders the
full disclosure block from them.

Phase 0 (doc 16 D-1): the compliance strings resolve through the LOCKED config
cascade (central-only, ADR-037 semantics) with the canonical settings/flags values
as byte-identical defaults. Before this, the locked keys had zero production
readers — the lock guarded rows nothing consumed. Rail E-2 asserts the rendered
output tracks the resolver.
"""
from __future__ import annotations

from django.conf import settings

from apps.config.cascade import resolve
from gorefer.flags import flags


def compliance(request):
    return {
        "REFERRAL_INCENTIVE_CLAIM": resolve(
            "referral_incentive_claim", default=flags.REFERRAL_INCENTIVE_CLAIM
        ),
        "NSE_AP_NO": resolve("nse_ap_no", default=getattr(settings, "NSE_AP_NO", "")),
        # Canonical, byte-exact compliance strings — single source (ADR-014), rendered
        # verbatim on every customer page so wording can never drift. Locked keys
        # resolve central-only; the settings constants are the seed values AND the
        # defaults, so an unseeded database renders byte-identically.
        "AP_DISCLOSURE_BLOCK": resolve(
            "ap_disclosure_block", default=getattr(settings, "AP_DISCLOSURE_BLOCK", "")
        ),
        "MARKET_RISK_WARNING": resolve(
            "market_risk_warning", default=getattr(settings, "MARKET_RISK_WARNING", "")
        ),
        "SUPPORT_HELPLINE_PHONE": getattr(settings, "SUPPORT_HELPLINE_PHONE", ""),
        # tel:-safe form of the helpline (strip spaces so it dials from the display value).
        "SUPPORT_HELPLINE_TEL": getattr(settings, "SUPPORT_HELPLINE_PHONE", "").replace(" ", ""),
        "FEATURE_FLAGS": flags,
    }
