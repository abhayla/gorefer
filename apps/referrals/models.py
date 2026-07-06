"""Referral Programs + Partners (05-Database-Design Contexts 2 & 3).

PROVIDER-AGNOSTIC by construction (implementation/10 §3): the models are named
Partner / ReferralProgram / ProgramRedirectRule — never Zerodha*. Zerodha is
seeded as row #1 of `programs` with partner code ZMPHZC; a future partner (Groww,
insurance, MF...) is another row, never a code change.

M1 scope: enough of Contexts 2 & 3 to seed the single program and hold its
server-side destination-URL template + swappable reward copy. The referral
identity / journey / event tables are M2+ and are NOT created here.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import AuditedModel, SoftDeleteModel, TenantScopedModel


class Partner(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """The external org whose referral journeys GoRefer manages (Sprint 1: PIFS).

    `code` is the partner code (e.g. ZMPHZC) injected server-side into redirects —
    it is config data here, never a client-facing value. `credentials` holds the
    Partner Credentials abstraction (client_id/agent_id/advisor_code/nse_ap_no);
    real secrets are referenced from env/vault, not stored raw.
    """

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    credentials = models.JSONField(default=dict, blank=True)
    website = models.URLField(blank=True, default="")
    status = models.CharField(max_length=20, default="active")

    class Meta:
        db_table = "partners"
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.code})"


class ReferralProgram(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """A company/product whose referrals GoRefer manages. Zerodha = row #1.

    `reward_description` is the single swappable incentive copy for this program
    (mirrors flags.REFERRAL_INCENTIVE_CLAIM for the seeded program). No
    Zerodha-specific columns exist.
    """

    STATUS_CHOICES = [("active", "active"), ("inactive", "inactive")]

    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="programs")
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    logo_url = models.URLField(blank=True, default="")
    brand_color = models.CharField(max_length=20, blank=True, default="")
    reward_description = models.TextField(blank=True, default="")
    terms_url = models.URLField(blank=True, default="")

    class Meta:
        db_table = "programs"
        constraints = [
            # Program name unique per partner per tenant (05 §6 + ADR-023 §2).
            models.UniqueConstraint(
                fields=["tenant", "partner", "name"], name="uq_program_tenant_partner_name"
            ),
        ]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class ProgramRedirectRule(AuditedModel, TenantScopedModel):
    """Drives the server-side destination build for a program (05 §6).

    `destination_url_template` is filled server-side at redirect time (M2) with the
    partner code and referrer client_id, e.g.
    `https://signup.zerodha.com/api/lead/?c={partner_code}&r={client_id}`.
    The template and partner code are NEVER exposed to the client.
    """

    program = models.ForeignKey(ReferralProgram, on_delete=models.CASCADE, related_name="redirect_rules")
    match_condition = models.JSONField(default=dict, blank=True)
    destination_url_template = models.TextField()
    priority = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "program_redirect_rules"
        indexes = [models.Index(fields=["program", "priority"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"redirect_rule<{self.program_id}:{self.priority}>"
