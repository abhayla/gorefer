"""Referrer self-service identity (M13 / ADR-027 + ADR-035).

`ReferrerAccount` binds a Django auth user to the `(tenant_id, client_id)` login
subject (ADR-023/ADR-035). A login only UNLOCKS the retroactive view of what is
already keyed to the client_id — there is no link-claiming step. One account per
client_id per tenant (the shape ADR-041's one-client_id-one-tenant-per-partner
rule later depends on).

`VerificationRequest` is the pending-verification queue (ADR-027 mismatch route +
ADR-035 Path B evidence route). The evidence screenshot is PII held ERASABLY in
the DB (never in the immutable event log, never publicly served) and is PURGED the
moment the request is decided (DPDP / ADR-020) — approval and rejection both purge.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TenantScopedModel, TimestampedModel


class ReferrerAccount(TimestampedModel, TenantScopedModel):
    """One referrer's login identity, bound to `(tenant, client_id)`."""

    BOUND_VIA_OTP = "otp"                      # Path A: OTP to the on-file channel
    BOUND_VIA_OAUTH_AUTO = "oauth_auto"        # ADR-027 auto-bind (email/mobile matched)
    BOUND_VIA_ADMIN = "admin_approval"         # verification queue approval
    BOUND_VIA_CHOICES = [
        (BOUND_VIA_OTP, "otp"),
        (BOUND_VIA_OAUTH_AUTO, "oauth_auto"),
        (BOUND_VIA_ADMIN, "admin_approval"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_DISABLED = "disabled"
    STATUS_CHOICES = [(STATUS_ACTIVE, "active"), (STATUS_DISABLED, "disabled")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrer_account"
    )
    client_id = models.CharField(max_length=64)
    # The verified Google identity, when bound via OAuth (blank for OTP-only logins).
    google_email = models.EmailField(blank=True, default="")
    # Canonical on-file mobile AT BIND TIME (erasable PII; display/audit only — the
    # OTP recipient is always re-resolved from the on-file sources, never from here).
    mobile = models.CharField(max_length=20, blank=True, default="")
    bound_via = models.CharField(max_length=20, choices=BOUND_VIA_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = "referrer_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_id"], name="uq_referrer_account_tenant_client"
            ),
        ]
        indexes = [models.Index(fields=["google_email"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"referrer-account<{self.client_id}:{self.status}>"


class VerificationRequest(TimestampedModel, TenantScopedModel):
    """A pending ownership-verification (ADR-027 mismatch / ADR-035 Path B)."""

    KIND_OAUTH_MISMATCH = "oauth_mismatch"  # ADR-027: neither email nor mobile matched
    KIND_EVIDENCE = "evidence"              # ADR-035 Path B: console-screenshot evidence
    KIND_CHOICES = [(KIND_OAUTH_MISMATCH, "oauth_mismatch"), (KIND_EVIDENCE, "evidence")]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_APPROVED, "approved"),
        (STATUS_REJECTED, "rejected"),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    client_id = models.CharField(max_length=64)
    # What the requester supplied (their CLAIM — verified by a human, never trusted):
    registered_name = models.CharField(max_length=160, blank=True, default="")
    mobile_entered = models.CharField(max_length=20, blank=True, default="")
    google_email = models.EmailField(blank=True, default="")
    # Path-B evidence: the Zerodha-console screenshot, held erasably; purged on decision.
    evidence = models.BinaryField(null=True, blank=True, editable=False)
    evidence_content_type = models.CharField(max_length=60, blank=True, default="")
    evidence_size = models.IntegerField(default=0)
    evidence_purged_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    decided_by = models.BigIntegerField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "referrer_verification_requests"
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["client_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"verification<{self.kind}:{self.client_id}:{self.status}>"

    def purge_evidence(self) -> None:
        """Drop the screenshot bytes (DPDP) — called on approve AND reject."""
        if self.evidence is not None or self.evidence_purged_at is None:
            self.evidence = None
            self.evidence_purged_at = timezone.now()
