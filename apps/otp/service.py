"""OtpService (Q-M-OTP) — issue + verify OTP codes over the pluggable channel port.

issue(identity):
  1. rate-limit (per identity/hour) + resend-cooldown guard,
  2. generate a CSPRNG code, store HASH + expiry ONLY (never plaintext, never logged),
  3. supersede any prior active code for the identity (single active code),
  4. send via the PRIMARY channel; on non-delivery, AUTO-CASCADE down the configured
     fallback list — all read from the ADR-022 config cascade (config-over-code:
     switching OTP_PRIMARY_CHANNEL takes effect with no code change).

verify(identity, code):
  check hash + expiry + attempts; single-use (a correct code consumes the challenge;
  a wrong code increments attempts and exhausts at the configured max).

All limits/lengths/TTL come from the per-tenant config (apps.config.preferences), so
an admin tunes them on the Preferences screen with no deploy. The service NEVER
fabricates a channel or logs the code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.config import preferences as prefkeys

from . import hashing
from .channels import resolve_channel
from .models import OtpChallenge
from .ports import (
    STATUS_DELIVERED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SUPPRESSED,
    DeliveryResult,
)

logger = logging.getLogger("gorefer.otp.service")


class OtpError(Exception):
    """Base for OTP issue/verify errors surfaced to the caller."""


class OtpRateLimited(OtpError):
    """Too many issues this hour, or the resend cooldown has not elapsed."""


@dataclass
class IssueResult:
    challenge_id: int
    channel: str          # the channel that produced the terminal outcome
    delivery_status: str  # delivered / queued / suppressed / failed(all-cascaded)
    delivered: bool


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""      # "" on success; else expired/used/no_code/wrong/exhausted


class OtpService:
    """Issue + verify OTP codes for a `(tenant, identity)` login subject."""

    def __init__(self, tenant, *, recipient_resolver=None):
        """`tenant` scopes every read/write. `recipient_resolver(identity) -> phone`
        supplies the ON-FILE channel (Zoho/Customer) — NEVER a user-typed number
        (S2-03 §15 Path A). Defaults to a resolver that fails closed (no channel)."""
        self.tenant = tenant
        self.tenant_id = getattr(tenant, "id", None)
        self._resolve_recipient = recipient_resolver or (lambda identity: "")
        self._cfg = prefkeys.get_preferences(self.tenant_id)

    # ------------------------------------------------------------------ issue

    def issue(self, identity: str, *, purpose: str = "login") -> IssueResult:
        identity = (identity or "").strip()
        if not identity:
            raise OtpError("identity required")

        self._enforce_rate_limit(identity)
        self._enforce_resend_cooldown(identity)

        length = self._cfg[prefkeys.OTP_CODE_LENGTH]
        ttl = self._cfg[prefkeys.OTP_CODE_TTL_SECONDS]
        code = hashing.generate_code(length)
        salt = hashing.make_salt()
        recipient = self._resolve_recipient(identity) or ""

        with transaction.atomic():
            # Single active code per identity: retire any prior active challenges.
            OtpChallenge.objects.filter(
                tenant=self.tenant, identity=identity, status=OtpChallenge.STATUS_ACTIVE
            ).update(status=OtpChallenge.STATUS_SUPERSEDED)

            challenge = OtpChallenge.objects.create(
                tenant=self.tenant,
                identity=identity,
                recipient=recipient,
                code_hash=hashing.hash_code(code, identity=identity, salt=salt),
                salt=salt,
                max_attempts=self._cfg[prefkeys.OTP_MAX_VERIFY_ATTEMPTS],
                expires_at=timezone.now() + timedelta(seconds=ttl),
            )

        # Deliver: primary then configured fallbacks, in order (config-over-code).
        result = self._deliver(recipient=recipient, code=code, ttl=ttl, purpose=purpose)
        # NB: `code` goes out of scope here — never persisted, never logged.

        challenge.channel = result.channel or ""
        challenge.provider_ref = result.provider_ref or ""
        challenge.delivery_status = result.status
        challenge.save(update_fields=["channel", "provider_ref", "delivery_status", "updated_at"])

        return IssueResult(
            challenge_id=challenge.id,
            channel=result.channel or "",
            delivery_status=result.status,
            delivered=result.status in {STATUS_DELIVERED, STATUS_QUEUED, STATUS_SUPPRESSED},
        )

    def _deliver(self, *, recipient: str, code: str, ttl: int, purpose: str):
        """Try primary, then each fallback, until one is delivered/queued/suppressed.

        A channel that returns STATUS_FAILED cascades to the next. STATUS_SUPPRESSED
        (demo) and STATUS_QUEUED (manual handoff) are terminal successes for the
        cascade — they mean the intended send happened (or was intentionally not sent
        in demo). Returns the LAST result with its `channel` stamped.
        """
        order = [self._cfg[prefkeys.OTP_PRIMARY_CHANNEL], *self._cfg[prefkeys.OTP_FALLBACK_CHANNELS]]
        template = self._cfg[prefkeys.OTP_WHATSAPP_TEMPLATE]
        last = None
        for code_name in order:
            adapter = resolve_channel(code_name)
            context = {
                "tenant_id": self.tenant_id,
                "template": template,
                "purpose": purpose,
                "intended_channel": code_name,
            }
            try:
                result = adapter.send(recipient=recipient, code=code, ttl_seconds=ttl, context=context)
            except Exception as exc:  # noqa: BLE001 — a raising channel must cascade, never crash login
                # NB: `exc` may carry the recipient but NEVER the code (adapters don't
                # put the code in exceptions). Log the type only, not the message body.
                logger.warning("OTP channel %s raised %s — cascading", code_name, type(exc).__name__)
                result = DeliveryResult(status=STATUS_FAILED, error=f"{type(exc).__name__}")
            result.channel = code_name
            last = result
            if result.status in {STATUS_DELIVERED, STATUS_QUEUED, STATUS_SUPPRESSED}:
                return result
            logger.info("OTP channel %s did not deliver (%s) — cascading", code_name, result.error)
        return last

    # ----------------------------------------------------------------- verify

    def verify(self, identity: str, code: str) -> VerifyResult:
        identity = (identity or "").strip()
        code = (code or "").strip()
        with transaction.atomic():
            challenge = (
                OtpChallenge.objects.select_for_update()
                .filter(tenant=self.tenant, identity=identity, status=OtpChallenge.STATUS_ACTIVE)
                .order_by("-created_at")
                .first()
            )
            if challenge is None:
                return VerifyResult(ok=False, reason="no_code")

            if challenge.is_expired:
                challenge.status = OtpChallenge.STATUS_EXPIRED
                challenge.save(update_fields=["status", "updated_at"])
                return VerifyResult(ok=False, reason="expired")

            if challenge.attempts >= challenge.max_attempts:
                challenge.status = OtpChallenge.STATUS_EXHAUSTED
                challenge.save(update_fields=["status", "updated_at"])
                return VerifyResult(ok=False, reason="exhausted")

            good = code and hashing.verify_code(
                code, identity=identity, salt=challenge.salt, expected_hash=challenge.code_hash
            )
            if not good:
                challenge.attempts += 1
                if challenge.attempts >= challenge.max_attempts:
                    challenge.status = OtpChallenge.STATUS_EXHAUSTED
                challenge.save(update_fields=["attempts", "status", "updated_at"])
                reason = "exhausted" if challenge.status == OtpChallenge.STATUS_EXHAUSTED else "wrong"
                return VerifyResult(ok=False, reason=reason)

            # Correct — single-use: consume the challenge.
            challenge.status = OtpChallenge.STATUS_VERIFIED
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["status", "consumed_at", "updated_at"])
            return VerifyResult(ok=True)

    # ------------------------------------------------------------- rate limits

    def _enforce_rate_limit(self, identity: str) -> None:
        limit = self._cfg[prefkeys.OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR]
        since = timezone.now() - timedelta(hours=1)
        issued = OtpChallenge.objects.filter(
            tenant=self.tenant, identity=identity, created_at__gte=since
        ).count()
        if issued >= limit:
            raise OtpRateLimited(
                f"OTP rate limit reached ({limit}/hour) — try again later."
            )

    def _enforce_resend_cooldown(self, identity: str) -> None:
        cooldown = self._cfg[prefkeys.OTP_RESEND_COOLDOWN_SECONDS]
        if cooldown <= 0:
            return
        window = timezone.now() - timedelta(seconds=cooldown)
        recent = (
            OtpChallenge.objects.filter(tenant=self.tenant, identity=identity, created_at__gte=window)
            .order_by("-created_at")
            .first()
        )
        if recent is not None:
            raise OtpRateLimited(
                f"Please wait {cooldown}s before requesting another code."
            )
