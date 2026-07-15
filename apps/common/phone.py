"""The single canonical phone-normalization helper (implementation/10 §3).

ONE way, used everywhere internally (dedup, WATI send): strip spaces / + / () / -,
then ensure a leading `91` country prefix. Kept dependency-free and pure so every
call site normalizes identically.

`to_zoho_mobile()` is a thin DERIVATION of that canonical form for the Zoho write
leg only — see its docstring. It is deliberately not a second normalizer: it takes
the canonical value as its input, so the two can never drift apart.
"""
from __future__ import annotations

import re

_STRIP = re.compile(r"[\s+()\-]")

# Indian subscriber numbers are 10 digits; Zoho `Leads.Mobile` stores them bare.
_ZOHO_MOBILE_DIGITS = 10


def normalize_phone(raw: str | None) -> str:
    """Return the canonical mobile key for `raw`.

    Rules: remove spaces / + / ( ) / -, keep digits; if the result does not already
    start with the 91 country code (and is a 10-digit Indian mobile), prefix `91`.
    An already-91-prefixed 12-digit number is returned unchanged. Empty/None -> "".
    """
    if not raw:
        return ""
    digits = _STRIP.sub("", raw)
    digits = re.sub(r"\D", "", digits)  # drop any stray non-digits
    if not digits:
        return ""
    if len(digits) == 10:
        return "91" + digits
    if digits.startswith("91") and len(digits) == 12:
        return digits
    # Leave other lengths as-is (validation is a separate concern); still de-punctuated.
    return digits


def to_zoho_mobile(raw: str | None) -> str:
    """Derive the BARE 10-digit form Zoho's `Leads.Mobile` actually stores.

    Zoho holds Indian mobiles WITHOUT a country code (DA correction 2026-07-15,
    MCP-verified against live Leads: all bare 10-digit, zero 91-prefixed). GoRefer
    normalizes internally to the 91-prefixed form. Writing the internal form to Zoho
    would make the upsert's `duplicate_check_fields=[Mobile]` search `919335179938`,
    MISS the stored `9335179938`, and silently create a parallel lead — Zoho's native
    uniqueness can't catch it because the two strings differ.

    So: take the canonical value and keep its LAST 10 digits (strips the `91` country
    code and any leading `0`). This is a DERIVATION of `normalize_phone`, not a fork —
    internal + WATI formats are unchanged; only the Zoho write leg reformats.

    Returns "" when fewer than 10 digits remain (malformed). NEVER pads — a padded
    number is a wrong number, and writing one to a CRM is worse than writing none.
    """
    canonical = normalize_phone(raw)
    if len(canonical) < _ZOHO_MOBILE_DIGITS:
        return ""
    return canonical[-_ZOHO_MOBILE_DIGITS:]
