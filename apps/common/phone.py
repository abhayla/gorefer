"""The single canonical phone-normalization helper (implementation/10 §3).

ONE way, used everywhere (dedup, Zoho join, WATI send): strip spaces / + / () / -,
then ensure a leading `91` country prefix. Kept dependency-free and pure so every
call site normalizes identically.
"""
from __future__ import annotations

import re

_STRIP = re.compile(r"[\s+()\-]")


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
