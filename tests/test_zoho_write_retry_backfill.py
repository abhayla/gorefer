"""Zoho WRITE retry + backfill (async queue) — the remaining WRITE gate.

Before this, a Zoho upsert failure logged and left the lead local-only forever:
nothing was technically dropped, but Ashok would never see the lead in the CRM —
silent loss from the operator's point of view. These tests prove the closure:

  1. capture is async: the submit never waits on Zoho (enqueued on_commit);
  2. outage -> lead saved + `pending` -> retried -> `synced` once Zoho recovers;
  3. attempts exhausted -> stays `failed`, surfaced in the admin, ZERO data loss;
  4. replay/retry never twins (upsert dedups on the bare-10-digit mobile);
  5. PII stays out of the immutable event log; capture-first preserved;
  6. the WRITE leg NEVER sets account status (guardrail #2).

Tests run in sync mode (Q_CLUSTER sync=True — the dev/CI/demo default), so the
enqueued task executes inline and the whole flow is exercised offline.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.integrations.zoho.adapter import LeadWriteResult
from apps.integrations.zoho.tasks import (
    MAX_SYNC_ATTEMPTS,
    backfill_unsynced,
    upsert_lead_task,
)
from apps.referrals.models import Lead


def _capture(client, *, client_id="RJ4521", mobile="9876543210", name="Rahul Sharma"):
    """Drive the real capture-first endpoint (the landing form's path)."""
    client.get(f"/r/{client_id}", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    return client.post(
        "/api/leads/",
        data={
            "client_id": client_id, "name": name, "mobile": mobile,
            "email": "rahul@example.com", "city": "Prayagraj", "consent": True,
        },
        content_type="application/json",
    )


class _OutageAdapter:
    """Zoho is down: every upsert raises."""

    def __init__(self):
        self.calls = 0

    def upsert_lead(self, *, payload: dict, gorefer_reference: str):
        self.calls += 1
        raise RuntimeError("Zoho HTTP 503: service unavailable")


class _RecoveredAdapter:
    """Zoho is back: upserts succeed, deduping server-side on the bare mobile."""

    def __init__(self):
        self.calls = []
        self._seen: dict[str, str] = {}

    def upsert_lead(self, *, payload: dict, gorefer_reference: str):
        from apps.integrations.zoho.adapter import build_lead_record

        record = build_lead_record(payload=payload, gorefer_reference=gorefer_reference)
        self.calls.append(record)
        mobile = record["Mobile"]
        if mobile in self._seen:
            return LeadWriteResult(
                zoho_lead_id=self._seen[mobile], gorefer_reference=gorefer_reference,
                action="update",
            )
        zid = f"zoho-{len(self._seen) + 1}"
        self._seen[mobile] = zid
        return LeadWriteResult(
            zoho_lead_id=zid, gorefer_reference=gorefer_reference, action="insert"
        )


# --- 1. async capture -------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_capture_enqueues_the_upsert_and_does_not_write_inline():
    """The submit must not wait on Zoho — the write is enqueued on_commit."""
    call_command("seed_program")
    with mock.patch("apps.integrations.services.enqueue_lead_upsert") as enq:
        resp = _capture(Client())

    assert resp.status_code in (200, 201)
    lead = Lead.objects.get(prospect__mobile="919876543210")
    enq.assert_called_once_with(lead.pk)
    # Nothing ran yet => the lead is parked pending for the task/sweep.
    assert lead.zoho_sync_status == Lead.SYNC_PENDING


@pytest.mark.django_db(transaction=True)
def test_demo_flag_off_syncs_via_log_only_adapter_no_network():
    """Flag off (demo default): the task still runs end-to-end, log-only, no network."""
    call_command("seed_program")
    resp = _capture(Client())
    assert resp.status_code in (200, 201)

    lead = Lead.objects.get(prospect__mobile="919876543210")
    assert lead.zoho_sync_status == Lead.SYNC_SYNCED
    assert lead.zoho_lead_id == "demo-zoho-9876543210"  # bare-10-digit key
    assert lead.gorefer_reference == f"GR-{lead.referral_id}"


# --- 2. outage -> pending -> recovery -> synced -----------------------------------

@pytest.mark.django_db(transaction=True)
def test_outage_keeps_lead_pending_then_syncs_on_recovery():
    """THE gate: a Zoho outage must never strand a lead. It retries to synced."""
    call_command("seed_program")

    # --- Zoho is down during capture ---
    outage = _OutageAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=outage):
        resp = _capture(Client())

    assert resp.status_code in (200, 201), "capture-first: the submit must still succeed"
    lead = Lead.objects.get(prospect__mobile="919876543210")
    assert lead.zoho_sync_status == Lead.SYNC_PENDING, "outage must leave it retryable"
    assert lead.zoho_sync_attempts == 1
    assert "503" in lead.zoho_last_error
    assert lead.zoho_lead_id is None  # never reached Zoho

    # --- Zoho recovers; the backfill sweep re-enqueues it ---
    recovered = _RecoveredAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=recovered):
        enqueued = backfill_unsynced()

    assert enqueued == 1
    lead.refresh_from_db()
    assert lead.zoho_sync_status == Lead.SYNC_SYNCED, "recovery must heal the stranded lead"
    assert lead.zoho_lead_id == "zoho-1"
    assert lead.zoho_last_error == ""
    assert lead.zoho_synced_at is not None


