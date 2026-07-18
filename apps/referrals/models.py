"""Referral Programs + Partners (05-Database-Design Contexts 2 & 3).

PROVIDER-AGNOSTIC by construction (implementation/10 §3): the models are named
Partner / ReferralProgram / ProgramRedirectRule — never Zerodha*. Zerodha is
seeded as row #1 of `programs` with partner code ZMPHZC; a future partner (Groww,
insurance, MF...) is another row, never a code change.

M1 seeded Contexts 2 & 3 (partner, program, redirect template). M2 adds the
lazily-created referral identity + referral (Contexts 5 & 6): on first click we
create a ReferralIdentity (keyed by the raw client_id, id_source=native) and a
Referral (with its source), alongside the immutable Click event (apps.events).
Prospect/lead are NOT pulled in here — those are M3/M4.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import AuditedModel, SoftDeleteModel, TenantScopedModel


class Customer(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """An existing Zerodha client who refers — the referrer (05 Context 4).

    Deliberately MINIMAL — GoRefer must not become a customer master (NO PAN / KYC /
    brokerage). Used in M5 only to resolve a referrer's phone when GoRefer actually
    knows it (Abhay's own customers); otherwise the referrer notification is skipped.
    Eligibility/status are display-only — their source of truth is Zerodha/Zoho.
    """

    program = models.ForeignKey(
        "referrals.ReferralProgram", on_delete=models.PROTECT, related_name="customers"
    )
    partner = models.ForeignKey("referrals.Partner", on_delete=models.PROTECT, related_name="customers")
    client_id = models.CharField(max_length=64)
    mobile = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    first_name = models.CharField(max_length=80, blank=True, default="")
    last_name = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=20, default="active")

    class Meta:
        db_table = "customers"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "program", "client_id"], name="uq_customer_program_client"
            ),
        ]
        indexes = [models.Index(fields=["mobile"]), models.Index(fields=["email"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"customer<{self.client_id}>"


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
    # Regulator whose mandated disclosure block this program carries — drives the
    # ordering on the per-sub-broker disclosure page /d/{slug} (B2 / ADR-031):
    # SEBI/NSE (securities) → IRDAI (insurance) → RBI (loans) → …
    REGULATOR_CHOICES = [
        ("sebi_nse", "SEBI / NSE"),
        ("irdai", "IRDAI"),
        ("rbi", "RBI"),
        ("other", "Other"),
    ]

    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="programs")
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    logo_url = models.URLField(blank=True, default="")
    brand_color = models.CharField(max_length=20, blank=True, default="")
    reward_description = models.TextField(blank=True, default="")
    terms_url = models.URLField(blank=True, default="")

    # --- Disclosure composition (B2 / ADR-031) — the /d/{slug} page renders each
    # ACTIVE program's regulator block, ordered by (disclosure_sequence, regulator).
    # `disclosure_template` is a config-driven text with {placeholders} filled from
    # the partner/tenant's own values (AP code, SEBI reg, etc.). Blank = fall back to
    # the canonical central AP disclosure block (interim single-partner behaviour).
    regulator = models.CharField(max_length=16, choices=REGULATOR_CHOICES, default="sebi_nse")
    disclosure_template = models.TextField(blank=True, default="")
    disclosure_sequence = models.IntegerField(default=100)

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


class ReferralIdentity(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """The identity of a referrer within a program (05-Database-Design Context 5).

    Keyed by (partner, client_id, id_source). For Zerodha the client_id IS the raw
    Zerodha client id carried in gorefer.in/r/{client_id} — no opaque token
    (ADR-001). Created LAZILY on first click (never pre-provisioned), after the
    client_id is format-validated. `token` stays NULL for Zerodha (reserved for a
    future non-native partner id).
    """

    ID_SOURCE_CHOICES = [("native", "native"), ("generated", "generated")]
    STATUS_CHOICES = [("active", "active"), ("disabled", "disabled")]

    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="referral_identities")
    program = models.ForeignKey(ReferralProgram, on_delete=models.PROTECT, related_name="referral_identities")
    client_id = models.CharField(max_length=64)
    id_source = models.CharField(max_length=16, choices=ID_SOURCE_CHOICES, default="native")
    token = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")

    class Meta:
        db_table = "referral_identities"
        constraints = [
            # The identity key, resolved on every redirect, unique per tenant.
            models.UniqueConstraint(
                fields=["tenant", "partner", "client_id", "id_source"],
                name="uq_referral_identity_key",
            ),
        ]
        indexes = [
            models.Index(fields=["program"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"identity<{self.client_id}>"


class Referral(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """The act/instance of a referral (05-Database-Design Context 6).

    Created lazily on first click alongside the identity. `referral_identity` is
    NULLABLE — a partner-direct journey (GET /open) and a future Zoho-imported
    off-platform conversion have NO referrer identity (Gap 1 / ADR-015). `source`
    distinguishes them. Conversion/credit fields are NOT set here — they only ever
    come from Zoho (M6), never fabricated.
    """

    SOURCE_CHOICES = [
        ("referral_link", "referral_link"),
        ("partner_direct", "partner_direct"),
        ("zoho_import", "zoho_import"),
    ]
    STATUS_CHOICES = [
        ("created", "created"),
        ("opened", "opened"),
        ("landing_viewed", "landing_viewed"),
        ("signup_started", "signup_started"),
        ("signup_completed", "signup_completed"),
        ("confirmed", "confirmed"),
        ("rewarded", "rewarded"),
    ]

    referral_identity = models.ForeignKey(
        ReferralIdentity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="referrals",
    )
    program = models.ForeignKey(ReferralProgram, on_delete=models.PROTECT, related_name="referrals")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")
    first_click_at = models.DateTimeField(null=True, blank=True)

    # --- Conversion fields — set ONLY from the Zoho import path (M6). Never
    # fabricated by an internal write (guardrail #2). ---
    conversion_status = models.CharField(max_length=20, blank=True, default="")  # mirrors Zoho
    conversion_source = models.CharField(max_length=20, blank=True, default="")  # 'zoho'
    credited_referrer = models.CharField(max_length=64, blank=True, default="")  # winning client_id (Zoho)
    reward_status = models.CharField(max_length=40, blank=True, default="")      # display-only, Zoho signal
    # TRUE Zoho account-opening date (ADR-017), distinct from the sync date; all
    # conversion analytics run off THIS, never the import date.
    account_opened_at = models.DateTimeField(null=True, blank=True)
    conversion_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "referrals"
        indexes = [
            models.Index(fields=["referral_identity"]),
            models.Index(fields=["source"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            # Fable5 M1: lazy create is check-then-insert and races under concurrent
            # first clicks (a WhatsApp blast is exactly that shape). Partial UNIQUE
            # constraints make a race raise IntegrityError instead of twinning a
            # journey; the service catches it and refetches the winner.
            #
            # Identity-backed journeys (referral_link / zoho_import): one per
            # (tenant, identity, source). Partial — only where the identity is present.
            models.UniqueConstraint(
                fields=["tenant", "referral_identity", "source"],
                condition=models.Q(referral_identity__isnull=False),
                name="uq_referral_tenant_identity_source",
            ),
            # Partner-direct journeys have a NULL identity — one row per (tenant,
            # source) for source=partner_direct. A separate partial unique because a
            # composite unique over a nullable FK doesn't constrain NULL rows.
            models.UniqueConstraint(
                fields=["tenant", "source"],
                condition=models.Q(referral_identity__isnull=True, source="partner_direct"),
                name="uq_referral_partner_direct_tenant",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"referral<{self.pk}:{self.source}>"


class Prospect(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """The person who may open an account — the "friend" (05 Context 7).

    An ERASABLE PII record: name/mobile/email/city live here (and on Lead), never
    in the immutable event log (#16/#17). Unconverted PII is anonymized after 12
    months (Sprint 1: manual erasure). `mobile` is the canonical normalized key.
    """

    mobile = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=120, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    lead_source = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        db_table = "prospects"
        indexes = [models.Index(fields=["email"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"prospect<{self.mobile}>"


class Lead(AuditedModel, SoftDeleteModel, TenantScopedModel):
    """CRM-linkage lead — GoRefer's shadow of the Zoho pipeline (05 Context 11).

    Saved to GoRefer FIRST on form submit (capture-first); Zoho mirroring is M6
    (behind ENABLE_ZOHO_WRITE). Account/reward STATUS is set only from Zoho, never
    fabricated. This is an erasable PII home; the immutable event log holds none.
    `submitted_by` distinguishes the friend filling their own details vs the
    referrer filling the friend's.
    """

    STATUS_CHOICES = [
        ("new", "new"),
        ("contacted", "contacted"),
        ("interested", "interested"),
        ("kyc_started", "kyc_started"),
        ("account_opened", "account_opened"),
        ("rejected", "rejected"),
    ]
    SUBMITTED_BY_CHOICES = [("friend", "friend"), ("referrer", "referrer")]

    referral = models.ForeignKey(Referral, on_delete=models.PROTECT, related_name="leads")
    prospect = models.ForeignKey(Prospect, on_delete=models.PROTECT, related_name="leads")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    status_source = models.CharField(max_length=20, blank=True, default="")  # 'zoho' when imported (M6)
    submitted_by = models.CharField(max_length=12, choices=SUBMITTED_BY_CHOICES, default="friend")
    # How this lead entered GoRefer — e.g. 'landing' (self-serve form) or
    # 'whatsapp_assisted' (B4 / ADR-033: referrer asked us to reach their friend).
    lead_source = models.CharField(max_length=32, blank=True, default="landing")
    consent = models.BooleanField(default=False)
    # DPDP: when consent was captured (third-party PII in the assisted branch).
    consent_captured_at = models.DateTimeField(null=True, blank=True)
    zoho_lead_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    # The GoRefer journey-reference stamped onto the Zoho lead (#10, Model 2). Kept
    # here so a re-run can prove it was never lost, and so a later Zoho conversion
    # can be joined back to this journey.
    gorefer_reference = models.CharField(max_length=64, blank=True, default="")
    account_opened_at = models.DateTimeField(null=True, blank=True)  # TRUE Zoho date (M6)

    # --- Zoho WRITE sync state (retry/backfill) --------------------------------
    # Lives on this ERASABLE model, never in the immutable event log (#16/#17).
    # Tracks only whether OUR write reached Zoho — it is NOT account status, which
    # still comes solely from the Zoho inbound path (guardrail #2).
    SYNC_PENDING, SYNC_SYNCED, SYNC_FAILED = "pending", "synced", "failed"
    ZOHO_SYNC_STATUS_CHOICES = [
        (SYNC_PENDING, "pending"),
        (SYNC_SYNCED, "synced"),
        (SYNC_FAILED, "failed"),  # attempts exhausted — surfaced in the admin, never silent
    ]
    zoho_sync_status = models.CharField(
        max_length=10, choices=ZOHO_SYNC_STATUS_CHOICES, default=SYNC_PENDING
    )
    zoho_sync_attempts = models.PositiveIntegerField(default=0)
    zoho_last_error = models.TextField(blank=True, default="")
    zoho_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "leads"
        indexes = [
            models.Index(fields=["referral"]),
            models.Index(fields=["status"]),
            # The backfill sweep scans (status, attempts) oldest-first — keep it cheap
            # as leads accumulate.
            models.Index(fields=["zoho_sync_status", "zoho_sync_attempts"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"lead<{self.pk}:{self.status}>"
