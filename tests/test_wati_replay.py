"""T-048 — Wati webhook replay protection + stale-status guard.

WHY THESE TESTS EXIST
---------------------
The Zoho webhook is sealed (HMAC + freshness + one-time nonce). The Wati webhook cannot
be: Wati's sender is fixed and carries only a static `?token=` query param, so a captured
request stays valid forever. These tests pin the two protections that close that gap:

  1. REPLAY — a second POST identical to an already-accepted webhook changes nothing.
  2. STALE STATUS — anything arriving later can never walk a message (or a session
     window) BACKWARDS from a state it already reached.

Ground truth for payload shapes: this repo's existing Wati tests (`tests/test_followups.py`
inbound cases) + the verified key map in `Wati-GoRefer/Wati-Integration-Contract.md` §10.
Wati message payloads carry `id`, `waId`, `owner`, `timestamp`/`created`, `statusString` —
no signature and no nonce, which is exactly why dedupe has to key on Wati's own `id`.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.config.cascade import set_tenant
from apps.followups.models import FollowupRule, FollowupWindow, ScheduledFollowup
from apps.integrations.models import Notification, WatiWebhookReceipt
from apps.integrations.wati import status as st
from apps.integrations.wati import tasks
from apps.tenants.resolve import get_bootstrap_tenant

MOBILE = "917000000501"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def tenant(seeded):
    return get_bootstrap_tenant()


@pytest.fixture
def enabled(tenant):
    set_tenant("followups_enabled", True, tenant_id=tenant.id)
    return tenant


def _rule(tenant, step_key="nudge_15m"):
    return FollowupRule.objects.create(
        tenant=tenant, step_key=step_key, offset_minutes=15,
        body_en="Hi!", body_hi="", enabled=True, order=100,
    )


def _post(payload, token="testkey123"):
    return Client().post(
        f"/api/wati/inbound?token={token}", data=payload, content_type="application/json"
    )


# --- 1. REPLAY ---------------------------------------------------------------

def test_replayed_inbound_webhook_changes_nothing(enabled, settings):
    """The DoD case: the SAME valid-auth payload posted twice must not act twice.

    Without the guard the second POST re-stamps the window and (24h on) re-fires the
    whole nudge cadence — a message-spam primitive for anyone holding one captured URL.
    """
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    payload = {"id": "wamid.TEST-REPLAY-1", "waId": MOBILE, "text": "hi", "owner": False}

    first = _post(payload)
    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    window = FollowupWindow.objects.get(mobile=MOBILE)
    stamped_at = window.last_inbound_at
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1

    second = _post(payload)  # byte-identical replay
    assert second.status_code == 200
    assert second.json()["reason"] == "duplicate"
    assert second.json()["stamped"] is False

    window.refresh_from_db()
    assert window.last_inbound_at == stamped_at                          # no re-stamp
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1  # no re-enqueue
    assert WatiWebhookReceipt.objects.filter(endpoint="inbound").count() == 1


def test_replay_guard_keys_on_wati_message_id_not_the_bytes(enabled, settings):
    """Two payloads with the same Wati `id` are ONE event even if other fields differ.

    Wati re-delivers with the same message id but e.g. a different `senderName`; a
    bytes-only digest would wrongly treat that as a new event.
    """
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    assert _post({"id": "wamid.SAME", "waId": MOBILE, "senderName": "A"}).json()["status"] == "ok"
    again = _post({"id": "wamid.SAME", "waId": MOBILE, "senderName": "B (retry)"})
    assert again.json()["reason"] == "duplicate"
    assert ScheduledFollowup.objects.filter(mobile=MOBILE).count() == 1


def test_distinct_wati_messages_are_not_deduped(enabled, settings):
    """The guard must not swallow genuine traffic: different ids both get through."""
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    assert _post({"id": "wamid.A", "waId": MOBILE}).json()["status"] == "ok"
    second = _post({"id": "wamid.B", "waId": MOBILE})
    assert second.json()["status"] == "ok"
    assert second.json()["stamped"] is True
    assert WatiWebhookReceipt.objects.filter(endpoint="inbound").count() == 2


def test_payload_without_an_id_falls_back_to_the_body_digest(enabled, settings):
    """No id in the body → a byte-identical replay is still refused."""
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    payload = {"waId": MOBILE, "text": "no id here"}
    assert _post(payload).json()["status"] == "ok"
    assert _post(payload).json()["reason"] == "duplicate"
    assert WatiWebhookReceipt.objects.get(endpoint="inbound").event_key.startswith("sha256=")


def test_unauthenticated_replay_burns_nothing(enabled, settings):
    """A wrong token is rejected BEFORE the claim, so an unauthenticated flood cannot
    fill the table — nor pre-burn the key of a real message that has not arrived yet."""
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    payload = {"id": "wamid.PREBURN", "waId": MOBILE}
    assert _post(payload, token="WRONG").status_code == 401
    assert WatiWebhookReceipt.objects.count() == 0
    assert _post(payload).json()["status"] == "ok"      # the real delivery still works


def test_outbound_event_does_not_burn_a_receipt(enabled, settings):
    """An OUTBOUND event changes no state, so it must not consume the event key —
    otherwise a customer inbound sharing that id would be silently swallowed."""
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    assert _post({"id": "wamid.OUT", "waId": MOBILE, "owner": True}).json()["reason"] == "outbound"
    assert WatiWebhookReceipt.objects.count() == 0


def test_assisted_webhook_replay_is_refused(enabled, settings):
    """The assisted-capture endpoint (lead-creating) refuses a replayed delivery."""
    from apps.referrals.models import Lead

    settings.WATI_WEBHOOK_KEY = "testkey123"
    payload = {"id": "wamid.ASSIST-1", "client_id": "RJ4521",
               "name": "Test Prospect", "mobile": "9876500011"}
    first = Client().post("/api/wati/webhook?token=testkey123",
                          data=payload, content_type="application/json")
    assert first.status_code == 200
    before = Lead.objects.count()

    second = Client().post("/api/wati/webhook?token=testkey123",
                           data=payload, content_type="application/json")
    assert second.status_code == 409
    assert Lead.objects.count() == before


def test_purge_drops_only_expired_receipts(db):
    from apps.integrations.wati.replay import RECEIPT_RETENTION_DAYS, purge_expired_receipts

    fresh = WatiWebhookReceipt.objects.create(endpoint="inbound", event_key="id=fresh")
    old = WatiWebhookReceipt.objects.create(endpoint="inbound", event_key="id=old")
    WatiWebhookReceipt.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=RECEIPT_RETENTION_DAYS + 1)
    )
    assert purge_expired_receipts() == 1
    assert list(WatiWebhookReceipt.objects.values_list("pk", flat=True)) == [fresh.pk]


def test_receipt_purge_is_registered_on_a_schedule():
    """An unbounded receipt table is its own defect — the purge must actually be wired."""
    from apps.integrations.schedules import INTEGRATION_SCHEDULES

    path, minutes = INTEGRATION_SCHEDULES["wati_purge_webhook_receipts"]
    assert path == "apps.integrations.wati.replay.purge_expired_receipts"
    assert minutes > 0


# --- 2. STALE STATUS ---------------------------------------------------------

def test_replayed_older_inbound_cannot_rewind_the_session_window(enabled, settings):
    """END-TO-END through the webhook: an OLDER inbound never moves the window back.

    Rewinding is not cosmetic — `window_is_open` is computed from `last_inbound_at`, so
    pushing it into the past marks a genuinely open 24h window CLOSED and downgrades
    every in-window session send to the closed-window path.
    """
    settings.WATI_WEBHOOK_KEY = "testkey123"
    _rule(enabled)
    now = timezone.now()
    newer_ts = int((now - timedelta(minutes=5)).timestamp())
    older_ts = int((now - timedelta(hours=10)).timestamp())

    assert _post({"id": "wamid.NEW", "waId": MOBILE, "timestamp": newer_ts}).json()["status"] == "ok"
    window = FollowupWindow.objects.get(mobile=MOBILE)
    newest = window.last_inbound_at

    # A DIFFERENT message id, so the replay guard lets it through — the ORDERING guard
    # is what has to hold here.
    out = _post({"id": "wamid.OLD", "waId": MOBILE, "timestamp": older_ts}).json()
    assert out["status"] == "ok" and out["opened_fresh"] is False
    window.refresh_from_db()
    assert window.last_inbound_at == newest


def test_replayed_older_status_cannot_overwrite_a_newer_terminal_status(enabled):
    """DELIVERED first, then a stale SENT/FAILED re-read — final state stays DELIVERED.

    SCOPE NOTE (verified, not assumed): Wati has NO delivery-status webhook. The
    integration contract says so outright and `wati/tasks.py` repeats it; the only
    status-applying code path is the send + the reconcile sweep re-reading `getMessages`.
    That sweep is the real stale-status surface, and both paths now funnel through the
    single `_finalize` guard exercised here.
    """
    n = Notification.objects.create(
        tenant=enabled, recipient_mobile=MOBILE, recipient_role="prospect",
        template="t", status=st.STATUS_ACCEPTED, idempotency_key="k-stale-1",
    )
    assert tasks._finalize(n, st.STATUS_DELIVERED, meta_error_code=None) is True
    n.refresh_from_db()
    assert n.status == st.STATUS_DELIVERED

    assert tasks._finalize(n, st.STATUS_SENT, meta_error_code=None) is False
    n.refresh_from_db()
    assert n.status == st.STATUS_DELIVERED

    # Nor may a late FAILED flip a recorded delivery into a failure.
    assert tasks._finalize(n, st.STATUS_FAILED, meta_error_code=131049) is False
    n.refresh_from_db()
    assert n.status == st.STATUS_DELIVERED
    assert not n.meta_error_code

    # Forward progress still works: read supersedes delivered.
    assert tasks._finalize(n, st.STATUS_READ, meta_error_code=None) is True
    n.refresh_from_db()
    assert n.status == st.STATUS_READ


def test_reconcile_sweep_still_finalizes_a_genuinely_newer_status(enabled, monkeypatch):
    """The guard must not break the sweep's real job: ACCEPTED → DELIVERED still lands."""
    n = Notification.objects.create(
        tenant=enabled, recipient_mobile=MOBILE, recipient_role="prospect",
        template="t", status=st.STATUS_ACCEPTED, idempotency_key="k-live-1",
    )
    Notification.objects.filter(pk=n.pk).update(
        updated_at=timezone.now() - timedelta(hours=1)
    )

    class _Adapter:
        def get_message_status(self, **kwargs):
            class _R:
                status = st.STATUS_DELIVERED
                meta_error_code = None
            return _R()

    monkeypatch.setattr(tasks, "_adapter_for_reconcile", lambda _n: _Adapter())
    out = tasks.reconcile_pending_deliveries()
    assert out["finalized"] == 1
    n.refresh_from_db()
    assert n.status == st.STATUS_DELIVERED


# --- 3. status ordering rules ------------------------------------------------

@pytest.mark.parametrize("current,incoming,expected", [
    ("accepted", "delivered", True),
    ("accepted", "sent", True),
    ("sent", "delivered", True),
    ("delivered", "read", True),
    ("delivered", "sent", False),
    ("delivered", "accepted", False),
    ("delivered", "failed", False),
    ("failed", "delivered", False),
    ("read", "delivered", False),
    ("read", "read", False),
    ("accepted", "unknown-status", False),
])
def test_supersedes_rules(current, incoming, expected):
    from apps.integrations.delivery_status import supersedes

    assert supersedes(current, incoming) is expected
