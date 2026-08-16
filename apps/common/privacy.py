"""DPDP erasure + retention purge (CLAUDE.md §4 Privacy, ADR-020).

WHY THIS EXISTS
---------------
Both obligations were SPECIFIED and NEITHER was implemented (found 2026-07-27):

  - "manual erasure on request in Sprint 1 (ADR-020)" — `VisitorPII.erased_at` existed
    and was READ (`dashboard/profile.py` filters on it), but nothing ever WROTE it. There
    was no service, no command, no admin action. A real erasure request would have meant
    hand-editing the database.
  - "anonymize/purge UNCONVERTED prospect PII after 12 months" — absent entirely; the only
    purges in the codebase were for auth nonces.

The existing test `test_i3_visitor_pii_is_erasable` looked like coverage but performed the
erasure ITSELF (set `raw_ip=None`, stamped `erased_at`, saved). It proved the model can
HOLD an erased state, not that any code can produce one.

T-157 (2026-08-16, eight-lens review M4 wave 2) found this module itself had drifted: it
only ever touched `Prospect`/`VisitorPII`, while `Notification`, `FollowupWindow`,
`ScheduledFollowup`, `AdvisorCallbackRequest`, `SyncedReferrer` and
`ScheduledCampaignMessage` were all added later, all carry a mobile (`Notification` also
carries name/email inside `template_params`), and none of them were ever wired in — a
"forgotten" person's number and name lived on in every send/schedule record. `Prospect`
already documented this exact drift class happening once before; T-157 is the second
occurrence, which is why `COVERED_PII_FIELDS`/`EXEMPT_PII_FIELDS` below plus
`tests/test_pii_erasure_rail.py` exist — a field-introspection CI rail that fails the
build the next time a PII column is added and this module isn't, instead of relying on
someone remembering.

WHAT IS AND IS NOT ERASED
-------------------------
Erased: the identifying fields — `Prospect.name/email/city`, `Lead`-linked contact data,
`VisitorPII.raw_ip/city`, `Notification.recipient_mobile`/`template_params` (name/email/
mobile values only — see `_scrub_template_params`), `FollowupWindow.mobile`,
`ScheduledFollowup.mobile`, `AdvisorCallbackRequest.mobile`/`name`,
`SyncedReferrer.mobile`/`name`, `ScheduledCampaignMessage.mobile`, `Customer.mobile`/
`email` (the referrals-app record used to resolve a referrer's phone for M5 notifications),
`OtpChallenge.recipient` (the checker-probe finding, T-157 round 2, 2026-08-16 — a field
named `recipient`, not `*mobile*`/`*phone*`/`*email*`, that evaded rail E-8's name pattern
entirely; see the pattern hardening below).

DELIBERATELY KEPT:
  - The immutable event log. It holds NO PII by design (Round-2 #16), so erasure has
    nothing to do there — and rewriting it would destroy the audit trail that proves what
    happened. Analytics counts therefore survive erasure unchanged, which is the point.
  - `Prospect.mobile` (and every other "mobile" column this module touches) is
    PSEUDONYMISED via `pseudonymise_mobile`, not blanked. It is the dedupe key that stops
    one person becoming several records; nulling it would fracture history and could
    resurrect the very person who asked to be forgotten as a brand-new prospect on their
    next click. Every table is pseudonymised with the SAME digest of the SAME canonical
    mobile, so they stay a matched set without any of them holding the real number.
  - `WhatsAppOptOut.mobile` — NEVER touched, on purpose (see `EXEMPT_PII_FIELDS` below).
    It is a suppression-list key, not marketing PII: pseudonymising it would silently
    re-enable messaging to someone who told us to stop, defeating the table's entire
    reason for existing. DPDP itself permits retaining the minimum data needed to honour
    the person's own do-not-contact instruction.
  - Conversion/account status. GUARDRAIL 2 — only the Zoho ingest may write those. A
    converted account is a business/regulatory record, not marketing PII, so converted
    subjects are excluded from the automatic purge (a manual request still erases them).
  - `ReferrerAccount.mobile`/`google_email` and `VerificationRequest.mobile_entered`/
    `google_email` — these are LOGIN credentials, not just contact records; erasing them
    could silently break a referrer's ability to sign back in. Left as a documented,
    owner-flagged gap (COORDINATION.md, T-157) rather than guessed at, per this repo's
    "surface an inconsistency, don't silently resolve it" rule (CLAUDE.md §3).

Idempotent throughout: erasing twice is a no-op, so a retried job or a duplicated request
cannot corrupt anything.
"""
from __future__ import annotations

import hashlib
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("gorefer.privacy")

#: Retention for UNCONVERTED prospect PII. Configuration, not code (§6d) — an operator
#: may need to shorten it for a stricter jurisdiction without a deploy.
RETENTION_DAYS_KEY = "pii_retention_days"
DEFAULT_RETENTION_DAYS = 365

