"""The link-preview card's baked-in legal text must match the canonical strings.

The card (`static/img/referral-preview-card.png`) is a raster: what it says cannot be
corrected by a config change, and it is the highest-volume surface the compliance strings
appear on — every referrer forwards it to every friend. The 2026-08-08 compliance review
caught a hand-made card that truncated `MARKET_RISK_WARNING` by 60 characters (dropping
the whole "read all the related documents" limb) and omitted the broker's SEBI
registration from the AP disclosure.

`scripts/make_preview_card.py` now renders the card FROM `settings`, writing every string
it drew to a sidecar `.txt`. These tests compare that sidecar against settings, so editing
a compliance constant without re-running the generator fails here instead of shipping a
stale statutory line to every prospect.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

CARD_PNG = Path(settings.BASE_DIR) / "static" / "img" / "referral-preview-card.png"
CARD_TXT = Path(settings.BASE_DIR) / "static" / "img" / "referral-preview-card.txt"


def _sidecar() -> str:
    if not CARD_TXT.exists():  # pragma: no cover - guarded by its own test below
        pytest.fail(
            "referral-preview-card.txt is missing — run `python scripts/make_preview_card.py`"
        )
    return CARD_TXT.read_text(encoding="utf-8")


def test_card_and_its_sidecar_are_committed():
    assert CARD_PNG.exists(), "the preview card PNG is missing from static/img/"
    assert CARD_TXT.exists(), "the card's text sidecar is missing — regenerate the card"


def test_card_carries_the_market_risk_warning_byte_exact():
    """Not 'contains a risk warning' — the canonical sentence, whole and unaltered."""
    assert settings.MARKET_RISK_WARNING in _sidecar(), (
        "the card's risk warning has drifted from settings.MARKET_RISK_WARNING — "
        "re-run scripts/make_preview_card.py after changing the constant"
    )


def test_card_carries_the_full_ap_disclosure_block():
    """Including the broker's name + SEBI registration: an AP must disclose its principal."""
    assert settings.AP_DISCLOSURE_BLOCK in _sidecar(), (
        "the card's AP disclosure has drifted from settings.AP_DISCLOSURE_BLOCK — "
        "re-run scripts/make_preview_card.py after changing the constant"
    )


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
