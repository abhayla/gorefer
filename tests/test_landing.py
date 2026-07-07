"""M3 landing page + capture + beacon + name-reveal + share tests."""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import ClickNonce, Event
from apps.referrals.models import Lead, Prospect


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


# --- landing content -------------------------------------------------------

def test_landing_renders_generic_greeting_no_referrer_name(seeded, client):
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    html = resp.content.decode()
    assert resp.status_code == 200
    # Generic greeting, NOT a referrer name (enumeration guard #1/#3).
    assert 'id="gr-referrer"' in html
    assert "Someone" in html


def test_landing_has_compliance_referral_echo_and_business_whatsapp(seeded, client):
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    html = resp.content.decode()
    # Referral ID echo
    assert "Referral ID:" in html and "RJ4521" in html
    # Compliance disclosure + risk warning (non-removable)
    assert "AP2516003693" in html
    assert "market risks" in html
    # Single swappable incentive claim (reordered — DA polish #2)
    assert "10% brokerage share + 300 reward points" in html
    # The WATI BUSINESS number is exposed to the page (JS builds the wa.me deep link
    # from it at click time — DA polish #1); never Ashok's personal 73888.
    assert "917080642020" in html
    assert "7388882020" not in html
    # Consent + Privacy Policy present
    assert "Privacy Policy" in html
    assert "consentInput" in html


def test_whatsapp_share_message_built_from_form_in_js():
    """The exact DA share message + config number are constructed client-side in
    landing.js (from the form inputs at click time), URL-encoded."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "static" / "js" / "landing.js").read_text(encoding="utf-8")
    assert "My Referral ID: " in js
    assert "*Here are referral details*" in js
    assert "Name: " in js and "Phone Number: " in js and "Email: " in js
    assert "https://wa.me/" in js and "GR.watiNumber" in js
    assert "encodeURIComponent" in js


def test_landing_does_not_clone_zerodha(seeded, client):
    html = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0").content.decode()
    # PIFS-branded, not Zerodha-branded.
    assert "Passive Income Financial Solutions" in html
    assert "signup.zerodha.com" not in html
    assert "ZMPHZC" not in html


def test_invalid_link_renders_branded_fallback_no_incentive(seeded, client):
    resp = client.get("/r/bad--id", HTTP_USER_AGENT="Mozilla/5.0")
    html = resp.content.decode()
    assert resp.status_code == 400
    assert "isn't valid" in html
    # Compliance still injected, but no referral-benefit panel.
    assert "AP2516003693" in html
    assert "Referral benefit" not in html


# --- beacon + nonce --------------------------------------------------------

def test_landing_mints_nonce(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    assert ClickNonce.objects.count() == 1


def test_beacon_confirms_human_with_valid_nonce(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    nonce = ClickNonce.objects.get()
    vid = client.cookies["gr_vid"].value
    resp = client.post(
        "/api/click/confirm",
        data={"client_id": "RJ4521", "nonce": nonce.nonce, "visitor_id": vid},
        content_type="application/json",
    )
    assert resp.status_code == 202
    assert resp.json() == {"confirmed": True}
    nonce.refresh_from_db()
    assert nonce.consumed_at is not None
    assert Event.objects.filter(event_type="landing_viewed", is_confirmed_human=True).count() == 1


def test_beacon_rejects_forged_nonce(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    resp = client.post(
        "/api/click/confirm",
        data={"client_id": "RJ4521", "nonce": "forged", "visitor_id": "x"},
        content_type="application/json",
    )
    assert resp.status_code == 401


def test_nonce_is_single_use(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    nonce = ClickNonce.objects.get()
    vid = client.cookies["gr_vid"].value
    body = {"client_id": "RJ4521", "nonce": nonce.nonce, "visitor_id": vid}
    assert client.post("/api/click/confirm", data=body, content_type="application/json").status_code == 202
    # second use rejected
    assert client.post("/api/click/confirm", data=body, content_type="application/json").status_code == 401


# --- name reveal (nonce-gated) --------------------------------------------

def test_name_reveal_requires_valid_nonce(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    # no nonce -> 401
    assert client.get("/api/click/referrer/RJ4521", HTTP_USER_AGENT="Mozilla/5.0").status_code == 401
    # valid nonce -> 200 (has_referrer true, name null in M3 — never fabricated)
    nonce = ClickNonce.objects.get()
    resp = client.get(f"/api/click/referrer/RJ4521?nonce={nonce.nonce}", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_referrer"] is True
    assert data["first_name"] is None  # no Zoho name source yet (M6)


def test_name_reveal_blocks_bots(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    nonce = ClickNonce.objects.get()
    resp = client.get(
        f"/api/click/referrer/RJ4521?nonce={nonce.nonce}", HTTP_USER_AGENT="facebookexternalhit/1.1"
    )
    assert resp.status_code == 401


# --- lead capture (capture-first, PII placement) --------------------------

@pytest.mark.django_db(transaction=True)
def test_lead_capture_saves_gorefer_first_and_emits_event():
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    resp = c.post(
        "/api/leads/",
        data={"client_id": "RJ4521", "name": "Rahul Sharma", "mobile": "9876543210",
              "email": "rahul@example.com", "consent": True},
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "new"
    assert body["continue_url"] == "/r/RJ4521/continue"
    # Prospect + Lead saved to GoRefer; phone normalized to 91XXXXXXXXXX.
    prospect = Prospect.objects.get()
    assert prospect.mobile == "919876543210"
    lead = Lead.objects.get()
    assert lead.consent is True
    # lead_captured event emitted; NO PII in the event.
    ev = Event.objects.filter(event_type="lead_captured").get()
    assert "rahul@example.com" not in str(ev.metadata)
    assert "9876543210" not in str(ev.metadata)


def test_lead_capture_requires_consent(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    resp = client.post(
        "/api/leads/",
        data={"client_id": "RJ4521", "name": "Rahul", "mobile": "9876543210", "consent": False},
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_lead_capture_rejects_bad_mobile(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    resp = client.post(
        "/api/leads/",
        data={"client_id": "RJ4521", "name": "Rahul", "mobile": "12345", "consent": True},
        content_type="application/json",
    )
    assert resp.status_code == 422


# --- share ----------------------------------------------------------------

def test_share_records_event(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    resp = client.post(
        "/api/share/",
        data={"client_id": "RJ4521", "channel": "whatsapp"},
        content_type="application/json",
    )
    assert resp.status_code == 202
    assert Event.objects.filter(event_type="share_clicked").count() == 1
