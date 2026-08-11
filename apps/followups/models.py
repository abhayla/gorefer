"""24h-window follow-up engine — data model (Phase 1, tenant-scoped).

Spec: docs/architecture/14-24h-Window-Followup-Engine.md. Constraint: doc-13 §5 —
Phase 1 is TENANT-SCOPED ONLY. There is NO PartnerGroup / 5-tier resolution here; a
`FollowupRule` is a real feature table at the EXISTING tenant tier, not the
speculative hierarchy §5 forbids. A future Phase 2 adds a nullable `scope` so
group/partner DEFAULT rules resolve above the AP rule with no rework.

Three tables, all mirroring existing idioms:
  - FollowupRule       — the AP's editable cadence step (per-AP config, one AP → many steps).
  - FollowupWindow     — the 24h window-state feed, keyed by (tenant, mobile). Stamped by
                         the Wati inbound webhook. Deliberately mobile-keyed (not a column on
                         Prospect): window state must exist for a contact who messages before
                         they are ever a lead, and it is a messaging fact, not prospect PII.
  - ScheduledFollowup  — the due-table (the schedule primitive AND the CRUD surface). Swept by
                         `followup_sweep`, exactly like `wati_reconcile_pending` sweeps
                         Notification rows stranded at ACCEPTED.

No PII beyond the recipient `mobile` (needed to send) lives here, and these are erasable
operational records — never the immutable event log.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import TenantScopedModel, TimestampedModel


class FollowupRule(TimestampedModel, TenantScopedModel):
    """One editable step in an AP's follow-up cadence (e.g. +15 min SESSION nudge).

    This IS the per-AP config (doc-13 §4: per-AP timings are tenant-tier config, no new
    machinery) — tenant-scoped, so it honours AP=tenant isolation (ADR-023/036). Simple
    on/off knobs (`followups_enabled`, default copy) stay as cascade keys; only the
    multi-step editable list needs its own table.
    """

    CHANNEL_SESSION = "session"
    CHANNEL_TEMPLATE = "template"
    CHANNEL_CHOICES = [
        (CHANNEL_SESSION, "session (free-form, in 24h window)"),
        (CHANNEL_TEMPLATE, "template (approved, works out of window)"),
    ]

    # A stable per-AP key for the step (e.g. "nudge_15m"), so an edit targets a step
    # without depending on row order. Unique per tenant.
    step_key = models.CharField(max_length=40)
    # Minutes after chat-open (the inbound that opened the 24h window) to fire this step.
    offset_minutes = models.PositiveIntegerField()
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default=CHANNEL_SESSION)
    # Approved template name — required only when this step can send out of window.
    template_name = models.CharField(max_length=100, blank=True, default="")
    # The message copy per language (session sends). Kept here (config), not hardcoded.
    body_en = models.TextField(blank=True, default="")
    body_hi = models.TextField(blank=True, default="")
    enabled = models.BooleanField(default=True)
    # Session channel only fires while the window is open; when closed it falls back to
    # a template if one is set, else skips — UNLESS only_if_window_open is True (then a
    # closed window means SKIP, never a template fallback).
    only_if_window_open = models.BooleanField(default=True)
    # Cancel pending steps once the contact replies / advances / converts (engaged-exit).
    stop_on_reply = models.BooleanField(default=True)
    order = models.IntegerField(default=100)

    class Meta:
        db_table = "followup_rules"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "step_key"], name="uq_followup_rule_tenant_step"
            ),
        ]
        indexes = [models.Index(fields=["enabled"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"followup_rule<{self.step_key}:+{self.offset_minutes}m:{self.channel}>"


class FollowupWindow(TimestampedModel, TenantScopedModel):
    """The 24h WhatsApp window-state feed for one contact, keyed by (tenant, mobile).

    `last_inbound_at` is stamped by the Wati inbound webhook on every inbound. The send
    gate reads it to decide window-open (session) vs window-closed (template/skip), and
    the enqueue path reads a fresh open (>24h since the prior inbound, or none) to know
    a new cadence should start.
    """

    mobile = models.CharField(max_length=20)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    # Per-AP (=tenant) per-contact opt-out (doc-13 G-4). Set from a "stop"/opt-out signal;
    # the enqueue and the send gate both refuse an opted-out contact. Scoped to this
    # tenant's number only — a platform-wide kill-switch is a Phase-2 concern (ADR-040).
    opted_out = models.BooleanField(default=False)

    class Meta:
        db_table = "followup_windows"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "mobile"], name="uq_followup_window_tenant_mobile"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"followup_window<{self.mobile}:{self.last_inbound_at}>"


class ScheduledFollowup(TimestampedModel, TenantScopedModel):
    """One contact's scheduled follow-up for one rule step (the due-table row).

    `dedupe_key` is unique per (contact, step, chat-open), so re-firing the enqueue for
    the SAME window open is idempotent. The sweep locks the row (select_for_update) before
    running the gate, so a CRUD edit can never race a send. Immutable once SENT.
    """

    STATUS_SCHEDULED = "scheduled"
    STATUS_SENT = "sent"
    STATUS_CANCELLED = "cancelled"
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "scheduled"),
        (STATUS_SENT, "sent"),
        (STATUS_CANCELLED, "cancelled"),   # gate cancelled it (opt-out / engaged / disabled)
        (STATUS_SKIPPED, "skipped"),       # nothing to send (window closed, no template)
        (STATUS_FAILED, "failed"),         # send attempted, not accepted
    ]

    rule = models.ForeignKey(FollowupRule, on_delete=models.PROTECT, related_name="scheduled")
    # The "contact" link — best-effort. May be null (a mobile can message before it is a
    # Prospect); `mobile` is the durable key the gate and send path use.
    prospect = models.ForeignKey(
        "referrals.Prospect", on_delete=models.SET_NULL, null=True, blank=True, related_name="followups"
    )
    mobile = models.CharField(max_length=20)
    pref_lang = models.CharField(max_length=5, default="en")
    fire_at = models.DateTimeField()
    # The inbound timestamp that opened this window — the engaged-exit baseline: a LATER
    # inbound (a reply) than this cancels pending steps.
    window_opened_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    dedupe_key = models.CharField(max_length=200, unique=True)
    source_event = models.CharField(max_length=40, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    # Why it was cancelled/skipped/failed — for the admin + audit. Never a send secret.
    reason = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        db_table = "scheduled_followups"
        indexes = [
            # The sweep scans (status, fire_at) due-first — keep it cheap at volume.
            models.Index(fields=["status", "fire_at"]),
            models.Index(fields=["mobile"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"scheduled_followup<{self.mobile}:{self.rule_id}:{self.status}>"


class AdvisorCallbackRequest(TimestampedModel, TenantScopedModel):
    """T-097 — a "talk to advisor" capture from a chatbot flow (partner-neutral).

    One row per (tenant, mobile, slot, request_date): the natural idempotency key for
    a customer re-tapping the same day. The immediate staff alert is sent synchronously
    at creation (see `apps.followups.advisor_callback`); the timed reminder rides the
    EXISTING `ScheduledFollowup` due-table/sweep via the `reminder` link below.
    `done` is the suppression signal — set it True before the reminder fires and the
    sweep cancels the pending row instead of sending, mirroring how
    `services.evaluate_gate` already cancels on `has_converted()`/opt-out: a lazy check
    at fire time against existing state, not a second scheduler.
    """

    SLOT_9_12 = "9-12"
    SLOT_12_3 = "12-3"
    SLOT_3_6 = "3-6"
    SLOT_CHOICES = [
        (SLOT_9_12, "9 AM - 12 PM"),
        (SLOT_12_3, "12 PM - 3 PM"),
        (SLOT_3_6, "3 PM - 6 PM"),
    ]
    SLOT_START_HOUR_IST = {SLOT_9_12: 9, SLOT_12_3: 12, SLOT_3_6: 15}
    SLOT_LABELS = dict(SLOT_CHOICES)

    mobile = models.CharField(max_length=20)
    name = models.CharField(max_length=80, blank=True, default="")
    slot = models.CharField(max_length=10, choices=SLOT_CHOICES)
    # The IST calendar date the request landed — the idempotency anchor, distinct from
    # the reminder's fire_at (which may roll to the next day if the slot already passed).
    request_date = models.DateField()
    done = models.BooleanField(default=False)
    alert_sent_at = models.DateTimeField(null=True, blank=True)
    reminder = models.OneToOneField(
        ScheduledFollowup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advisor_callback_request",
    )

    class Meta:
        db_table = "advisor_callback_requests"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "mobile", "slot", "request_date"],
                name="uq_advisor_callback_tenant_mobile_slot_date",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"advisor_callback_request<{self.mobile}:{self.slot}:{self.request_date}>"
