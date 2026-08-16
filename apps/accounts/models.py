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


class RecordsLinkState(TimestampedModel, TenantScopedModel):
    """Revocation state for the tokened "Referral Records" magic link (T-051).

    The link token itself is STATELESS (a `django.core.signing` payload), so the only
    thing that has to live in the database is the counter that makes revocation
    possible: a token carries the epoch it was minted under, and verification refuses
    any token whose epoch is not the current one. Bumping `epoch` therefore kills
    every link ever sent to THAT referrer, and only that referrer.

    Bound to `referrals.ReferralIdentity` — the lazily-created referrer entity keyed by
    client_id — NOT to `ReferrerAccount`. The recipients of these links are referrers
    we message on WhatsApp; the overwhelming majority have never logged in and so have
    no ReferrerAccount row to hang state off.
    """

    identity = models.OneToOneField(
        "referrals.ReferralIdentity",
        on_delete=models.CASCADE,
        related_name="records_link_state",
    )
    #: Monotonic revocation counter. Tokens embed the epoch current at mint time.
    epoch = models.PositiveIntegerField(default=1)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "records_link_state"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "identity"], name="uq_records_link_state_tenant_identity"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"records-link-state<{self.identity_id}:e{self.epoch}>"


class ReferrerShareOpener(TimestampedModel, TenantScopedModel):
    """One referrer's PERSONAL opening line for the message they forward (T-064).

    Bound to `referrals.ReferralIdentity` for the same reason `RecordsLinkState` is:
    the people editing this arrive from a WhatsApp tap on `/hub/{token}` and mostly
    have no `ReferrerAccount` row to hang state off.

    This table holds ONLY the opener. It is deliberately NOT the whole message: the
    credit link and the compliance disclosure line are appended server-side, after
    this text, every time a message is composed
    (`apps.referrals.share_intent_service.kit_message`). So the worst a referrer can
    do by editing here is write a bad sentence — they cannot delete the link they get
    paid for, and they cannot delete the disclosure.

    Empty `text` means "use the tenant's official message", which is also what a
    missing row means. The two are equivalent on purpose: clearing the box and never
    having opened it must produce byte-identical output.
    """

    identity = models.OneToOneField(
        "referrals.ReferralIdentity",
        on_delete=models.CASCADE,
        related_name="share_opener",
    )
    #: The referrer's own words. Length is capped at WRITE time against the
    #: `referrer_share_opener_max_chars` cascade key, not by a column limit — the cap
    #: is owner-tunable config (rail E-6) and a migration must not be needed to change it.
    text = models.TextField(blank=True, default="")

    class Meta:
        db_table = "referrer_share_opener"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "identity"], name="uq_referrer_share_opener_tenant_identity"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"share-opener<{self.identity_id}:{len(self.text)}c>"


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

    # Admin-queue badge (T-158 pt 29): whether the client_id was ALREADY on file
    # (Customer/Zoho) at submission time — distinguishes "we know this person and
    # their submitted details didn't match" from "we've never heard of this
    # client_id at all". Computed once at submission (onfile.resolve_onfile), not
    # re-resolved at render time, so the admin queue never triggers a live Zoho call.
    ONFILE_UNKNOWN = "unknown"    # client_id not found in Customer/Zoho at all
    ONFILE_MISMATCH = "mismatch"  # client_id found, but submitted details didn't match
    ONFILE_STATUS_CHOICES = [
        (ONFILE_UNKNOWN, "unknown to the system"),
        (ONFILE_MISMATCH, "found, details mismatched"),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    client_id = models.CharField(max_length=64)
    # What the requester supplied (their CLAIM — verified by a human, never trusted):
    registered_name = models.CharField(max_length=160, blank=True, default="")
    mobile_entered = models.CharField(max_length=20, blank=True, default="")
    google_email = models.EmailField(blank=True, default="")
    onfile_status = models.CharField(max_length=20, blank=True, default="")
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
