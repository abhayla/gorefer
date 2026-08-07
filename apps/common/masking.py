"""The ONE canonical PII-masking helper (same philosophy as `apps/common/phone.py`).

Exactly one implementation, imported everywhere a customer-facing surface must show
"enough to recognise, not enough to contact". Two rules only:

  - `mask_name`   -> first 2 characters + a FIXED run of bullets + the last character
                     ("Rahul" -> "Ra••••l"). The bullet run is fixed on purpose: a
                     length-proportional run would leak how long the name is, which
                     is exactly the kind of side-channel a masked view exists to close.
  - `mask_mobile` -> first 2 + bullets + last 2 of the NATIONAL number
                     ("919876543221" -> "98••••••21"). Here the run IS
                     length-proportional, because Indian national numbers are a fixed
                     10 digits — the length carries no information to leak.

Both take the raw stored value and return "" for empty/unusable input, so the caller
renders its own "not on file" copy rather than a row of meaningless bullets.
"""
from __future__ import annotations

from .phone import normalize_phone

BULLET = "•"

#: Fixed bullet run for names (see module docstring — deliberately not length-derived).
NAME_BULLETS = 4
#: Names this short cannot show 2 + 1 without showing everything.
NAME_SHORT_MAX = 3

#: Digits kept at each end of a mobile.
MOBILE_HEAD = 2
MOBILE_TAIL = 2
#: Indian national (subscriber) number length — the part we mask, country code dropped.
NATIONAL_DIGITS = 10


def mask_name(raw: str | None) -> str:
    """Mask a person's name for a customer-facing view. "" for empty input."""
    name = (raw or "").strip()
    if not name:
        return ""
    if len(name) <= NAME_SHORT_MAX:
        return name[0] + BULLET * 2
    return name[:2] + BULLET * NAME_BULLETS + name[-1]


def mask_mobile(raw: str | None) -> str:
    """Mask a mobile for a customer-facing view. "" for empty/unusable input.

    Normalizes through the ONE canonical phone helper first, so a number stored as
    `+91 98765 43221`, `9876543221` or `919876543221` all mask identically — a second
    normalizer here is exactly the drift `apps/common/phone.py` exists to prevent.
    """
    canonical = normalize_phone(raw)
    if not canonical:
        return ""
    national = canonical[-NATIONAL_DIGITS:] if len(canonical) > NATIONAL_DIGITS else canonical
    if len(national) <= MOBILE_HEAD + MOBILE_TAIL:
        return BULLET * len(national)
    middle = len(national) - MOBILE_HEAD - MOBILE_TAIL
    return national[:MOBILE_HEAD] + BULLET * middle + national[-MOBILE_TAIL:]
