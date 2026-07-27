"""Conversion reconciler (P0, 2026-07-26).

The webhook silently delivered nothing for a month: the trigger watched Zoho *Leads* while a
converting lead becomes a *Contact*, and nothing reconciled, so "no conversions arrived" and
"no conversions happened" were indistinguishable. These tests pin the behaviours that make a
missed webhook self-heal — and the filter that stops it inventing conversions.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.integrations.models import Conversion
from apps.integrations.zoho import reconcile
from apps.referrals.models import Referral
from apps.tenants.resolve import get_bootstrap_tenant

# One page of Zoho Contacts as the live layout actually returns it. AACK095261 is real:
# an AngelOne account sitting in the SAME module as the Zerodha ones.
ROWS = [
    {"id": "1", "Full_Name": "Malvika Gupta", "ClientId": "EUG979",
     "Referrer_Client_Id": "YTW629", "Account_Opened_On": "2026-07-16", "Account_Status": None},
    {"id": "2", "Full_Name": "Uday Kumar Singh", "ClientId": "UGF159",
     "Referrer_Client_Id": None, "Account_Opened_On": "2026-07-18", "Account_Status": None},
    {"id": "3", "Full_Name": "Sneha Kumari", "ClientId": "AACK095261",
     "Referrer_Client_Id": None, "Account_Opened_On": "2026-07-24", "Account_Status": None},
    {"id": "4", "Full_Name": "No Client Id", "ClientId": "",
     "Referrer_Client_Id": "YTW629", "Account_Opened_On": "2026-07-20", "Account_Status": None},
]


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


@pytest.fixture
def fake_zoho(monkeypatch):
    monkeypatch.setattr(reconcile, "fetch_opened_contacts", lambda since, **kw: list(ROWS))


def test_ingests_zerodha_openings_and_credits_the_referrer(seeded, fake_zoho):
    counts = reconcile.reconcile_conversions(tenant=seeded)
    assert counts["ingested"] == 2, counts
    assert Conversion.objects.filter(opener_zerodha_account_id="EUG979").exists()
    referral = Referral.objects.get(credited_referrer="YTW629")
    assert referral.conversion_status == "account_opened"


def test_skips_a_non_zerodha_account_in_the_same_module(seeded, fake_zoho):
    """AACK095261 is an AngelOne account. Ingesting it would invent a PIFS conversion and
    credit a PIFS referrer for an account PIFS never opened."""
    counts = reconcile.reconcile_conversions(tenant=seeded)
    assert counts["skipped_not_zerodha"] == 1
    assert not Conversion.objects.filter(opener_zerodha_account_id="AACK095261").exists()


def test_skips_a_row_with_no_client_id(seeded, fake_zoho):
    counts = reconcile.reconcile_conversions(tenant=seeded)
    assert counts["skipped_no_client_id"] == 1


def test_blank_referrer_credits_nobody(seeded, fake_zoho):
    """No referrer in Zoho ⇒ credit NO ONE. Never infer, never fall back (ADR-013/016)."""
    reconcile.reconcile_conversions(tenant=seeded)
    conv = Conversion.objects.get(opener_zerodha_account_id="UGF159")
    assert conv.referrer_client_id == ""


def test_is_idempotent_so_the_sweep_can_run_forever(seeded, fake_zoho):
    """The whole point is running every 15 min — a second pass must not duplicate."""
    reconcile.reconcile_conversions(tenant=seeded)
    before = Conversion.objects.count()
    reconcile.reconcile_conversions(tenant=seeded)
    assert Conversion.objects.count() == before


def test_a_replayed_row_is_already_ingested_NOT_a_failure(seeded, fake_zoho):
    """A re-seen row is the NORMAL outcome of a reconciler, and must not read as failure.

    Found live 2026-07-27: `DuplicateDelivery` was caught by the bare `except Exception`
    and counted as `failed`, so prod logged `ingested: 0, failed: 6` on EVERY 15-minute
    sweep — permanently. The damage is not the noise, it is the BLINDNESS: a genuinely
    broken seventh opening would have been invisible among six permanent failures, which is
    the exact condition this reconciler exists to end.

    The pre-existing idempotency test above passed throughout, because it only asserted that
    no duplicate rows appeared — it never looked at the counts. So this asserts the counts.
    """
    first = reconcile.reconcile_conversions(tenant=seeded)
    assert first["ingested"] >= 1 and first["failed"] == 0

    second = reconcile.reconcile_conversions(tenant=seeded)
    assert second["failed"] == 0, f"a replay must never report failure: {second}"
    assert second["ingested"] == 0, "nothing new to ingest on a replay"
    assert second["already_ingested"] == first["ingested"], (
        f"every previously-ingested row must be counted as already_ingested: {second}"
    )


def test_dry_run_reports_already_ingested_rather_than_pretending_work(seeded, fake_zoho):
    """A dry-run must describe what WOULD happen, not what we hope would.

    Counting every row as "would ingest" made a fully caught-up reconciler look like it had
    real work pending — which is what masked the counting bug above: the dry-run reported
    `ingested: 6, failed: 0` while every scheduled run reported `ingested: 0, failed: 6`.
    """
    reconcile.reconcile_conversions(tenant=seeded)
    dry = reconcile.reconcile_conversions(tenant=seeded, dry_run=True)
    assert dry["ingested"] == 0, f"nothing is left to ingest, so claim nothing: {dry}"
    assert dry["already_ingested"] >= 1
    assert dry["failed"] == 0


def test_stores_the_true_opening_date_not_the_import_date(seeded, fake_zoho):
    """ADR-017 — a backfilled conversion must land in the month it actually opened."""
    reconcile.reconcile_conversions(tenant=seeded)
    conv = Conversion.objects.get(opener_zerodha_account_id="EUG979")
    assert conv.account_opened_at is not None
    assert conv.account_opened_at.date().isoformat().startswith("2026-07-1")


def test_config_can_disable_it_without_a_deploy(seeded, fake_zoho):
    """CLAUDE.md §6d — behaviour is configuration, not code."""
    from apps.config.cascade import set_tenant

    set_tenant(reconcile.ENABLED_KEY, False, tenant_id=seeded.id)
    counts = reconcile.reconcile_conversions(tenant=seeded)
    assert counts == {"skipped": "disabled"}
    assert Conversion.objects.count() == 0


def test_a_zoho_outage_does_not_crash_the_sweep(seeded, monkeypatch):
    """A failing fetch must be reported, not raised — this runs on a scheduler."""
    def boom(since, **kw):
        raise RuntimeError("Zoho HTTP 401")

    monkeypatch.setattr(reconcile, "fetch_opened_contacts", boom)
    counts = reconcile.reconcile_conversions(tenant=seeded)
    assert counts["failed"] == 1
    assert counts["ingested"] == 0
