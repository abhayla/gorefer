"""M2 redirect + lazy-journey + click-event tests."""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event, VisitorPII
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram
from apps.referrals.redirect_service import assemble_destination


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


# --- destination assembly (server-side c= injection) -----------------------

def test_destination_assembled_with_server_side_partner_code(seeded):
    program = ReferralProgram.objects.get()
    url = assemble_destination(program, client_id="RJ4521")
    assert url == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"


def test_partner_direct_destination_has_no_r_param(seeded):
    program = ReferralProgram.objects.get()
    url = assemble_destination(program, client_id=None)
    assert url == "https://signup.zerodha.com/api/lead/?c=ZMPHZC"
    assert "r=" not in url.split("?", 1)[1]


# --- /r/{client_id} landing view (M3: renders 200, lazy journey + landing_viewed) --

def test_referral_landing_renders_200_and_creates_lazy_journey(seeded, client):
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")
    assert resp.status_code == 200  # landing page, NOT an immediate 302 (ADR-002)
    assert ReferralIdentity.objects.count() == 1
    assert Referral.objects.filter(source="referral_link").count() == 1
    assert Event.objects.filter(event_type="landing_viewed").count() == 1
    assert "gr_vid" in resp.cookies  # visitor cookie set on first landing


def test_continue_action_302s_to_zerodha(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    resp = client.get("/r/RJ4521/continue", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"


def test_client_id_normalized_uppercase(seeded, client):
    client.get("/r/rj4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert ReferralIdentity.objects.get().client_id == "RJ4521"


def test_repeat_landing_same_visitor_is_idempotent_on_identity(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert ReferralIdentity.objects.count() == 1
    assert Referral.objects.filter(source="referral_link").count() == 1


def test_invalid_client_id_returns_400_and_creates_nothing(seeded, client):
    resp = client.get("/r/bad--id!!", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 400
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.count() == 0


# --- bot/preview UA: generic landing, NO journey --------------------------

def test_bot_preview_creates_no_journey(seeded, client):
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="WhatsApp/2.23.20")
    assert resp.status_code == 200  # generic landing renders, but...
    assert ReferralIdentity.objects.count() == 0  # ...no journey/identity for a bot
    assert Referral.objects.count() == 0
    assert Event.objects.count() == 0


# --- /open partner-direct --------------------------------------------------

def test_partner_direct_creates_none_referrer_journey(seeded, client):
    resp = client.get("/open", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC"
    referral = Referral.objects.get(source="partner_direct")
    assert referral.referral_identity is None  # never a synthetic referrer
    assert ReferralIdentity.objects.count() == 0


# --- PII placement: raw IP on erasable record, NOT in event ---------------

@pytest.mark.django_db(transaction=True)
def test_raw_ip_stored_on_erasable_record_not_in_event(client):
    call_command("seed_program")
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    pii = VisitorPII.objects.get()
    assert pii.raw_ip == "203.0.113.7"
    event = Event.objects.get()
    assert "203.0.113.7" not in str(event.metadata)
    assert event.person_ref_id == pii.pk