@pytest.mark.django_db(transaction=True)
def test_max_attempts_leaves_lead_failed_and_visible_with_no_data_loss():
    """Exhausted retries must park the lead `failed` + VISIBLE — never silent, never lost."""
    call_command("seed_program")
    outage = _OutageAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=outage):
        _capture(Client())
        lead = Lead.objects.get(prospect__mobile="919876543210")
        # Burn through the remaining retry budget.
        for _ in range(MAX_SYNC_ATTEMPTS - 1):
            upsert_lead_task(lead.pk)

    lead.refresh_from_db()
    assert lead.zoho_sync_attempts == MAX_SYNC_ATTEMPTS
    assert lead.zoho_sync_status == Lead.SYNC_FAILED
    # ZERO data loss: the lead + its PII are intact locally for a human to work.
    assert lead.prospect.name == "Rahul Sharma"
    assert lead.prospect.mobile == "919876543210"
    assert Lead.objects.filter(pk=lead.pk).exists()

    # Exhausted leads are NOT re-enqueued by the sweep — they need a human.
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=outage):
        assert backfill_unsynced() == 0

    # ...and they are visible via the admin's "needs attention" filter.
    from apps.referrals.admin import UnsyncedZohoFilter

    f = UnsyncedZohoFilter(None, {"zoho_unsynced": ["needs_attention"]}, Lead, None)
    assert lead.pk in set(f.queryset(None, Lead.objects.all()).values_list("id", flat=True))


# --- 3. idempotency on retry ------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_retry_never_twins_the_zoho_lead():
    """Replaying the task can only UPDATE the same Zoho lead — never create a twin."""
    call_command("seed_program")
    recovered = _RecoveredAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=recovered):
        _capture(Client())
        lead = Lead.objects.get(prospect__mobile="919876543210")
        first_id = lead.zoho_lead_id
        # Force a replay of an already-synced lead (duplicate enqueue / at-least-once).
        lead.zoho_sync_status = Lead.SYNC_PENDING
        lead.save(update_fields=["zoho_sync_status"])
        upsert_lead_task(lead.pk)

    lead.refresh_from_db()
    assert lead.zoho_lead_id == first_id, "retry twinned the Zoho lead"
    assert {c["Mobile"] for c in recovered.calls} == {"9876543210"}
    assert len(recovered._seen) == 1, "more than one Zoho record for one person"


@pytest.mark.django_db(transaction=True)
def test_already_synced_lead_is_not_rewritten():
    """A duplicate enqueue for a synced lead is a no-op — no redundant Zoho write."""
    call_command("seed_program")
    recovered = _RecoveredAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=recovered):
        _capture(Client())
        lead = Lead.objects.get(prospect__mobile="919876543210")
        before = len(recovered.calls)
        assert upsert_lead_task(lead.pk) == "noop"
    assert len(recovered.calls) == before


@pytest.mark.django_db(transaction=True)
def test_backfill_is_bounded_and_oldest_first():
    """The sweep drains steadily (bounded) and works the earliest-stranded lead first."""
    from apps.integrations.zoho import tasks as zt

    call_command("seed_program")
    outage = _OutageAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=outage):
        for i in range(3):
            _capture(Client(), mobile=f"98765432{i:02d}")

    stranded = list(Lead.objects.order_by("created_at").values_list("id", flat=True))
    enqueued = []
    with mock.patch.object(zt, "BACKFILL_BATCH_SIZE", 2), \
         mock.patch("apps.integrations.zoho.tasks.enqueue_upsert", side_effect=enqueued.append):
        assert backfill_unsynced() == 2  # bounded, not all 3
    assert enqueued == stranded[:2], "sweep must work oldest-first"


# --- 4. guardrails ----------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_sync_state_never_reaches_the_event_log_and_carries_no_pii():
    """Sync state lives on the erasable Lead; the immutable event log stays PII-free."""
    call_command("seed_program")
    outage = _OutageAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=outage):
        _capture(Client())

    blob = json.dumps([e.metadata for e in Event.objects.all()])
    for leaked in ("Rahul", "9876543210", "919876543210", "rahul@example.com", "Prayagraj"):
        assert leaked not in blob, f"PII {leaked!r} leaked into the event log"
    # ...and no sync bookkeeping crept into the immutable log either.
    for k in ("zoho_sync_status", "zoho_last_error", "503"):
        assert k not in blob


@pytest.mark.django_db(transaction=True)
def test_write_leg_never_sets_account_status():
    """Guardrail #2: the WRITE leg mirrors OUT. Account status comes only from Zoho in."""
    call_command("seed_program")
    recovered = _RecoveredAdapter()
    with mock.patch("apps.integrations.zoho.tasks.get_zoho_adapter", return_value=recovered):
        _capture(Client())

    lead = Lead.objects.get(prospect__mobile="919876543210")
    assert lead.zoho_sync_status == Lead.SYNC_SYNCED  # our write landed...
    assert lead.status == "new"                       # ...but status is untouched
    assert lead.account_opened_at is None
    assert not Event.objects.filter(event_type="account_opened").exists()