ERASED_NAME = "[erased]"

#: (app_label, ModelName) -> the field names on it that `erase_subject`/
#: `purge_expired_pii` actually reach today. `tests/test_pii_erasure_rail.py` walks
#: every TENANT-SCOPED model for a CharField/EmailField named mobile/phone/email and
#: fails the build if it finds one that is neither here nor in `EXEMPT_PII_FIELDS` —
#: this is the anti-drift rail T-157 exists to add. Keep this EMPTY of anything not
#: really wired into the functions below; the rail's stale-entry test catches a lie.
COVERED_PII_FIELDS: dict[tuple[str, str], frozenset[str]] = {
    ("referrals", "Prospect"): frozenset({"mobile", "email"}),
    ("referrals", "Customer"): frozenset({"mobile", "email"}),
    ("integrations", "Notification"): frozenset({"recipient_mobile"}),
    ("followups", "FollowupWindow"): frozenset({"mobile"}),
    ("followups", "ScheduledFollowup"): frozenset({"mobile"}),
    ("followups", "AdvisorCallbackRequest"): frozenset({"mobile"}),
    ("campaigns", "SyncedReferrer"): frozenset({"mobile"}),
    ("campaigns", "ScheduledCampaignMessage"): frozenset({"mobile"}),
    ("otp", "OtpChallenge"): frozenset({"recipient"}),
}

#: Fields the rail would otherwise flag, deliberately left OUT of `COVERED_PII_FIELDS`,
#: each with a reason a reviewer can check. This is not a place to silence the rail — it
#: is a place to explain why silencing it here is correct (or, for the last three
#: entries, to keep the gap VISIBLE until the owner decides, rather than hiding it).
EXEMPT_PII_FIELDS: dict[tuple[str, str], dict[str, str]] = {
    ("followups", "WhatsAppOptOut"): {
        "mobile": (
            "Suppression-list key, kept in plaintext on purpose. Pseudonymising it would "
            "let the same real WhatsApp number be messaged again after it re-appears "
            "under a fresh Prospect — silently un-suppressing someone who said STOP. "
            "DPDP permits retaining the minimum data needed to honour the person's own "
            "do-not-contact instruction. See the model's own docstring."
        ),
    },
    ("accounts", "ReferrerAccount"): {
        "mobile": (
            "Out of T-157 scope (2026-08-16) — a login-identity field, not just a contact "
            "record; erasing it risks silently breaking sign-in. Flagged in COORDINATION.md "
            "as a QUESTION for an owner decision, not resolved here."
        ),
        "google_email": (
            "Out of T-157 scope (2026-08-16) — the verified OAuth login identity; erasing "
            "it risks silently breaking sign-in. Flagged in COORDINATION.md as a QUESTION "
            "for an owner decision, not resolved here."
        ),
    },
    ("accounts", "VerificationRequest"): {
        "mobile_entered": (
            "Out of T-157 scope (2026-08-16) — part of a login-verification audit trail. "
            "Flagged in COORDINATION.md as a QUESTION for an owner decision, not resolved "
            "here."
        ),
        "google_email": (
            "Out of T-157 scope (2026-08-16) — part of a login-verification audit trail. "
            "Flagged in COORDINATION.md as a QUESTION for an owner decision, not resolved "
            "here."
        ),
    },
}


def _retention_days(tenant_id: int | None) -> int:
    from apps.config.cascade import resolve

    try:
        return int(resolve(RETENTION_DAYS_KEY, tenant_id=tenant_id, default=DEFAULT_RETENTION_DAYS))
    except Exception:
        return DEFAULT_RETENTION_DAYS


def pseudonymise_mobile(mobile: str) -> str:
    """A stable, non-reversible stand-in that preserves dedupe without holding the number.

    Same input -> same token, so the person stays ONE record; the number itself is gone.
    """
    # MUST fit Prospect.mobile (max_length=20). "erased:" is 7 chars, so 12 hex digits
    # gives 19 — 48 bits of collision resistance, far beyond what a dedupe key needs, and
    # it fits. A 16-digit version overflowed the column and raised DataError on save.
    digest = hashlib.sha256((mobile or "").encode()).hexdigest()[:12]
    return f"erased:{digest}"


def _scrub_template_params(params, redact_values: set[str]):
    """Redact any `{"name": ..., "value": ...}` entry whose value is in `redact_values`.

    `Notification.template_params` is a point-in-time snapshot of what was actually
    substituted into a send (see `apps/integrations/models.py`) — a name, mobile, or
    email can ride in there even after the source record is erased. Only entries whose
    VALUE matches are touched; the `name` key (the template variable's slot name, e.g.
    "prospect_mobile") is metadata, not PII, and is left alone so the row stays legible.
    """
    if not params:
        return params
    scrubbed = []
    for item in params:
        if isinstance(item, dict) and item.get("value") in redact_values:
            item = {**item, "value": ERASED_NAME}
        scrubbed.append(item)
    return scrubbed


