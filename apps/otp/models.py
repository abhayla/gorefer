"""OTP challenge records (Q-M-OTP).

`OtpChallenge` is one issued code's lifecycle: HASH + expiry + attempt count only —
NEVER the plaintext code (stored hashed, salted+peppered; the code exists only in
memory long enough to send it). Single-use: a successful verify (or exhausting the
attempts, or expiry) consumes the challenge. Per-tenant + keyed by `identity` (the
`(tenant_id, client_id)` login subject, ADR-023) so rate-limiting and resend-cooldown
scope per identity on the public-Client-ID surface.

This is an erasable operational record (PII = the recipient mobile, needed to send),
NOT the immutable event log — no OTP data goes into `events`.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.common.models import TenantScopedModel, TimestampedModel


class OtpChallenge(TimestampedModel, TenantScopedModel):
    """One issued OTP code (hashed) for one identity + its verify lifecycle."""

    STATUS_ACTIVE = "active"        # issued, not yet verified/expired/exhausted
    STATUS_VERIFIED = "verified"    # consumed by a correct code (single-use)
    STATUS_EXPIRED = "expired"      # TTL passed without a correct code
    STATUS_EXHAUSTED = "exhausted"  # too many wrong attempts
    STATUS_SUPERSEDED = "superseded"  # a newer code was issued for the identity
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "active"),
        (STATUS_VERIFIED, "verified"),
        (STATUS_EXPIRED, "expired"),
        (STATUS_EXHAUSTED, "exhausted"),
        (STATUS_SUPERSEDED, "superseded"),
    ]

    # The login subject — the referrer's Zerodha client_id within the tenant
    # (ADR-023 (tenant_id, client_id) boundary). Rate-limit + resend scope per this.
    identity = models.CharField(max_length=64)
    # Canonical recipient (91-prefixed) the code was sent to (on-file channel only).
    recipient = models.CharField(max_length=32, blank=True, default="")
    # HASH ONLY — never the plaintext code. `salt` is per-challenge; the pepper is a
    # process secret (settings.OTP_HASH_PEPPER), so it is NOT stored here.
    code_hash = models.CharField(max_length=128)
    salt = models.CharField(max_length=64)
    channel = models.CharField(max_length=20, blank=True, default="")   # channel actually used
    provider_ref = models.CharField(max_length=120, blank=True, default="")
    delivery_status = models.CharField(max_length=20, blank=True, default="")

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    attempts = models.IntegerField(default=0)      # wrong-code attempts used
    max_attempts = models.IntegerField(default=5)  # snapshot of the config at issue time
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "otp_challenges"
        indexes = [
            models.Index(fields=["tenant", "identity", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"otp<{self.identity}:{self.status}>"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumable(self) -> bool:
        """A code can still be verified only while active, unexpired, and under-limit."""
        return (
            self.status == self.STATUS_ACTIVE
            and not self.is_expired
            and self.attempts < self.max_attempts
        )
