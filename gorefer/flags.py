"""Feature flags + compliance config — the ONE place flags are read from env.

Per implementation/10 §4 and COORDINATION M1 step 2: flags are loaded from the
environment ONCE at import time into a single frozen object. No feature flag is
ever checked by a raw string literal scattered across the codebase — code imports
`flags` from here and reads an attribute.

This module is intentionally import-safe with **no Django dependency** so it can be
read from settings, management commands, and tests alike.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None else raw


@dataclass(frozen=True)
class FeatureFlags:
    """Immutable snapshot of feature flags, resolved from env at startup.

    Defaults match implementation/10 §4 and the M1 mission brief. The not-yet-built
    capabilities default OFF so nothing half-built is reachable in production, and
    external-system adapters stay dormant (log-only) until explicitly enabled.
    """

    # Later-sprint capabilities — OFF by default (never rendered as dead UI).
    ENABLE_CUSTOMER_LOGIN: bool = False
    ENABLE_ASSET_GENERATOR: bool = False

    # External-system adapters — OFF until credentials/templates verified.
    # When OFF, adapters log the intended call instead of sending (demo-safe).
    ENABLE_WATI_SEND: bool = False
    ENABLE_ZOHO_WRITE: bool = False

    # Sprint-1 surfaces that ARE built.
    ENABLE_ADMIN_DASHBOARD: bool = True
    ENABLE_DEMO_MODE: bool = True

    # Compliance: the single swappable "10% brokerage" claim string (ADR-014).
    # This is the ONLY place the incentive claim wording lives.
    REFERRAL_INCENTIVE_CLAIM: str = "300 reward points + 10% brokerage share"

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        return cls(
            ENABLE_CUSTOMER_LOGIN=_bool("ENABLE_CUSTOMER_LOGIN", cls.ENABLE_CUSTOMER_LOGIN),
            ENABLE_ASSET_GENERATOR=_bool("ENABLE_ASSET_GENERATOR", cls.ENABLE_ASSET_GENERATOR),
            ENABLE_WATI_SEND=_bool("ENABLE_WATI_SEND", cls.ENABLE_WATI_SEND),
            ENABLE_ZOHO_WRITE=_bool("ENABLE_ZOHO_WRITE", cls.ENABLE_ZOHO_WRITE),
            ENABLE_ADMIN_DASHBOARD=_bool("ENABLE_ADMIN_DASHBOARD", cls.ENABLE_ADMIN_DASHBOARD),
            ENABLE_DEMO_MODE=_bool("ENABLE_DEMO_MODE", cls.ENABLE_DEMO_MODE),
            REFERRAL_INCENTIVE_CLAIM=_str("REFERRAL_INCENTIVE_CLAIM", cls.REFERRAL_INCENTIVE_CLAIM),
        )

    def as_dict(self) -> dict:
        return self.__dict__.copy()


# The single, process-wide flags snapshot. Import this, don't re-read os.environ.
flags = FeatureFlags.from_env()
