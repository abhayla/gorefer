"""Rail E-8 (T-157): DPDP erasure coverage is STRUCTURAL, not remembered.

`apps/common/privacy.py`'s own docstring records this drift class happening TWICE —
`erase_subject`/`purge_expired_pii` were written to cover `Prospect`/`VisitorPII`, and
every mobile-bearing table added afterwards (`Notification`, `FollowupWindow`,
`ScheduledFollowup`, `AdvisorCallbackRequest`, `SyncedReferrer`,
`ScheduledCampaignMessage`) was silently missed, because nothing forced an author
touching a new model to also touch the erasure module.

This rail makes that machine-checked, same shape as the E-7 tenant-scoping rail
(`tests/test_tenant_scoping_rail.py`): field-introspection instead of AST (model fields
are far easier to interrogate via Django's own `_meta` than to parse), an EMPTY-ish
baseline registry that can only grow with a justification, and a self-test proving the
scanner actually fires.

SCOPE (read before extending): this walks TENANT-SCOPED models only, for a
CharField/EmailField whose NAME contains "mobile", "phone", "email", or the exact word
"recipient". That is a name heuristic, not a semantic one — it will not catch a PII field
named something else entirely. The checker-probe finding (T-157 round 2, 2026-08-16)
caught exactly this: `apps.otp.models.OtpChallenge.recipient` holds "the recipient
mobile" per the model's own docstring, under a name the original mobile/phone/email
pattern couldn't see. `recipient` was added as a whole-word alternative rather than
widened further (e.g. a bare "contact" substring would also catch `recipient_role`,
which is a role label, not PII) — this stays a narrow, reviewable allowlist, not a
license to keep chasing every synonym; a field named something else again still needs a
human to notice. It also does not reach into JSONField blobs (`Notification.
template_params`, `ZohoDeadLetter.payload`) — those are scrubbed/handled by hand in
`privacy.py`, not by this rail. Treat a green rail as "no NAMED mobile/phone/email/
recipient column was left stranded", not as "every PII field in the schema is provably
erasable".
"""
from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.db import models as djmodels

from apps.common.models import TenantScopedModel
from apps.common.privacy import COVERED_PII_FIELDS, EXEMPT_PII_FIELDS

PII_FIELD_PATTERN = re.compile(r"(mobile|phone|email|\brecipient\b)", re.IGNORECASE)


def _tenant_scoped_pii_fields() -> list[tuple[str, str, str]]:
    """(app_label, ModelName, field_name) for every mobile/phone/email scalar column
    on a tenant-scoped model, across the whole installed app registry."""
    hits: list[tuple[str, str, str]] = []
    for model in django_apps.get_models():
        if not issubclass(model, TenantScopedModel):
            continue
        for field in model._meta.get_fields():
            if not isinstance(field, (djmodels.CharField, djmodels.EmailField)):
                continue
            if not PII_FIELD_PATTERN.search(field.name):
                continue
            hits.append((model._meta.app_label, model.__name__, field.name))
    return hits


def _offenders(hits: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    offenders = []
    for app_label, model_name, field_name in hits:
        key = (app_label, model_name)
        covered = field_name in COVERED_PII_FIELDS.get(key, frozenset())
        exempt = field_name in EXEMPT_PII_FIELDS.get(key, {})
        if not covered and not exempt:
            offenders.append((app_label, model_name, field_name))
    return offenders


def test_e8_every_pii_field_is_covered_or_exempt():
    offenders = _offenders(_tenant_scoped_pii_fields())
    assert not offenders, (
        "mobile/phone/email field(s) on a tenant-scoped model with no erasure coverage "
        "and no documented exemption:\n  "
        + "\n  ".join(f"{app}.{model}.{field}" for app, model, field in offenders)
        + "\n\nEither extend apps.common.privacy.erase_subject (and add the field to "
        "COVERED_PII_FIELDS there), or add it to EXEMPT_PII_FIELDS with a one-line "
        "justification a reviewer can check."
    )


def test_e8_registry_entries_are_real_and_still_needed():
    """A stale registry entry is worse than none — it silently un-guards a live field."""
    hit_keys = {(app, model, field) for app, model, field in _tenant_scoped_pii_fields()}
    stale = [
        (app, model, field)
        for (app, model), fields in COVERED_PII_FIELDS.items()
        for field in fields
        if (app, model, field) not in hit_keys
    ] + [
        (app, model, field)
        for (app, model), fields in EXEMPT_PII_FIELDS.items()
        for field in fields
        if (app, model, field) not in hit_keys
    ]
    assert not stale, (
        f"registry entries with no matching field on any tenant-scoped model: {stale} — "
        "delete them so the rail keeps guarding real fields, not stale names."
    )


def test_e8_scanner_detects_a_violation():
    """The rail must actually fire — a scanner that finds nothing proves nothing."""
    synthetic = [("fake_app", "FakeModel", "mobile")]
    offenders = _offenders(synthetic)
    assert offenders == synthetic, "scanner failed to flag an unregistered PII field"
