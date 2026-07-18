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
        # SIMULATED terminal status from the log-only (demo) adapter — NO real send
        # happened. Excluded from real-delivery metrics (Fable5 M7).
        ("simulated_delivered", "simulated_delivered"),
    ]
    # Which adapter produced this row's terminal status, so a demo/log-only "delivery"
    # is always distinguishable from a real Wati delivery (Fable5 M7). 'live' = real
    # Wati API, 'log_only' = demo/no-network.
    ADAPTER_CHOICES = [("live", "live"), ("log_only", "log_only")]

    referral = models.ForeignKey(
        "referrals.Referral", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    recipient_role = models.CharField(max_length=16, choices=RECIPIENT_CHOICES)
    recipient_mobile = models.CharField(max_length=20, blank=True, default="")  # canonical 91-key
    template = models.CharField(max_length=100)
    category = models.CharField(max_length=16, default="UTILITY")  # UTILITY / MARKETING
    # Named template variables for this send, as an ordered [{"name","value"}] list —
    # a point-in-time snapshot resolved at create time (so a later customer-record edit
    # can't retro-change what was sent). Holds name/email like recipient_mobile does;
    # this is the erasable operational record, NOT the immutable event log (PII stays
    # out of Event by construction). Empty for variable-free templates.
    template_params = models.JSONField(default=list, blank=True)
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    # The adapter that handled the send (stamped at finalize). Blank until sent.
    adapter_kind = models.CharField(max_length=10, choices=ADAPTER_CHOICES, blank=True, default="")
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


class Conversion(TimestampedModel, TenantScopedModel):
    """Account-opening record mirrored from Zoho (05 §12.3). M6.

    The SOLE home of conversion truth. Written ONLY by the Zoho import path
    (guardrail #2) — never by an internal business write. Upsert key = the opener's
    Zerodha ACCOUNT ID (fallback zoho_lead_id, #11). Referrer credited by Zerodha
    CLIENT ID (#10) — NOT mobile. NO mobile stored. NO provisional/final — a
    conversion is whatever Zoho maps as-of-sync; a removal is a reversal/tombstone
    (is_reversed), never a silent delete (#6). `account_opened_at` is the TRUE Zoho
    open date (ADR-017), distinct from `synced_at` — analytics run off it.
    """

    program = models.ForeignKey(
        "referrals.ReferralProgram", on_delete=models.PROTECT, related_name="conversions"
    )
    opener_zerodha_account_id = models.CharField(max_length=64, blank=True, default="")
    zoho_lead_id = models.CharField(max_length=64, blank=True, default="")  # fallback key
    opener_name = models.CharField(max_length=120, blank=True, default="")
    referrer_client_id = models.CharField(max_length=64, blank=True, default="")  # credited referrer (Zoho)
    referral = models.ForeignKey(
        "referrals.Referral", on_delete=models.SET_NULL, null=True, blank=True, related_name="conversions"
    )
    account_opened_at = models.DateTimeField(null=True, blank=True)  # TRUE Zoho open date (ADR-017)
    status = models.CharField(max_length=40, default="account_opened")
    # reward_status: only if Zoho signals; never an amount (Zerodha Console only).
    reward_status = models.CharField(max_length=40, blank=True, default="")
    source_origin = models.CharField(max_length=20, default="zoho")  # where each status value came from
    status_changed_at = models.DateTimeField(null=True, blank=True)
    is_reversed = models.BooleanField(default=False)  # set by a reversal/tombstone only
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "conversions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "opener_zerodha_account_id"],
                condition=models.Q(opener_zerodha_account_id__gt=""),
                name="uq_conversion_opener_account",
            ),
            models.UniqueConstraint(
                fields=["tenant", "zoho_lead_id"],
                condition=models.Q(zoho_lead_id__gt=""),
                name="uq_conversion_zoho_lead",
            ),
        ]
        indexes = [
            models.Index(fields=["referrer_client_id"]),
            models.Index(fields=["account_opened_at"]),
            models.Index(fields=["is_reversed"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"conversion<{self.opener_zerodha_account_id or self.zoho_lead_id}:{self.status}>"


class ZohoSyncIdempotency(TimestampedModel, TenantScopedModel):
    """Exactly-once guard for Zoho updates (#8, 05 §12.3). A dedupe_key (Zoho
    event_id or composite account+referrer+date) is recorded before side-effects;
    a repeat delivery is a no-op."""

    dedupe_key = models.CharField(max_length=200, unique=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        db_table = "zoho_sync_idempotency"


class ZohoWebhookNonce(TimestampedModel):
    """DF-2 wax-seal: a burnt one-time nonce from a sealed Zoho webhook request.

    Deliberately NOT tenant-scoped and deliberately separate from
    `ZohoSyncIdempotency`. Those two distinctions are load-bearing:

    - **Not tenant-scoped:** the nonce is verified BEFORE the request is trusted, so
      the tenant it claims isn't yet authenticated. Scoping the uniqueness per tenant
      would let a replay succeed simply by claiming a different tenant.
    - **Not ZohoSyncIdempotency:** that is a BUSINESS dedupe on Zoho's `event_id` (the
      same real event delivered twice is a benign no-op). This is a SECURITY nonce —
      a byte-identical replay of a signed request. Sharing one table would let a
      legitimate business retry burn the security nonce, or vice versa.

    Rows are purged past the freshness window (`purge_expired_nonces`) — a nonce older
    than the window can't enable a replay, because the timestamp check rejects it first.
    """

    nonce = models.CharField(max_length=128, unique=True)

    class Meta:
        db_table = "zoho_webhook_nonce"
        indexes = [models.Index(fields=["created_at"])]  # the purge sweep's scan


class ZohoSyncWatermark(TenantScopedModel):
    """The sync worker's resume point (#7). Advances as records are processed so
    each run resumes where it left off."""

    last_event_id = models.CharField(max_length=120, blank=True, default="")
    last_processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "zoho_sync_watermark"


class ZohoDeadLetter(TimestampedModel, TenantScopedModel):
    """Dead-letter / problem-tray (#7): a record that repeatedly failed to process,
    retained for retry without loss (never silently dropped)."""

    dedupe_key = models.CharField(max_length=200, blank=True, default="")
    payload = models.JSONField(default=dict)  # raw inbound (may contain PII — erasable record)
    error = models.TextField(blank=True, default="")
    attempts = models.IntegerField(default=1)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "zoho_dead_letter"
