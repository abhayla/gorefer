"""T-130 — `sweep_customer_name_drift` + `sync_referrer_names` drift correction.

Proven here:
  1. the sweep flags a Customer row whose name disagrees with `SyncedReferrer`
     (the already-synced Zoho `Referrers` name) and leaves matching rows alone;
  2. a row is flagged `demo_seed_shadow` when its client_id is one seed_demo uses
     (RJ4521/DA1707/...) — the exact class of row behind the live incident
     (Customer id=2, client_id DA1707, demo-seed "Amit Deshpande" vs Zoho's real
     "Abhay Kumar");
  3. the sweep never writes — running it twice leaves the DB unchanged;
  4. `sync_referrer_names` now corrects that same drift (T-130's job fix) so a
     row the sweep flags today is gone from the sweep after the job runs;
  5. the management command surfaces the same counts on stdout.
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.campaigns.models import SyncedReferrer
from apps.integrations.zoho import tasks as zoho_tasks
from apps.referrals.models import Customer, ReferralIdentity, ReferralProgram
from apps.tenants.resolve import get_bootstrap_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def program(db):
    call_command("seed_program")
    return ReferralProgram.objects.get()


def _customer(program, client_id, first, last):
    return Customer.objects.create(
        tenant=program.tenant, program=program, partner=program.partner,
        client_id=client_id, first_name=first, last_name=last,
    )


def _synced_referrer(tenant, client_id, name):
    from django.utils import timezone
    return SyncedReferrer.objects.create(
        tenant=tenant, client_id=client_id, mobile="919876543210", name=name,
        record_created_at=timezone.now(), active=True,
    )


def test_sweep_flags_mismatch_and_ignores_match(program):
    tenant = get_bootstrap_tenant()
    _customer(program, "SW1001", "Wrong", "Name")
    _synced_referrer(tenant, "SW1001", "Right Name")
    _customer(program, "SW2002", "Same", "Name")
    _synced_referrer(tenant, "SW2002", "Same Name")

    result = zoho_tasks.sweep_customer_name_drift(tenant=tenant)

    ids = {row["client_id"] for row in result["rows"]}
    assert "SW1001" in ids
    assert "SW2002" not in ids
    assert result["mismatched"] == 1


def test_sweep_flags_demo_seed_shadow_for_the_live_incident_id(program):
    """DA1707 is a seed_demo id; if it also carries a name that disagrees with
    Zoho, the sweep must call it out as a demo-seed shadow candidate."""
    tenant = get_bootstrap_tenant()
    call_command("seed_demo")  # creates Customer(client_id="DA1707", "Amit", "Deshpande")
    _synced_referrer(tenant, "DA1707", "Abhay Kumar")

    result = zoho_tasks.sweep_customer_name_drift(tenant=tenant)

    row = next(r for r in result["rows"] if r["client_id"] == "DA1707")
    assert row["demo_seed_shadow"] is True
    assert row["local_name"] == "Amit Deshpande"
    assert row["zoho_name"] == "Abhay Kumar"


def test_sweep_is_read_only(program):
    tenant = get_bootstrap_tenant()
    _customer(program, "SW3003", "Wrong", "Name")
    _synced_referrer(tenant, "SW3003", "Right Name")

    zoho_tasks.sweep_customer_name_drift(tenant=tenant)
    zoho_tasks.sweep_customer_name_drift(tenant=tenant)

    cust = Customer.objects.get(client_id="SW3003")
    assert (cust.first_name, cust.last_name) == ("Wrong", "Name")


def test_job_fix_clears_a_sweep_flagged_row(program, monkeypatch):
    """The scenario end to end: sweep flags it, the fixed sync job corrects it,
    the sweep no longer flags it."""
    tenant = get_bootstrap_tenant()
    _customer(program, "SW4004", "Stale", "Demo")
    _synced_referrer(tenant, "SW4004", "Zoho Truth")
    ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner,
        client_id="SW4004", status="active",
    )

    class _FakeReadAdapter:
        def fetch_contact_by_client_id(self, *, client_id):
            from apps.integrations.zoho.read import ZohoContact
            if client_id != "SW4004":
                return ZohoContact(client_id=client_id, matched=False)
            return ZohoContact(client_id=client_id, matched=True, full_name="Zoho Truth")

    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter", lambda: _FakeReadAdapter()
    )

    before = zoho_tasks.sweep_customer_name_drift(tenant=tenant)
    assert any(r["client_id"] == "SW4004" for r in before["rows"])

    zoho_tasks.sync_referrer_names()

    after = zoho_tasks.sweep_customer_name_drift(tenant=tenant)
    assert not any(r["client_id"] == "SW4004" for r in after["rows"])


def test_sweep_management_command_reports_mismatch(program):
    tenant = get_bootstrap_tenant()
    _customer(program, "SW5005", "Wrong", "Name")
    _synced_referrer(tenant, "SW5005", "Right Name")

    out = StringIO()
    call_command("sweep_name_drift", stdout=out)

    output = out.getvalue()
    assert "mismatched: 1" in output
    assert "SW5005" in output
