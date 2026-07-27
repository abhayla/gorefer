"""DPDP erasure + retention purge (CLAUDE.md §4, ADR-020).

Both obligations were specified and NEITHER was implemented until 2026-07-27. The
pre-existing `test_i3_visitor_pii_is_erasable` performed the erasure ITSELF inside the
test — it proved the model could hold an erased state, not that any code could produce
one. These tests call the REAL service, which is the difference that matters.
"""
import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.common.privacy import ERASED_NAME, erase_subject, purge_expired_pii
from apps.events.models import Event, VisitorPII
from apps.referrals.models import Lead, Prospect, Referral
from apps.tenants.models import Tenant

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.5"}
MOBILE = "9876543210"


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _capture(tenant, mobile=MOBILE, name="Rahul Sharma"):
    """A real captured lead, through the real service."""
    from apps.referrals import lead_service, redirect_service

    program = redirect_service.get_active_program(tenant)
    referral = redirect_service._lazy_get_or_create_referral(tenant, program, "RJ4521")
    lead_service.capture_lead(
        tenant=tenant, referral=referral, name=name, mobile=mobile,
        email="rahul@example.com", city="Lucknow", consent=True,
    )
    return referral


def test_erasure_clears_identifying_fields(seeded):
    _capture(seeded)
    p = Prospect.objects.get()
    assert p.name and p.email and p.city

    counts = erase_subject(seeded, mobile=MOBILE)

    p.refresh_from_db()
    assert counts["prospects"] == 1
    assert p.name == ERASED_NAME
    assert p.email == "" and p.city == ""
    assert "rahul@example.com" not in (p.email or "")


def test_erasure_pseudonymises_the_mobile_rather_than_blanking_it(seeded):
    """Blanking the dedupe key would fracture history — and could resurrect the very
    person who asked to be forgotten as a brand-new prospect on their next click."""
    _capture(seeded)
    erase_subject(seeded, mobile=MOBILE)
    p = Prospect.objects.get()
    assert p.mobile.startswith("erased:")
    assert len(p.mobile) <= 20, "the pseudonym must fit Prospect.mobile(max_length=20)"
    assert MOBILE not in p.mobile
    assert "91" + MOBILE not in p.mobile


def test_erasure_is_idempotent(seeded):
    _capture(seeded)
    erase_subject(seeded, mobile=MOBILE)
    first = Prospect.objects.get().mobile
    # A retried job or a duplicated request must not corrupt anything.
    erase_subject(seeded, mobile=MOBILE)
    assert Prospect.objects.count() == 1
    assert Prospect.objects.get().mobile == first


def test_erasure_clears_visitor_pii_through_the_service(seeded):
    """The REAL service writes erased_at — the old test wrote it by hand."""
    c = Client()
    c.get("/r/RJ4521", **HUMAN)
    pii = VisitorPII.objects.get()
    assert pii.raw_ip == "203.0.113.5"

    counts = erase_subject(seeded, visitor_id=pii.visitor_id)

    pii.refresh_from_db()
    assert counts["visitor_pii"] == 1
    assert pii.raw_ip is None and pii.city == ""
    assert pii.erased_at is not None


def test_erasure_leaves_the_immutable_event_log_and_its_counts_intact(seeded):
    """Events hold NO PII by design, so erasure has nothing to do there — and rewriting
    them would destroy the audit trail. Analytics must survive an erasure unchanged."""
    _capture(seeded)
    before = Event.objects.count()
    types_before = sorted(Event.objects.values_list("event_type", flat=True))

    erase_subject(seeded, mobile=MOBILE)

    assert Event.objects.count() == before
    assert sorted(Event.objects.values_list("event_type", flat=True)) == types_before
    blob = " ".join(str(e.metadata) for e in Event.objects.all())
    assert MOBILE not in blob and "rahul@example.com" not in blob


def test_erasure_does_not_delete_the_lead_or_break_the_referral(seeded):
    """Erasure anonymises; it must not cascade rows away and orphan a journey."""
    referral = _capture(seeded)
    erase_subject(seeded, mobile=MOBILE)
    assert Lead.objects.count() == 1
    assert Referral.objects.filter(pk=referral.pk).exists()


# --- retention purge --------------------------------------------------------

def _age(tenant, days):
    old = timezone.now() - timezone.timedelta(days=days)
    Prospect.objects.filter(tenant=tenant).update(created_at=old)
    VisitorPII.objects.filter(tenant=tenant).update(created_at=old)


def test_purge_anonymises_unconverted_pii_past_the_window(seeded):
    _capture(seeded)
    _age(seeded, 400)
    counts = purge_expired_pii(seeded)
    assert counts["prospects"] == 1
    assert Prospect.objects.get().name == ERASED_NAME


def test_purge_leaves_recent_pii_alone(seeded):
    _capture(seeded)
    _age(seeded, 10)
    counts = purge_expired_pii(seeded)
    assert counts["prospects"] == 0
    assert Prospect.objects.get().name == "Rahul Sharma"


def test_purge_keeps_CONVERTED_subjects(seeded):
    """An opened account is a business/regulatory record, not marketing PII.

    'Converted' is read from `Referral.conversion_status` — the field the Zoho ingest
    maintains — never from `Lead.status`, which nothing writes. Reading the wrong field
    silently disabled converted-suppression in the follow-up engine for a month.
    """
    referral = _capture(seeded)
    Referral.objects.filter(pk=referral.pk).update(conversion_status="account_opened")
    _age(seeded, 400)

    counts = purge_expired_pii(seeded)

    assert counts["skipped_converted"] == 1
    assert counts["prospects"] == 0
    assert Prospect.objects.get().name == "Rahul Sharma"


def test_purge_dry_run_writes_nothing(seeded):
    """Erasure is irreversible — an operator must be able to see the blast radius first."""
    _capture(seeded)
    _age(seeded, 400)
    counts = purge_expired_pii(seeded, dry_run=True)
    assert counts["prospects"] == 1 and counts["dry_run"] is True
    assert Prospect.objects.get().name == "Rahul Sharma"


def test_retention_window_is_configuration_not_code(seeded):
    """§6d — an operator may need a shorter window for a stricter jurisdiction."""
    from apps.common.privacy import RETENTION_DAYS_KEY
    from apps.config.cascade import set_tenant

    _capture(seeded)
    _age(seeded, 40)
    assert purge_expired_pii(seeded)["prospects"] == 0      # inside the default 365d

    set_tenant(RETENTION_DAYS_KEY, 30, tenant_id=seeded.id)
    assert purge_expired_pii(seeded)["prospects"] == 1      # now outside a 30d window


def test_the_management_commands_run(seeded):
    """The sanctioned operator entry points must actually work, not just the service."""
    _capture(seeded)
    call_command("erase_pii", "--mobile", MOBILE, "--dry-run")
    call_command("erase_pii", "--mobile", MOBILE)
    assert Prospect.objects.get().name == ERASED_NAME
    call_command("purge_expired_pii", "--dry-run")


def test_purge_is_registered_as_a_scheduled_job(seeded):
    """A retention obligation nobody runs is not a policy."""
    from django_q.models import Schedule

    call_command("setup_schedules")
    sched = Schedule.objects.filter(name="pii_retention_purge").first()
    assert sched is not None
    assert sched.func == "apps.common.privacy.purge_expired_pii"
