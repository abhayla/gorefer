"""client_id format validation (ADR-008 / Gap 3, spec 06-API §4.1).

Format-validate ONLY — reject empty / wrong-length / illegal chars. There is NO
ownership verification: no Zerodha API exists to check a client_id against, so a
well-formed id is accepted and the referrer is created lazily on first click.
Zerodha client ids are short alphanumerics (e.g. RJ4521, DA1707) — the spec bound
is 4–16 chars (06-API §4.1), which every real Zerodha client id observed to date
falls inside.
"""
from __future__ import annotations

import re

# Reconciled to the single spec bound (06-API §4.1): 4–16 alphanumeric chars.
MIN_CLIENT_ID_LEN = 4
MAX_CLIENT_ID_LEN = 16
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9]{4,16}$")


class InvalidClientId(ValueError):
    """Raised when a client_id fails format validation."""


def validate_client_id(raw: str | None) -> str:
    """Return the normalized client_id (uppercased) or raise InvalidClientId.

    Rules (06-API §4.1): 4–16 chars, alphanumeric only. Normalizes to uppercase so
    the identity key is case-stable (r/rj4521 and r/RJ4521 resolve to one referrer).
    """
    if raw is None:
        raise InvalidClientId("client_id is required")
    candidate = raw.strip()
    if not candidate:
        raise InvalidClientId("client_id is empty")
    if not (MIN_CLIENT_ID_LEN <= len(candidate) <= MAX_CLIENT_ID_LEN):
        raise InvalidClientId("client_id must be 4–16 characters")
    if not _CLIENT_ID_RE.match(candidate):
        raise InvalidClientId("client_id contains illegal characters")
    return candidate.upper()
