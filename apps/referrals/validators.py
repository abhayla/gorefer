"""client_id format validation (ADR-008 / Gap 3).

Format-validate ONLY — reject empty / oversized / illegal chars. There is NO
ownership verification: no Zerodha API exists to check a client_id against, so a
well-formed id is accepted and the referrer is created lazily on first click.
Zerodha client ids are short alphanumerics (e.g. RJ4521, DA1707).
"""
from __future__ import annotations

import re

MAX_CLIENT_ID_LEN = 20
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9]{1,20}$")


class InvalidClientId(ValueError):
    """Raised when a client_id fails format validation."""


def validate_client_id(raw: str | None) -> str:
    """Return the normalized client_id (uppercased) or raise InvalidClientId.

    Rules: non-empty, <= 20 chars, alphanumeric only. Normalizes to uppercase so
    the identity key is case-stable (r/rj4521 and r/RJ4521 resolve to one referrer).
    """
    if raw is None:
        raise InvalidClientId("client_id is required")
    candidate = raw.strip()
    if not candidate:
        raise InvalidClientId("client_id is empty")
    if len(candidate) > MAX_CLIENT_ID_LEN:
        raise InvalidClientId("client_id too long")
    if not _CLIENT_ID_RE.match(candidate):
        raise InvalidClientId("client_id contains illegal characters")
    return candidate.upper()
