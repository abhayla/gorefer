"""OTP code hashing (Q-M-OTP) — store a hash, never the plaintext code.

A 6-digit code is low-entropy, so the hash is peppered with a process secret
(settings.OTP_HASH_PEPPER) AND bound to the identity + a per-challenge salt, so a DB
leak alone cannot brute-force codes offline and a hash cannot be replayed across
identities. Verification is constant-time (`hmac.compare_digest`) to avoid timing
leaks. The code is generated from `secrets` (CSPRNG), never `random`.

The plaintext code lives only in memory long enough to hand to the delivery adapter;
it is never logged and never persisted.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from django.conf import settings


def generate_code(length: int) -> str:
    """A cryptographically-random numeric code of `length` digits (CSPRNG)."""
    length = max(4, min(int(length), 10))
    # Uniform over [0, 10**length) with leading zeros preserved.
    n = secrets.randbelow(10**length)
    return str(n).zfill(length)


def _pepper() -> str:
    return getattr(settings, "OTP_HASH_PEPPER", "") or settings.SECRET_KEY


def make_salt() -> str:
    return secrets.token_hex(16)


def hash_code(code: str, *, identity: str, salt: str) -> str:
    """Peppered, identity-bound, salted hash of a code. Never store the code itself."""
    msg = f"{salt}:{identity}:{code}".encode()
    return hashlib.sha256(msg + _pepper().encode()).hexdigest()


def verify_code(code: str, *, identity: str, salt: str, expected_hash: str) -> bool:
    """Constant-time check of a candidate code against a stored hash."""
    candidate = hash_code(code, identity=identity, salt=salt)
    return hmac.compare_digest(candidate, expected_hash)