@transaction.atomic
def erase_subject(tenant, *, mobile: str | None = None, visitor_id: str | None = None) -> dict:
    """Erase one person's PII on request (DPDP). Idempotent.

    Identified by mobile (the usual request key) and/or visitor_id. Returns a per-model
    tally so the operator has evidence of what was actually done — an erasure you cannot
    evidence is not much use when someone asks you to prove it.
    """
    from apps.campaigns.models import ScheduledCampaignMessage, SyncedReferrer
    from apps.events.models import VisitorPII
    from apps.followups.models import AdvisorCallbackRequest, FollowupWindow, ScheduledFollowup
    from apps.integrations.models import Notification
    from apps.otp.models import OtpChallenge
    from apps.referrals.models import Customer, Prospect

    counts = {
        "prospects": 0, "visitor_pii": 0, "leads": 0,
        "notifications": 0, "followup_windows": 0, "scheduled_followups": 0,
        "advisor_callback_requests": 0, "synced_referrers": 0,
        "scheduled_campaign_messages": 0, "customers": 0, "otp_challenges": 0,
    }
    now = timezone.now()

    if mobile:
        from apps.common.phone import normalize_phone

        canonical = normalize_phone(mobile)
        pseudo = pseudonymise_mobile(canonical)
        redact_values = {canonical}

        qs = Prospect.objects.for_tenant(tenant).filter(mobile=canonical)
        for prospect in qs:
            if prospect.name and prospect.name != ERASED_NAME:
                redact_values.add(prospect.name)
            if prospect.email:
                redact_values.add(prospect.email)
            prospect.name = ERASED_NAME
            prospect.email = ""
            prospect.city = ""
            prospect.mobile = pseudo
            prospect.save(update_fields=["name", "email", "city", "mobile", "updated_at"])
            counts["prospects"] += 1
            counts["leads"] += prospect.leads.count()

        # Notification: recipient_mobile pseudonymised AND template_params scrubbed of
        # this subject's name/email/mobile values (scoped to rows ADDRESSED to this
        # subject — a subject's data embedded inside someone ELSE's notification, e.g.
        # an office alert naming a referrer, is a separate cross-reference question not
        # covered here; see COORDINATION.md T-157).
        notif_qs = Notification.objects.for_tenant(tenant).filter(recipient_mobile=canonical)
        for notif in notif_qs:
            notif.template_params = _scrub_template_params(notif.template_params, redact_values)
            notif.recipient_mobile = pseudo
            notif.save(update_fields=["recipient_mobile", "template_params", "updated_at"])
            counts["notifications"] += 1

        counts["followup_windows"] += FollowupWindow.objects.for_tenant(tenant).filter(
            mobile=canonical
        ).update(mobile=pseudo)

        counts["scheduled_followups"] += ScheduledFollowup.objects.for_tenant(tenant).filter(
            mobile=canonical
        ).update(mobile=pseudo)

        counts["scheduled_campaign_messages"] += ScheduledCampaignMessage.objects.for_tenant(
            tenant
        ).filter(mobile=canonical).update(mobile=pseudo)

        counts["advisor_callback_requests"] += AdvisorCallbackRequest.objects.for_tenant(
            tenant
        ).filter(mobile=canonical).update(mobile=pseudo, name=ERASED_NAME)

        counts["synced_referrers"] += SyncedReferrer.objects.for_tenant(tenant).filter(
            mobile=canonical
        ).update(mobile=pseudo, name=ERASED_NAME)

        counts["customers"] += Customer.objects.for_tenant(tenant).filter(
            mobile=canonical
        ).update(mobile=pseudo, email="")

        # `recipient` evades rail E-8's mobile/phone/email name pattern (it's the OTP
        # login channel, not a marketing contact) — pseudonymised same as every other
        # mobile-bearing table, not blanked, so a still-active challenge stays
        # distinguishable per-recipient without holding the real number.
        counts["otp_challenges"] += OtpChallenge.objects.for_tenant(tenant).filter(
            recipient=canonical
        ).update(recipient=pseudo)

    if visitor_id:
        pii_qs = VisitorPII.objects.for_tenant(tenant).filter(
            visitor_id=visitor_id, erased_at__isnull=True
        )
        counts["visitor_pii"] += pii_qs.update(raw_ip=None, city="", erased_at=now)

    logger.info(
        "DPDP erasure applied: tenant=%s mobile=%s visitor=%s counts=%s",
        getattr(tenant, "id", None), bool(mobile), bool(visitor_id), counts,
    )
    return counts


