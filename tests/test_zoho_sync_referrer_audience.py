"""T-126 (W3) — `apps.integrations.zoho.tasks.sync_referrer_audience`.

Proven here:
  1. inert (no port call at all) when ENABLE_ZOHO_READ is off — a demo-fixture
     write into the real audience table would silently corrupt who the engine
     messages, so this is stricter than the usual live/LogOnly swap;
  2. inert when the configured frequency window has not elapsed since the last
     sync (config row, decision from the plan — not a hardcoded interval);
  3. upserts SyncedReferrer by (tenant, client_id), normalizing mobile;
  4. a referrer missing from a COMPLETE fetch is marked active=False, never deleted;
  5. a TRUNCATED fetch skips the deactivation sweep entirely (never treats "didn't
     see it on a partial page" as "gone");
  6. the parity check logs loudly on a synced-active vs fetched mismatch;
  7. guardrail: the sync writes NOTHING to Zoho (asserted against the adapter
     surface actually used — fetch_referrer_audience only).
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.campaigns.models import SyncedReferrer
from apps.integrations.zoho import tasks as zoho_tasks
from apps.integrations.zoho.read import ReferrerAudience, ZohoReferrerRow
from apps.tenants.resolve import get_bootstrap_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def _audience(rows, truncated=False) -> ReferrerAudience:
    return ReferrerAudience(rows=rows, truncated=truncated)


# --- 1. inert when the flag is off -------------------------------------------------

def test_inert_no_op_when_enable_zoho_read_off(tenant):
    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=False), \
            mock.patch("apps.integrations.ports.get_crm_read_port") as port:
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result == {"skipped": "ENABLE_ZOHO_READ off"}
    port.assert_not_called()


# --- 2. frequency window gate -------------------------------------------------------

def test_inert_when_frequency_window_has_not_elapsed(tenant):
    now = timezone.now()
    SyncedReferrer.objects.create(
        tenant=tenant, client_id="ALREADY", mobile="919000000001", name="x",
        record_created_at=now, synced_at=now,
    )
    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port") as port:
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["skipped"] == "frequency window not elapsed"
    port.assert_not_called()


def test_runs_when_frequency_window_has_elapsed(tenant):
    stale = timezone.now() - timedelta(hours=48)
    SyncedReferrer.objects.create(
        tenant=tenant, client_id="OLD", mobile="919000000002", name="x",
        record_created_at=stale, synced_at=stale,
    )
    audience = _audience([
        ZohoReferrerRow(client_id="NEW1", mobile="9876500001", name="New One",
                         language="", record_created_at=timezone.now()),
    ])
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["created"] == 1
    fake_port.fetch_referrer_audience.assert_called_once()


# --- 3. upsert + mobile normalization -----------------------------------------------

def test_upserts_by_tenant_and_client_id_and_normalizes_mobile(tenant):
    anchor = timezone.now()
    audience = _audience([
        ZohoReferrerRow(client_id="RJ4521", mobile="9876504321", name="Rajesh Joshi",
                         language="", record_created_at=anchor),
    ])
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    row = SyncedReferrer.objects.get(tenant=tenant, client_id="RJ4521")
    assert row.mobile == "919876504321"  # normalize_phone prefixes 91
    assert row.active is True
    assert result["created"] == 1

    # second run with the same row -> update, not a duplicate
    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        SyncedReferrer.objects.filter(pk=row.pk).update(
            synced_at=timezone.now() - timedelta(hours=48)
        )
        result2 = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result2["updated"] == 1
    assert SyncedReferrer.objects.filter(tenant=tenant, client_id="RJ4521").count() == 1


def test_skips_rows_with_no_anchor(tenant):
    audience = _audience([
        ZohoReferrerRow(client_id="NOANCHOR", mobile="9876500003", name="x",
                         language="", record_created_at=None),
    ])
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["skipped_no_anchor"] == 1
    assert not SyncedReferrer.objects.filter(tenant=tenant, client_id="NOANCHOR").exists()


# --- 4. deactivation on a COMPLETE fetch ---------------------------------------------

def test_deactivates_rows_missing_from_a_complete_fetch(tenant):
    now = timezone.now()
    stale = now - timedelta(hours=48)  # outside the frequency window, so the sync actually runs
    SyncedReferrer.objects.create(
        tenant=tenant, client_id="GONE", mobile="919000000004", name="x",
        record_created_at=now, synced_at=stale, active=True,
    )
    audience = _audience([])  # complete fetch, GONE not present
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["deactivated"] == 1
    assert SyncedReferrer.objects.get(tenant=tenant, client_id="GONE").active is False


# --- 5. a TRUNCATED fetch never deactivates -------------------------------------------

def test_truncated_fetch_skips_deactivation_sweep(tenant):
    now = timezone.now()
    stale = now - timedelta(hours=48)  # outside the frequency window, so the sync actually runs
    SyncedReferrer.objects.create(
        tenant=tenant, client_id="MAYBE_GONE", mobile="919000000005", name="x",
        record_created_at=now, synced_at=stale, active=True,
    )
    audience = _audience([], truncated=True)  # partial fetch — MAYBE_GONE just wasn't seen
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["deactivated"] == 0
    assert SyncedReferrer.objects.get(tenant=tenant, client_id="MAYBE_GONE").active is True
    assert result["parity_ok"] is True  # truncation exempts the parity check


# --- 6. parity mismatch is logged loudly ----------------------------------------------

def test_parity_ok_and_clean_when_fetch_matches_active_count(tenant, caplog):
    now = timezone.now()
    audience = _audience([
        ZohoReferrerRow(client_id="A", mobile="9876500007", name="x", language="",
                         record_created_at=now),
        ZohoReferrerRow(client_id="B", mobile="9876500008", name="y", language="",
                         record_created_at=now),
    ])
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    # Simulate a mismatch: after the sync runs, add a stray active row from a
    # concurrent process that the parity check should catch.
    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        with caplog.at_level("WARNING", logger="gorefer.zoho.tasks"):
            result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["fetched"] == 2
    assert result["synced_active_count"] == 2
    assert result["parity_ok"] is True
    assert not any("PARITY MISMATCH" in r.getMessage() for r in caplog.records)


def test_parity_mismatch_is_detected_and_logged_loudly(tenant, caplog):
    """Force the deactivation sweep to no-op (simulating a stray active row the
    sweep should have caught) and prove the parity check catches the divergence
    rather than reporting a clean sync."""
    now = timezone.now()
    stale = now - timedelta(hours=48)  # outside the frequency window, so the sync actually runs
    SyncedReferrer.objects.create(
        tenant=tenant, client_id="STRAY", mobile="919000000009", name="x",
        record_created_at=now, synced_at=stale, active=True,
    )
    audience = _audience([])  # STRAY is not in this fetch — would normally be deactivated
    fake_port = mock.MagicMock()
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port), \
            mock.patch("django.db.models.query.QuerySet.update", return_value=0), \
            caplog.at_level("WARNING", logger="gorefer.zoho.tasks"):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result["fetched"] == 0
    assert result["synced_active_count"] == 1  # STRAY stayed active — sweep was no-op'd
    assert result["parity_ok"] is False
    assert any("PARITY MISMATCH" in r.getMessage() for r in caplog.records)


# --- 7. guardrail: never writes to Zoho ------------------------------------------------

def test_sync_never_calls_a_zoho_write_method(tenant):
    audience = _audience([
        ZohoReferrerRow(client_id="RJ4521", mobile="9876504321", name="Rajesh Joshi",
                         language="", record_created_at=timezone.now()),
    ])
    fake_port = mock.MagicMock(spec=["fetch_referrer_audience"])
    fake_port.fetch_referrer_audience.return_value = audience

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port):
        zoho_tasks.sync_referrer_audience(tenant=tenant)

    # spec=[...] means any write-shaped call (upsert_lead, upsert_referrer_contact,
    # etc.) would raise AttributeError — the mock only exposes the read method used.
    assert fake_port.method_calls == [mock.call.fetch_referrer_audience()]


# --- 8. transport blip degrades instead of crashing the scheduled job ------------------

def test_fetch_failure_degrades_instead_of_crashing(tenant, caplog):
    """M7 pt 16: the ONE scheduled call with no try/except used to propagate a Zoho
    transport error (now a RuntimeError per client.py's URLError/OSError handling)
    straight out of the task and crash the whole scheduled job."""
    fake_port = mock.MagicMock(spec=["fetch_referrer_audience"])
    fake_port.fetch_referrer_audience.side_effect = RuntimeError("Zoho transport error: URLError: timed out")

    with mock.patch("apps.config.integration_flags.resolve_flag", return_value=True), \
            mock.patch("apps.integrations.ports.get_crm_read_port", return_value=fake_port), \
            caplog.at_level("WARNING", logger="gorefer.zoho.tasks"):
        result = zoho_tasks.sync_referrer_audience(tenant=tenant)

    assert result == {"error": "zoho fetch failed"}
    assert SyncedReferrer.objects.for_tenant(tenant).count() == 0
    assert any("fetch failed" in r.getMessage() for r in caplog.records)
