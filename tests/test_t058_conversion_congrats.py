"""T-058 — referrer conversion-congrats (P-01, Gap 5 closure).

Hooked once, downstream of `apps.integrations.zoho.ingest` applying an
`account_opened` conversion. All run offline (ENABLE_ZOHO_READ/ENABLE_WATI_SEND
false -> log-only adapters; the webhook path is exercised with fixture payloads,
matching the existing M6 ingest test style in test_zoho.py).
"""
import json

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.config.cascade import set_tenant
from apps.config.preferences import (
    REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN,
)
from apps.followups.models import FollowupWindow
from apps.integrations.models import Conversion, Notification
from apps.referrals.models import Referral
from apps.tenants.resolve import get_bootstrap_tenant

WEBHOOK = "/api/zoho/status-webhook"
KEY_HEADER = {"HTTP_X_ZOHO_WEBHOOK_KEY": "testkey"}


def _post(client, payload, **extra):
    return client.post(WEBHOOK, data=json.dumps(payload), content_type="application/json", **extra)


def _seed(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")


# --- template leg dormant by default ---------------------------------------

@pytest.mark.django_db(transaction=True)
def test_congrats_dormant_when_no_template_configured(settings):
    """Window closed (default) + no template override -> DoD default: feature ships
    dormant on the template leg. Notification recorded as skipped, never crashes."""
    _seed(settings)
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    r = _post(c, {
        "event_id": "t058-e1", "opener_zerodha_account_id": "ZA9058",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.status_code == 200 and r.json()["applied"] is True

    conv = Conversion.objects.get(opener_zerodha_account_id="ZA9058")
    n = Notification.objects.get(idempotency_key=f"referrer_congrats:{conv.pk}")
    assert n.recipient_role == "referrer"
    assert n.status == "skipped"
    assert n.skip_reason == "no template configured"


# --- template leg, once configured ------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_congrats_sent_via_template_when_window_closed_and_configured(settings):
    _seed(settings)
    tenant = get_bootstrap_tenant()
    set_tenant(
        REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN, "gr_referrer_congrats_en_test",
        tenant_id=tenant.id,
    )
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    r = _post(c, {
        "event_id": "t058-e2", "opener_zerodha_account_id": "ZA9059",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.status_code == 200 and r.json()["applied"] is True

    conv = Conversion.objects.get(opener_zerodha_account_id="ZA9059")
    n = Notification.objects.get(idempotency_key=f"referrer_congrats:{conv.pk}")
    assert n.status == "accepted"
    assert n.template == "gr_referrer_congrats_en_test"
    # Mobile resolved via the CRM read port (demo fixture), never guessed.
    assert n.recipient_mobile == "919876504321"


# --- session leg, window open ------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_congrats_session_when_referrer_window_open(settings):
    _seed(settings)
    tenant = get_bootstrap_tenant()
    FollowupWindow.objects.create(
        tenant=tenant, mobile="919876504321", last_inbound_at=timezone.now()
    )
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    r = _post(c, {
        "event_id": "t058-e3", "opener_zerodha_account_id": "ZA9060",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.status_code == 200 and r.json()["applied"] is True

    conv = Conversion.objects.get(opener_zerodha_account_id="ZA9060")
    n = Notification.objects.get(idempotency_key=f"referrer_congrats:{conv.pk}")
    assert n.status == "accepted"
    assert n.template == "session:referrer_conversion_congrats"


# --- unresolvable mobile: observable skip, never a guess ---------------------

@pytest.mark.django_db(transaction=True)
def test_congrats_skips_when_referrer_mobile_unknown(settings):
    """No Zoho Contact fixture for this client_id -> unmatched -> no mobile. Must
    skip, never guess (BR-010)."""
    _seed(settings)
    c = Client()
    r = _post(c, {
        "event_id": "t058-e4", "opener_zerodha_account_id": "ZA9061",
        "referrer_client_id": "NOFIX01", "status": "Account Opened",
        "account_opened_at": "2026-04-01T10:00:00",
    }, **KEY_HEADER)
    assert r.json()["applied"] is True

    conv = Conversion.objects.get(opener_zerodha_account_id="ZA9061")
    n = Notification.objects.get(idempotency_key=f"referrer_congrats:{conv.pk}")
    assert n.status == "skipped"
    assert n.skip_reason == "referrer mobile unknown"


# --- idempotent across re-ingests / reconciler sweeps -----------------------

@pytest.mark.django_db(transaction=True)
def test_congrats_idempotent_across_double_ingest(settings):
    """Two DIFFERENT Zoho events landing on the SAME conversion (e.g. a reconciler
    sweep re-observing an already-applied account_opened) must fire AT MOST ONE
    congrats — the Notification's unique idempotency_key is keyed on the conversion,
    not the event id."""
    _seed(settings)
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    payload_base = {
        "opener_zerodha_account_id": "ZA9062",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }
    r1 = _post(c, {"event_id": "t058-e5a", **payload_base}, **KEY_HEADER)
    assert r1.json()["applied"] is True
    r2 = _post(c, {"event_id": "t058-e5b", **payload_base}, **KEY_HEADER)
    assert r2.json()["applied"] is True  # different event id -> re-applies (not a dupe at ingest level)

    conv = Conversion.objects.get(opener_zerodha_account_id="ZA9062")
    assert Notification.objects.filter(idempotency_key=f"referrer_congrats:{conv.pk}").count() == 1


# --- converted-suppression must NOT block this send (it IS the converted case) ---

@pytest.mark.django_db(transaction=True)
def test_congrats_not_suppressed_by_followup_converted_gate(settings):
    """`apps.followups.services.has_converted` / the converted-suppression switch stop
    the NUDGE cadence, never this one-time congrats — the congrats send path does not
    consult that gate at all, and the followup engine's own suppression must remain
    scoped to ScheduledFollowup sends only."""
    _seed(settings)
    tenant = get_bootstrap_tenant()
    FollowupWindow.objects.create(
        tenant=tenant, mobile="919876504321", last_inbound_at=timezone.now()
    )
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    r = _post(c, {
        "event_id": "t058-e6", "opener_zerodha_account_id": "ZA9063",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.json()["applied"] is True

    # The referral this conversion just credited IS converted — has_converted() would
    # suppress a NUDGE for this contact, but the congrats send above already succeeded.
    referral = Referral.objects.get(referral_identity__client_id="RJ4521")
    assert referral.conversion_status == "account_opened"

    conv = Conversion.objects.get(opener_zerodha_account_id="ZA9063")
    n = Notification.objects.get(idempotency_key=f"referrer_congrats:{conv.pk}")
    assert n.status == "accepted"


# --- ingest write path gains no new failure mode -----------------------------

@pytest.mark.django_db(transaction=True)
def test_ingest_survives_congrats_enqueue_failure(settings, monkeypatch):
    """A broken congrats enqueue must never block or roll back the conversion write."""
    from apps.integrations import services as integ_services

    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "apps.integrations.congrats.enqueue_referrer_congrats", _boom, raising=True
    )
    _seed(settings)
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    r = _post(c, {
        "event_id": "t058-e7", "opener_zerodha_account_id": "ZA9064",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.status_code == 200 and r.json()["applied"] is True
    assert Conversion.objects.filter(opener_zerodha_account_id="ZA9064").exists()
    del integ_services  # imported only to document which module owns the guard
