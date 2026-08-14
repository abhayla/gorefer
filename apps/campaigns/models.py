"""Messaging campaign configuration — T-124 (slice W1 of the configurable messaging
engine plan; owner design context: decisions 7/13/15 in
`~/.claude/plans/i-moved-you-to-silly-sonnet.md`).

`MessagingCampaign`/`MessagingCampaignStep` are CONFIGURATION — the shape of a
"campaign" (a single message stream, e.g. "referrer recurring nudge") with an on/off
switch, a step ladder, eligibility, per-recipient send budgets, send-days/hour, and
a per-language template map. `SyncedReferrer`/`ScheduledCampaignMessage` (T-125 W2)
are the engine's audience source and due-table that read these rows. Nothing in
THIS module imports `apps/integrations/**` — the send path lives in
`apps.campaigns.send` / `apps.campaigns.tasks`.

Mirrors `apps.followups.models` conventions: `TimestampedModel` + `TenantScopedModel`,
tenant-scoped uniqueness constraints, choices as class attributes, docstring style.

`send_days_mask` — a bitmask of the 7 ISO weekdays, bit 0 = Monday ... bit 6 = Sunday
(`1 << (isoweekday - 1)`), so a campaign can enable any combination of days (e.g.
Saturday-only, decision ④ in the owner design context) without a schema change. The
class constants `WEEKDAY_BITS` / `DEFAULT_SEND_DAYS_MASK` document the encoding.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import TenantScopedModel, TimestampedModel

# --- send_days_mask bit layout (Mon=bit0 ... Sun=bit6) --------------------------
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = (1 << i for i in range(7))
WEEKDAY_BITS = {
    1: MONDAY, 2: TUESDAY, 3: WEDNESDAY, 4: THURSDAY, 5: FRIDAY, 6: SATURDAY, 7: SUNDAY,
}
WEEKDAY_LABELS = [
    (MONDAY, "Mon"), (TUESDAY, "Tue"), (WEDNESDAY, "Wed"), (THURSDAY, "Thu"),
    (FRIDAY, "Fri"), (SATURDAY, "Sat"), (SUNDAY, "Sun"),
]
# Default: Monday-Friday (Saturday/Sunday off) — a sane default; any campaign may
# enable Saturday (or any other combination) per decision ④.
DEFAULT_SEND_DAYS_MASK = MONDAY | TUESDAY | WEDNESDAY | THURSDAY | FRIDAY


def days_mask_from_codes(codes) -> int:
    """Build a mask from an iterable of ISO weekday ints (1=Mon..7=Sun)."""
    mask = 0
    for code in codes:
        mask |= WEEKDAY_BITS.get(int(code), 0)
    return mask


def days_from_mask(mask: int) -> list[int]:
    """The ISO weekday ints (1=Mon..7=Sun) set in `mask`, in week order."""
    return [iso for iso, bit in WEEKDAY_BITS.items() if mask & bit]


class MessagingCampaign(TimestampedModel, TenantScopedModel):
    """One message stream's full configuration — decision ⑦ (one campaign per stream).

    Read by the T-125 messaging engine (`apps.campaigns.tasks.run_campaign_engine`).
    `enabled=False` is the safe default, so a freshly-seeded campaign never fires
    until an operator explicitly turns it on from /admin-panel/campaigns.
    """

    slug = models.SlugField(max_length=60)
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=False)

    # --- Eligibility -------------------------------------------------------------
    min_records = models.PositiveIntegerField(
        default=0, help_text="Minimum referral records the recipient must have."
    )
    activity_window_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Only consider activity within this many days (blank = no window limit).",
    )
    exclude_converted = models.BooleanField(default=True)
    manual_include_mobiles = models.JSONField(
        default=list, blank=True,
        help_text="Mobile numbers always included, bypassing eligibility (JSON list of strings).",
    )
    manual_exclude_mobiles = models.JSONField(
        default=list, blank=True,
        help_text="Mobile numbers always excluded, overriding eligibility (JSON list of strings).",
    )

    # --- Per-recipient send budgets (anti-spam) -----------------------------------
    max_msgs_per_24h = models.PositiveIntegerField(default=1)
    max_msgs_per_72h = models.PositiveIntegerField(default=1)
    max_msgs_per_7d = models.PositiveIntegerField(default=2)

    # --- Send window ---------------------------------------------------------------
    send_days_mask = models.PositiveSmallIntegerField(
        default=DEFAULT_SEND_DAYS_MASK,
        help_text="Bitmask of allowed send days, bit0=Mon..bit6=Sun (see WEEKDAY_BITS).",
    )
    send_hour_ist = models.PositiveSmallIntegerField(default=9)

    # --- Drip anchor + template map -------------------------------------------------
    anchor_event_key = models.CharField(
        max_length=60, blank=True, default="",
        help_text="Symbolic event key naming what anchors the drip (e.g. 'record_created'). "
        "Config only — no code here consumes it.",
    )
    language_template_map = models.JSONField(
        default=dict, blank=True,
        help_text='Language code -> Meta template name, e.g. {"en": "gr_platform_..."}. '
        "Blank/missing language falls back to English.",
    )

    class Meta:
        db_table = "messaging_campaigns"
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uq_messaging_campaign_tenant_slug"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"messaging_campaign<{self.slug}:{'on' if self.enabled else 'off'}>"

    def clean(self):
        super().clean()
        if self.send_hour_ist is not None and not (0 <= self.send_hour_ist <= 23):
            raise ValidationError({"send_hour_ist": "Must be between 0 and 23."})
        if self.send_days_mask is not None and not (0 <= self.send_days_mask <= 0b1111111):
            raise ValidationError({"send_days_mask": "Must be a 7-bit mask (0-127)."})

    def template_for(self, language: str) -> str:
        """The configured template name for `language`, falling back to English
        (decision ⑮) then to empty string when neither is set."""
        mapping = self.language_template_map or {}
        return mapping.get(language) or mapping.get("en") or ""

    def send_days(self) -> list[int]:
        return days_from_mask(self.send_days_mask)


class MessagingCampaignStep(TenantScopedModel, TimestampedModel):
    """One rung of a campaign's cadence ladder (order, gap, language, template).

    Tenant-scoped like its parent (repo convention — every table carries `tenant_id`,
    ADR-023), even though every practical query goes through `campaign`. Uniqueness is
    per (campaign, order) so a ladder can never have two steps claiming the same slot.
    """

    campaign = models.ForeignKey(MessagingCampaign, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField()
    gap_days_from_previous = models.PositiveIntegerField(
        default=0, help_text="Whole days after the previous step (or the anchor, for step 1)."
    )
    language = models.CharField(max_length=5, default="en")
    template_role = models.CharField(max_length=60, blank=True, default="")
    template_name = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Overrides the campaign's language_template_map for this step when set.",
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "messaging_campaign_steps"
        ordering = ["campaign_id", "order"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "order"], name="uq_campaign_step_order"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"messaging_campaign_step<{self.campaign_id}:#{self.order}:+{self.gap_days_from_previous}d>"

    def resolved_template_name(self) -> str:
        """This step's template: its own override, else the campaign's map for its language."""
        return self.template_name or self.campaign.template_for(self.language)


class SyncedReferrer(TimestampedModel, TenantScopedModel):
    """The engine's audience source (decision ⑫) — one row per referrer GoRefer knows
    how to message, tenant-scoped like every other table (ADR-023).

    W3 (a future slice) populates this from a READ-ONLY Zoho sync; nothing here
    writes back to Zoho or infers conversion state (CLAUDE.md §4 — Zoho stays the
    only source of account status). Until W3 lands, tests and any operator tooling
    fill it directly — the engine below never cares where a row came from, only
    that `active=True` and its fields are current as of `synced_at`.

    `record_created_at` is the drip anchor (decision ⑪ — an event-anchored ladder)
    AND the value a template's `{{record_date}}`-shaped copy describes, mirroring
    how `api.records_tokens._record_moment` treats a referral's creation instant.
    """

    client_id = models.CharField(max_length=64)
    mobile = models.CharField(max_length=20)
    name = models.CharField(max_length=120, blank=True, default="")
    language = models.CharField(max_length=5, default="en")
    record_created_at = models.DateTimeField(
        help_text="The referral record's creation instant — the drip's anchor event."
    )
    source = models.CharField(max_length=20, default="zoho")
    synced_at = models.DateTimeField(default=timezone.now)
    # False = the sync stopped seeing this referrer (or an operator disabled the row).
    # An enqueue never considers an inactive row eligible, regardless of other config.
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "synced_referrers"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_id"], name="uq_synced_referrer_tenant_client_id"
            ),
        ]
        indexes = [
            models.Index(fields=["active"]),
            models.Index(fields=["mobile"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"synced_referrer<{self.client_id}:{self.mobile}>"


class ScheduledCampaignMessage(TimestampedModel, TenantScopedModel):
    """One recipient's scheduled step for one campaign (the engine's due-table row).

    Mirrors `apps.followups.models.ScheduledFollowup` exactly — same due-table +
    sweep idiom (doc precedent this engine is built on): `dedupe_key` is unique per
    (tenant, campaign, mobile, step, anchor), so re-running enqueue for the SAME
    anchor creates nothing new. The sweep locks each row (select_for_update) before
    gating, so a concurrent CRUD edit can never race a send. Immutable once SENT.
    """

    STATUS_SCHEDULED = "scheduled"
    STATUS_SENT = "sent"
    STATUS_CANCELLED = "cancelled"
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "scheduled"),
        (STATUS_SENT, "sent"),
        (STATUS_CANCELLED, "cancelled"),  # gate cancelled it (opt-out / converted / on-reply / disabled)
        (STATUS_SKIPPED, "skipped"),      # nothing sendable (no template, unfillable token, no mobile)
        (STATUS_FAILED, "failed"),        # send attempted, not accepted
    ]

    campaign = models.ForeignKey(
        MessagingCampaign, on_delete=models.CASCADE, related_name="scheduled_messages"
    )
    step = models.ForeignKey(
        MessagingCampaignStep, on_delete=models.PROTECT, related_name="scheduled_messages"
    )
    referrer = models.ForeignKey(
        SyncedReferrer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="scheduled_messages",
    )
    client_id = models.CharField(max_length=64)
    mobile = models.CharField(max_length=20)
    language = models.CharField(max_length=5, default="en")
    # The referrer's `record_created_at` AT ENQUEUE TIME — the ladder's anchor.
    anchor_at = models.DateTimeField()
    fire_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    dedupe_key = models.CharField(max_length=220, unique=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        db_table = "scheduled_campaign_messages"
        indexes = [
            # The sweep scans (status, fire_at) due-first — keep it cheap at volume.
            models.Index(fields=["status", "fire_at"]),
            models.Index(fields=["mobile"]),
            models.Index(fields=["campaign", "mobile"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"scheduled_campaign_message<{self.mobile}:{self.campaign_id}:#{self.step_id}:{self.status}>"
