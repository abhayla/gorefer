"""B4 — assisted-referral webhook POST /api/wati/webhook (ADR-033).

The Wati "Refer directly" flow posts a prospect's Name + Mobile (Email optional)
with the referrer's client_id; GoRefer creates ONE Zoho lead (behind
ENABLE_ZOHO_WRITE; log-only when off), attributed to the referrer, with a DPDP
consent flag, deduped, never storing a password, PII out of the event log.

Guardrails asserted (S2-03 §11 / S2-04 §B4).
"""
import json

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.referrals.models import Lead, Prospect, ReferralIdentity

WEBHOOK = "/api/wati/webhook"
KEY_HEADER = {"HTTP_X_WATI_WEBHOOK_KEY": "testkey"}


@pytest.fixture
def seeded(db, settings):
    settings.WATI_WEBHOOK_KEY = "testkey"
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _post(client, payload, **extra):
    return client.post(WEBHOOK, data=json.dumps(payload), content_type="application/json", **extra)


ASSIST = {"client_id": "RJ4521", "name": "Ravi Kumar", "mobile": "9998887777", "email": "ravi@example.com"}


# --- auth ------------------------------------------------------------------

def test_webhook_rejects_without_key(seeded, client):
    assert _post(client, ASSIST).status_code == 401


def test_webhook_rejects_wrong_key(seeded, client):
    assert _post(client, ASSIST, HTTP_X_WATI_WEBHOOK_KEY="wrong").status_code == 401


# --- one Zoho lead, attributed to the referrer, with consent ---------------

def test_assisted_capture_creates_one_lead(seeded, client):
    r = _post(client, ASSIST, **KEY_HEADER)
    assert r.status_code == 200
    assert Lead.objects.count() == 1
    lead = Lead.objects.get()
    assert lead.lead_source == "whatsapp_assisted"
    assert lead.submitted_by == "referrer"
    assert lead.consent is True
    assert lead.consent_captured_at is not None
    # attributed to the referrer's identity (lazily created).
    assert lead.referral.referral_identity.client_id == "RJ4521"


def test_assisted_capture_lazily_creates_referrer_identity(seeded, client):
    assert not ReferralIdentity.objects.filter(client_id="RJ4521").exists()
    _post(client, ASSIST, **KEY_HEADER)
    assert ReferralIdentity.objects.filter(client_id="RJ4521").exists()


def test_prospect_pii_stored_on_erasable_record(seeded, client):
    _post(client, ASSIST, **KEY_HEADER)
    p = Prospect.objects.get()
    assert p.mobile == "919998887777"  # canonical normalized
    assert p.name == "Ravi Kumar"
    assert p.email == "ravi@example.com"


# --- dedup: repeat post does NOT double-create -----------------------------

def test_duplicate_post_does_not_double_create(seeded, client):
    _post(client, ASSIST, **KEY_HEADER)
    _post(client, ASSIST, **KEY_HEADER)  # same referrer + prospect mobile
    assert Lead.objects.count() == 1
    assert Prospect.objects.count() == 1


# --- never a password; PII never in the immutable event log ----------------

def test_password_field_rejected(seeded, client):
    payload = dict(ASSIST, password="hunter2")
    r = _post(client, payload, **KEY_HEADER)
    assert r.status_code == 422
    assert Lead.objects.count() == 0  # nothing persisted


def test_pii_not_in_event_log(seeded, client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _post(client, ASSIST, **KEY_HEADER)
    # A lead_captured event exists but carries NO PII in its metadata/body.
    for ev in Event.objects.all():
        blob = json.dumps(ev.metadata or {})
        assert "9998887777" not in blob
        assert "919998887777" not in blob
        assert "Ravi" not in blob
        assert "ravi@example.com" not in blob


# --- ENABLE_ZOHO_WRITE off => log-only, lead still captured locally ---------

def test_zoho_write_off_still_captures_lead(seeded, client, settings):
    # Default flags have ENABLE_ZOHO_WRITE False -> log-only adapter; the lead is
    # still saved locally (capture-first) and the request succeeds.
    from gorefer.flags import flags

    assert flags.ENABLE_ZOHO_WRITE is False
    r = _post(client, ASSIST, **KEY_HEADER)
    assert r.status_code == 200
    assert Lead.objects.count() == 1


# --- malformed payloads -> 422, never 500 ----------------------------------

def test_invalid_client_id_422(seeded, client):
    r = _post(client, dict(ASSIST, client_id="!!"), **KEY_HEADER)
    assert r.status_code == 422
    assert Lead.objects.count() == 0
