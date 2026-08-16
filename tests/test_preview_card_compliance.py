"""The link-preview card's baked-in legal text must match the canonical strings.

The card (`static/img/referral-preview-card.png`) is a raster: what it says cannot be
corrected by a config change, and it is the highest-volume surface the compliance strings
appear on — every referrer forwards it to every friend. The 2026-08-08 compliance review
caught a hand-made card that truncated `MARKET_RISK_WARNING` by 60 characters (dropping
the whole "read all the related documents" limb) and omitted the broker's SEBI
registration from the AP disclosure.

`scripts/make_preview_card.py` now renders the card FROM `settings`, writing every string
it drew to a sidecar `.txt`. These tests compare that sidecar against
`apps.config.cascade.resolve()` for the compliance-locked `ap_disclosure_block` /
`market_risk_warning` keys — the SAME source every render path reads (context
processors, `disclosure_service`) — rather than the raw `settings.AP_DISCLOSURE_BLOCK`
/ `settings.MARKET_RISK_WARNING` constants. Comparing against the settings constants
directly missed drift at the central-config tier: if a `ConfigCentral` row overrides
one of these compliance-locked keys, every live page renders the overridden text while
this test kept comparing against the untouched settings constant and stayed green — a
false pass. Reading through the cascade means a central-tier edit that isn't reflected
on the (regenerated) card fails here, same as an edit to the settings constant always
did.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.config.cascade import resolve

CARD_PNG = Path(settings.BASE_DIR) / "static" / "img" / "referral-preview-card.png"
CARD_TXT = Path(settings.BASE_DIR) / "static" / "img" / "referral-preview-card.txt"


@pytest.fixture
def seeded(db):
    """Seed ConfigCentral (incl. the compliance-locked rows) the same way prod does."""
    call_command("seed_program")


def _cascade_value(key: str) -> str:
    """Resolve `key` the same way every render path does (context_processors,
    disclosure_service) — through `apps.config.cascade.resolve()`, not the raw
    settings constant. Falls back to the settings constant only when no central row
    exists yet (matches the render paths' own `default=` fallback)."""
    return resolve(key, default=getattr(settings, key.upper(), ""))


def _sidecar() -> str:
    if not CARD_TXT.exists():  # pragma: no cover - guarded by its own test below
        pytest.fail(
            "referral-preview-card.txt is missing — run `python scripts/make_preview_card.py`"
        )
    return CARD_TXT.read_text(encoding="utf-8")


def test_card_and_its_sidecar_are_committed():
    assert CARD_PNG.exists(), "the preview card PNG is missing from static/img/"
    assert CARD_TXT.exists(), "the card's text sidecar is missing — regenerate the card"


def test_card_carries_the_market_risk_warning_byte_exact(seeded):
    """Not 'contains a risk warning' — the canonical sentence, whole and unaltered."""
    assert _cascade_value("market_risk_warning") in _sidecar(), (
        "the card's risk warning has drifted from the resolved market_risk_warning — "
        "re-run scripts/make_preview_card.py after changing the constant"
    )


def test_card_carries_the_full_ap_disclosure_block(seeded):
    """Including the broker's name + SEBI registration: an AP must disclose its principal."""
    assert _cascade_value("ap_disclosure_block") in _sidecar(), (
        "the card's AP disclosure has drifted from the resolved ap_disclosure_block — "
        "re-run scripts/make_preview_card.py after changing the constant"
    )


def test_compliance_drift_at_the_central_tier_is_caught(seeded):
    """Proves the cascade-read actually fires on drift, not just on paper.

    A `ConfigCentral` row diverging from `settings.MARKET_RISK_WARNING` (and therefore
    from the committed card) is exactly the false-pass this test file used to be blind
    to: comparing against the raw settings constant stayed green even though every live
    page — which reads through `resolve()` — would render the drifted text. Reading via
    `_cascade_value()` must catch it.
    """
    from apps.config.models import ConfigCentral

    ConfigCentral.objects.filter(key="market_risk_warning").update(
        value="This is a deliberately drifted risk warning for the test."
    )
    assert _cascade_value("market_risk_warning") not in _sidecar()


def test_card_makes_no_free_account_claim():
    """'free demat account' is a claim about the BROKER's pricing that PIFS cannot make.

    PIFS may say it charges the customer nothing for its own help; it may not describe the
    account itself as free (AMC and brokerage are the broker's, and are not zero).
    """
    body = _sidecar().lower()
    assert "free demat" not in body and "free trading" not in body
    assert "open a free" not in body


def test_card_names_no_partner_trademark_beyond_the_required_disclosure():
    """ADR-014: the partner may be NAMED in the disclosure, never used as branding."""
    sidecar = _sidecar()
    headline_block = "\n".join(sidecar.splitlines()[:3])  # eyebrow, headline, subline
    assert "Zerodha" not in headline_block, (
        "the partner brand belongs only in the disclosure line, not in the card's headline"
    )
