"""Recipient-identity resolver tests (doc 15 §12).

Fixtures are built via the REAL services (redirect_service / lead_service) so the
mobile→Prospect→Lead→Referral→referrer chain is exactly the one production creates.
Needs Postgres (the repo's only engine); run under the standard pytest-django suite.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.config.cascade import set_tenant
from apps.referrals import lead_service, redirect_service
from apps.referrals import recipient_identity as ri
from apps.referrals.models import Customer
from apps.tenants.resolve import get_bootstrap_tenant


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def _program(tenant):
    return redirect_service.get_active_program(tenant)


def _prospect_referred_by(tenant, client_id, mobile, name="Riya"):
    """A prospect who arrived via referrer `client_id` (Prospect + Lead + Referral)."""
    program = _program(tenant)
    referral = redirect_service._lazy_get_or_create_referral(tenant, program, client_id)
    lead = lead_service.capture_lead(
        tenant=tenant, referral=referral, name=name, mobile=mobile,
        email="", city="", consent=True,
    )
    return referral, lead


def _make_customer(tenant, client_id, mobile):
    program = _program(tenant)
    return Customer.objects.create(
        tenant=tenant, program=program, partner=program.partner,
        client_id=client_id, mobile=mobile,
    )


def test_prospect_with_referrer_resolves_referrer_link(tenant):
    _prospect_referred_by(tenant, "RJ4521", "9812345678")
    idn = ri.resolve_recipient(tenant, "9812345678")
    assert idn.role == ri.ROLE_PROSPECT
    assert idn.referrer_client_id == "RJ4521"
    assert idn.confidence == "lead_join"
    assert ri.nudge_link_for(idn, tenant_id=tenant.id) == "gorefer.in/r/wa/RJ4521"


def test_prospect_partner_direct_falls_back_to_open(tenant):
    program = _program(tenant)
    referral = redirect_service._get_or_create_partner_direct_referral(tenant, program)
    lead_service.capture_lead(
        tenant=tenant, referral=referral, name="Sam", mobile="9800000001",
        email="", city="", consent=True,
    )
    idn = ri.resolve_recipient(tenant, "9800000001")
    assert idn.role == ri.ROLE_PROSPECT
    assert idn.referrer_client_id == ""
    assert ri.nudge_link_for(idn, tenant_id=tenant.id) == "gorefer.in/open"


def test_zoho_credited_referrer_wins_over_identity(tenant):
    referral, _ = _prospect_referred_by(tenant, "RJ4521", "9800000002")
    referral.credited_referrer = "ZK9999"
    referral.save(update_fields=["credited_referrer"])
    idn = ri.resolve_recipient(tenant, "9800000002")
    assert idn.referrer_client_id == "ZK9999"
    assert idn.confidence == "zoho_credited"


def test_referrer_resolved_by_mobile(tenant):
    _make_customer(tenant, "RJ4521", "919811110000")
    idn = ri.resolve_recipient(tenant, "9811110000")  # bare form still matches
    assert idn.role == ri.ROLE_REFERRER
    assert idn.self_client_id == "RJ4521"
    assert idn.confidence == "customer_match"


def test_dual_role_prospect_in_progress_wins_then_referrer_when_converted(tenant):
    _, lead = _prospect_referred_by(tenant, "AA1111", "919822220000")
    _make_customer(tenant, "BB2222", "919822220000")
    idn = ri.resolve_recipient(tenant, "919822220000")
    assert idn.role == ri.ROLE_PROSPECT  # incomplete account wins

    lead.status = "account_opened"
    lead.save(update_fields=["status"])
    idn2 = ri.resolve_recipient(tenant, "919822220000")
    assert idn2.role == ri.ROLE_REFERRER
    assert idn2.self_client_id == "BB2222"


def test_unknown_mobile_gets_open_link(tenant):
    idn = ri.resolve_recipient(tenant, "919899999999")
    assert idn.role == ri.ROLE_UNKNOWN
    assert ri.nudge_link_for(idn, tenant_id=tenant.id) == "gorefer.in/open"


def test_language_comes_from_existing_referrer_language_rule(tenant):
    set_tenant("referrer_language", "hi", tenant_id=tenant.id)
    idn = ri.resolve_recipient(tenant, "919899999999")
    assert idn.lang == "hi"


def test_blank_mobile_is_unknown_never_raises(tenant):
    idn = ri.resolve_recipient(tenant, "")
    assert idn.role == ri.ROLE_UNKNOWN


def test_link_mode_open_only_ignores_referrer(tenant):
    _prospect_referred_by(tenant, "RJ4521", "9800000003")
    set_tenant("followup_link_mode", "open_only", tenant_id=tenant.id)
    idn = ri.resolve_recipient(tenant, "9800000003")
    assert ri.nudge_link_for(idn, tenant_id=tenant.id) == "gorefer.in/open"
