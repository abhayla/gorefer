"""Notification records (M5) — WATI transactional sends + terminal delivery status.

Each row is one intended message to one recipient for one journey. The
`idempotency_key` (recipient + template + journey) makes sends deduped — a repeat
trigger finds the existing row and does not re-send. Terminal delivery status +
Meta error classification are recorded here (doc-08 A3 / Gap 12), so the funnel can
start at "delivered" and the ~33% WATI leak is visible, not hidden.

No PII beyond the recipient mobile (needed to send) lives here — and this is an
erasable operational record, not the immutable event log.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import TenantScopedModel, TimestampedModel


class Notification(TimestampedModel, TenantScopedModel):
    """One WATI transactional message + its terminal delivery status."""

    RECIPIENT_CHOICES = [
        ("office", "office"),      # Ashok / office alert
        ("prospect", "prospect"),  # the new person / friend
        ("referrer", "referrer"),  # the referrer (only if phone known)
    ]
    STATUS_CHOICES = [
        ("queued", "queued"),
        ("accepted", "accepted"),    # WATI HTTP 200 — NOT delivery
        ("delivered", "delivered"),
        ("read", "read"),
        ("failed", "failed"),
        ("skipped", "skipped"),      # e.g. referrer phone unknown / opted out
    ]

    referral = models.ForeignKey(
        "referrals.Referral", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    recipient_role = models.CharField(max_length=16, choices=RECIPIENT_CHOICES)
    recipient_mobile = models.CharField(max_length=20, blank=True, default="")  # canonical 91-key
    template = models.CharField(max_length=100)
    category = models.CharField(max_length=16, default="UTILITY")  # UTILITY / MARKETING
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued")
    provider_message_id = models.CharField(max_length=120, blank=True, default="")
    meta_error_code = models.IntegerField(null=True, blank=True)
    failure_classification = models.CharField(max_length=120, blank=True, default="")
    skip_reason = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["recipient_role"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"notification<{self.recipient_role}:{self.template}:{self.status}>"