#: Every `counts` key `erase_subject` produces for a mobile-keyed erasure, beyond
#: "prospects" itself — the shared list `purge_expired_pii`'s dry-run tally and the
#: `erase_pii` command's dry-run preview both walk, so a table added to `erase_subject`
#: only has to be added here once to show up in both previews.
MOBILE_ERASURE_TABLE_COUNT_KEYS: tuple[str, ...] = (
    "notifications", "followup_windows", "scheduled_followups",
    "advisor_callback_requests", "synced_referrers",
    "scheduled_campaign_messages", "customers", "otp_challenges",
)


def dry_run_pii_counts(tenant, canonical_mobile: str) -> dict:
    """How many rows a real `erase_subject(tenant, mobile=canonical_mobile)` would touch,
    per table, WITHOUT writing anything — the evidence an operator sees before committing
    to an irreversible erasure.
    """
    from apps.campaigns.models import ScheduledCampaignMessage, SyncedReferrer
    from apps.followups.models import AdvisorCallbackRequest, FollowupWindow, ScheduledFollowup
    from apps.integrations.models import Notification
    from apps.otp.models import OtpChallenge
    from apps.referrals.models import Customer

    return {
        "notifications": Notification.objects.for_tenant(tenant).filter(
            recipient_mobile=canonical_mobile
        ).count(),
        "followup_windows": FollowupWindow.objects.for_tenant(tenant).filter(
            mobile=canonical_mobile
        ).count(),
        "scheduled_followups": ScheduledFollowup.objects.for_tenant(tenant).filter(
            mobile=canonical_mobile
        ).count(),
        "advisor_callback_requests": AdvisorCallbackRequest.objects.for_tenant(tenant).filter(
            mobile=canonical_mobile
        ).count(),
        "synced_referrers": SyncedReferrer.objects.for_tenant(tenant).filter(
            mobile=canonical_mobile
        ).count(),
        "scheduled_campaign_messages": ScheduledCampaignMessage.objects.for_tenant(tenant).filter(
            mobile=canonical_mobile
        ).count(),
        "customers": Customer.objects.for_tenant(tenant).filter(
            mobile=canonical_mobile
        ).count(),
        "otp_challenges": OtpChallenge.objects.for_tenant(tenant).filter(
            recipient=canonical_mobile
        ).count(),
    }


def purge_expired_pii(tenant=None, *, days: int | None = None, dry_run: bool = False) -> dict:
    """Anonymise UNCONVERTED prospect PII older than the retention window (§4).

    Converted subjects are EXCLUDED: an opened account is a business/regulatory record we
    are required to keep, not marketing PII. A manual `erase_subject` still reaches them.

    Runs per tenant so the retention window stays a per-tenant setting.
    """
    from datetime import timedelta

    from apps.events.models import VisitorPII
    from apps.referrals.models import Prospect
    from apps.tenants.models import Tenant

    tenants = [tenant] if tenant is not None else list(Tenant.objects.filter(is_active=True))
    totals = {"prospects": 0, "visitor_pii": 0, "skipped_converted": 0, "dry_run": dry_run}
    for key in MOBILE_ERASURE_TABLE_COUNT_KEYS:
        totals[key] = 0

    for tnt in tenants:
        window = days or _retention_days(getattr(tnt, "id", None))
        cutoff = timezone.now() - timedelta(days=window)
        totals["cutoff"] = cutoff.date().isoformat()
        totals["days"] = window

        stale = Prospect.objects.for_tenant(tnt).filter(created_at__lt=cutoff).exclude(
            name=ERASED_NAME
        )
        for prospect in stale:
            # "Unconverted" is read from the referral's conversion_status — the field the
            # Zoho ingest maintains. Never inferred from Lead.status, which nothing writes
            # (that mistake silently disabled converted-suppression for a month).
            converted = prospect.leads.filter(
                referral__conversion_status="account_opened"
            ).exists()
            if converted:
                totals["skipped_converted"] += 1
                continue
            if dry_run:
                totals["prospects"] += 1
                for key, value in dry_run_pii_counts(tnt, prospect.mobile).items():
                    totals[key] += value
                continue
            counts = erase_subject(tnt, mobile=prospect.mobile)
            totals["prospects"] += 1
            for key in MOBILE_ERASURE_TABLE_COUNT_KEYS:
                totals[key] += counts.get(key, 0)

        old_pii = VisitorPII.objects.for_tenant(tnt).filter(
            created_at__lt=cutoff, erased_at__isnull=True
        )
        if dry_run:
            totals["visitor_pii"] += old_pii.count()
        else:
            totals["visitor_pii"] += old_pii.update(
                raw_ip=None, city="", erased_at=timezone.now()
            )

    logger.info("PII retention purge finished: %s", totals)
    return totals
