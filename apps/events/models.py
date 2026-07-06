"""Analytics / event context (05-Database-Design Context 12) — M2 subset.

M2 introduces:
  - `Event`: the immutable, append-only event log. NO PII ever (name/phone/email/
    raw IP/city) in a row or its `metadata` — CI-enforced (see tests). The Click
    event lives here (event_type="ReferralLinkOpened").
  - `VisitorPII`: the SEPARATE erasable record that holds the raw IP (PII, #16/#17)
    linked to a visitor/journey. Kept OUT of the immutable log so it can be purged/
    erased on request. (Before a prospect/lead exists at M2, this is the journey/
    visitor-level erasable PII home the DA specified.)

Full analytics (sessions/devices/rollups, the JS human-confirmation beacon
counting, unique-visitor aggregation) is M4.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import TenantScopedModel

# The canonical set of PII field names that must NEVER appear in Event.metadata.
# The guardrail test asserts against this list.
PII_KEYS = frozenset({"name", "mobile", "phone", "email", "ip", "raw_ip", "city", "address"})


class Event(TenantScopedModel):
    """Immutable, append-only event (05 §12.1). No updated_at, no soft-delete."""

    event_type = models.CharField(max_length=64)
    # Source/origin tag (#18): which system/event produced this row. The audit
    # backbone for never-fabricate — every event is traceable to an origin.
    source = models.CharField(max_length=32, default="system")
    referral = models.ForeignKey(
        "referrals.Referral", on_delete=models.PROTECT, null=True, blank=True, related_name="events"
    )
    user_type = models.CharField(max_length=16, default="anonymous")
    visitor_id = models.CharField(max_length=64, null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    is_bot = models.BooleanField(default=False)
    is_confirmed_human = models.BooleanField(default=False)
    country = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=64, blank=True, default="")
    # person_ref_id points at the erasable PII record BY ID only (no PII inline).
    person_ref_id = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "events"
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["referral"]),
            models.Index(fields=["visitor_id"]),
            models.Index(fields=["is_bot"]),
            models.Index(fields=["is_confirmed_human"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"event<{self.event_type}:{self.pk}>"


class VisitorPII(TenantScopedModel):
    """The SEPARATE erasable PII record (raw IP + derived city), linked by visitor_id.

    Raw IP is stored UNHASHED (Round-2 #17: not hashed, not dropped), retention-
    limited and erasable on request. Deliberately NOT part of the immutable event
    log — `Event.person_ref_id` references this row by id only.
    """

    visitor_id = models.CharField(max_length=64, db_index=True)
    raw_ip = models.GenericIPAddressField(null=True, blank=True)
    city = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    erased_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "visitor_pii"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"visitor_pii<{self.visitor_id}>"


class ClickNonce(TenantScopedModel):
    """One-time nonce gating the human-confirmation beacon + name reveal (ADR-021).

    Minted server-side when a click is logged (M3), handed to the page JS. The
    beacon (POST /api/click/confirm) verifies it, marks the click confirmed-human,
    and CONSUMES it; the name-reveal endpoint requires the SAME fresh nonce. This
    closes the id->name enumeration hole: without a valid, unused, unexpired nonce
    the referrer's name is never returned. Single-use + short TTL + rate-limited.
    """

    nonce = models.CharField(max_length=64, unique=True, db_index=True)
    visitor_id = models.CharField(max_length=64, db_index=True)
    referral = models.ForeignKey(
        "referrals.Referral", on_delete=models.CASCADE, null=True, blank=True, related_name="nonces"
    )
    client_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "click_nonces"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"nonce<{self.nonce[:8]}…>"


class DailyMetric(TenantScopedModel):
    """Pre-aggregated daily rollup (05 §12.2). Rebuildable from events; dashboards
    read these cheap rows, not the raw firehose. Recomputed via the dirty-days set."""

    metric_date = models.DateField()
    program = models.ForeignKey("referrals.ReferralProgram", on_delete=models.CASCADE, related_name="+")
    links_created = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    landing_views = models.IntegerField(default=0)
    redirects = models.IntegerField(default=0)
    leads = models.IntegerField(default=0)
    accounts_opened = models.IntegerField(default=0)  # source-only (Zoho, M6); 0 until then
    recomputed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_metrics"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "metric_date", "program"], name="uq_daily_metric"
            ),
        ]


class MonthlyMetric(TenantScopedModel):
    """Pre-aggregated monthly rollup (mirrors DailyMetric at month grain)."""

    year = models.IntegerField()
    month = models.IntegerField()  # 1-12
    program = models.ForeignKey("referrals.ReferralProgram", on_delete=models.CASCADE, related_name="+")
    links_created = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    landing_views = models.IntegerField(default=0)
    redirects = models.IntegerField(default=0)
    leads = models.IntegerField(default=0)
    accounts_opened = models.IntegerField(default=0)
    recomputed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "monthly_metrics"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year", "month", "program"], name="uq_monthly_metric"
            ),
        ]


class DirtyPeriod(TenantScopedModel):
    """The dirty-days set (#6/#34). Any add/fix/removal records the affected day (and
    its month) here; a worker recomputes exactly those periods — no full rebuild.
    Consistent after out-of-order / backdated data (e.g. a Zoho conversion landing in
    its true prior period)."""

    program = models.ForeignKey("referrals.ReferralProgram", on_delete=models.CASCADE, related_name="+")
    period_date = models.DateField()  # the day marked dirty (its month is derived)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dirty_periods"
        indexes = [models.Index(fields=["processed_at"])]


class SyncHealth(TenantScopedModel):
    """Sync-freshness scaffold (#19). Populated by M5/M6; in demo shows 'no sync yet'.
    Guards against 'looks-current-but-isn't' data (fabrication-by-omission)."""

    STATE_CHOICES = [
        ("healthy", "healthy"), ("degraded", "degraded"),
        ("stalled", "stalled"), ("no_sync", "no_sync"),
    ]

    last_successful_zoho_sync_at = models.DateTimeField(null=True, blank=True)
    zoho_state = models.CharField(max_length=16, choices=STATE_CHOICES, default="no_sync")
    last_successful_wati_at = models.DateTimeField(null=True, blank=True)
    wati_state = models.CharField(max_length=16, choices=STATE_CHOICES, default="no_sync")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_health"
