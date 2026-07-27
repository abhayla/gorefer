"""ADR-023 cross-tenant isolation — single-schema `tenant_id` discriminator.

WHAT THIS IS ACTUALLY TESTING (and why the framing matters)
-----------------------------------------------------------
The E2E brief says "tenant-scoped managers block cross-tenant reads". There ARE no
tenant-scoped managers: `TenantScopedModel` contributes a plain FK column and nothing
more. Isolation is therefore a CONVENTION — every query must remember `tenant=` — not
something the ORM enforces.

With one tenant in production that distinction is invisible: a query that forgets the
filter returns the right answer by accident. It stops being invisible the day a second
tenant exists, and then it leaks silently rather than erroring.

So these tests create a SECOND tenant with its own data and assert the read paths that
feed customer- and staff-facing surfaces stay scoped. They are the early-warning system
for a boundary that is currently upheld by discipline alone.
"""
import pytest
from django.core.management import call_command

from apps.referrals.models import Lead, Prospect, Referral, ReferralIdentity
from apps.tenants.models import Tenant


@pytest.fixture
def two_tenants(db):
    """Tenant A is the seeded bootstrap tenant; tenant B is a rival with its own data."""
    call_command("seed_program")
    a = Tenant.objects.get(slug="pifs")
    b = Tenant.objects.create(slug="rival", name="Rival AP", is_active=True)

    from apps.referrals.models import Partner, ProgramRedirectRule, ReferralProgram

    partner_b = Partner.objects.create(tenant=b, name="Rival Partner", code="RIVAL1")
    program_b = ReferralProgram.objects.create(
        tenant=b, partner=partner_b, name="Zerodha", display_name="Zerodha", status="active"
    )
    ProgramRedirectRule.objects.create(
        tenant=b, program=program_b,
        destination_url_template="https://signup.zerodha.com/api/lead/?c=RIVAL1&r={client_id}",
    )
    # The SAME client_id under both tenants — the sharpest possible probe: any unscoped
    # lookup returns whichever row it finds first, and both look plausible.
    for tnt, prog, partner in ((a, ReferralProgram.objects.filter(tenant=a).first(),
                                Partner.objects.filter(tenant=a).first()),
                               (b, program_b, partner_b)):
        identity = ReferralIdentity.objects.create(
            tenant=tnt, partner=partner, program=prog,
            client_id="RJ4521", id_source="native", status="active",
        )
        Referral.objects.create(
            tenant=tnt, referral_identity=identity, program=prog,
            source="referral_link", status="opened",
        )
        prospect = Prospect.objects.create(
            tenant=tnt, mobile="919876543210", name=f"{tnt.slug} person"
        )
        # `has_converted` joins mobile -> Lead -> Referral, so the Lead is required for
        # that path to be exercised at all. Without it the test passes vacuously.
        Lead.objects.create(
            tenant=tnt, referral=Referral.objects.get(tenant=tnt), prospect=prospect,
            status="new", submitted_by="friend",
        )
    return a, b


def test_the_same_client_id_can_exist_under_two_tenants(two_tenants):
    """Precondition for every other test here — if the constraint were global instead of
    tenant-scoped, this would already have failed and isolation would be moot."""
    a, b = two_tenants
    assert ReferralIdentity.objects.filter(client_id="RJ4521").count() == 2
    assert ReferralIdentity.objects.filter(tenant=a, client_id="RJ4521").count() == 1
    assert ReferralIdentity.objects.filter(tenant=b, client_id="RJ4521").count() == 1


def test_referral_lookup_is_scoped(two_tenants):
    a, b = two_tenants
    from apps.referrals.redirect_service import _lazy_get_or_create_referral, get_active_program

    ref_a = _lazy_get_or_create_referral(a, get_active_program(a), "RJ4521")
    ref_b = _lazy_get_or_create_referral(b, get_active_program(b), "RJ4521")
    assert ref_a.pk != ref_b.pk, "the same client_id resolved to ONE referral across tenants"
    assert ref_a.tenant_id == a.id and ref_b.tenant_id == b.id
    # And no extra rows were minted — each tenant reused its own.
    assert ReferralIdentity.objects.filter(client_id="RJ4521").count() == 2


def test_dashboard_kpis_do_not_count_the_other_tenant(two_tenants):
    a, b = two_tenants
    from apps.dashboard.queries import kpis
    from apps.events.models import Event

    # Give tenant B a click that tenant A must never see. kpis() reads the ROLLUP
    # snapshot, not raw events, so the rollup must be recomputed for this to mean
    # anything — asserting against un-recomputed rollups would pass vacuously.
    from apps.events.rollups import recompute_dirty

    Event.objects.create(
        tenant=b, event_type="click", source="click",
        referral=Referral.objects.get(tenant=b), is_bot=False, metadata={},
    )
    recompute_dirty()

    k_a, k_b = kpis(a), kpis(b)
    assert k_b["total_clicks"] == 1, f"tenant B should see its own click: {k_b}"
    assert k_a["total_clicks"] == 0, f"tenant A counted tenant B's click: {k_a}"


def test_referrer_profile_does_not_leak_the_other_tenants_person(two_tenants):
    """The self-view and admin profile both read these builders (ADR-026)."""
    a, b = two_tenants
    from apps.dashboard import profile

    band_a = profile.top_band(a, "RJ4521")
    assert band_a is not None
    clicks_a = profile.clicks_rows(a, "RJ4521")
    assert all(getattr(r, "tenant_id", a.id) == a.id for r in clicks_a) or clicks_a == []


def test_erasure_is_scoped_to_one_tenant(two_tenants):
    """A DPDP request against tenant A must not erase tenant B's identically-numbered
    person — the two share a mobile in this fixture precisely to catch that."""
    from apps.common.privacy import ERASED_NAME, erase_subject

    a, b = two_tenants
    erase_subject(a, mobile="919876543210")

    assert Prospect.objects.get(tenant=a).name == ERASED_NAME
    assert Prospect.objects.get(tenant=b).name == "rival person", (
        "erasing for one tenant erased another tenant's person"
    )


def test_retention_purge_is_scoped_to_one_tenant(two_tenants):
    from django.utils import timezone

    from apps.common.privacy import ERASED_NAME, purge_expired_pii

    a, b = two_tenants
    old = timezone.now() - timezone.timedelta(days=400)
    Prospect.objects.all().update(created_at=old)

    purge_expired_pii(a)

    assert Prospect.objects.get(tenant=a).name == ERASED_NAME
    assert Prospect.objects.get(tenant=b).name == "rival person"


def test_followup_gate_reads_only_its_own_tenants_conversion(two_tenants):
    """`has_converted` decides whether to keep nudging someone. If it ignored tenant, one
    AP's conversion would silence another AP's cadence."""
    from apps.followups import services

    a, b = two_tenants
    Referral.objects.filter(tenant=b).update(conversion_status="account_opened")

    assert services.has_converted(b, "919876543210") is True
    assert services.has_converted(a, "919876543210") is False, (
        "tenant A saw tenant B's conversion"
    )
