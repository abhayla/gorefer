"""M3 landing page + capture + beacon + name-reveal + share tests."""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.common.phone import normalize_phone
from apps.events import vocab
from apps.events.models import ClickNonce, Event
from apps.referrals import redirect_service
from apps.referrals.models import Customer, Lead, Prospect
from apps.tenants.resolve import get_bootstrap_tenant


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
    # from it at click time — DA polish #1); it is the WhatsApp SHARE target.
    assert "917080642020" in html
    assert 'watiNumber: "917080642020"' in html
    # Ashok's helpline (73888…) now legitimately appears on the landing as the config
    # "call" line (DA M9 fix batch) — but it is NEVER the wa.me SHARE target.
    assert "wa.me/917388882020" not in html and "917388882020?text" not in html
    assert "tel:+917388882020" in html   # helpline is a tel: link only
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


def test_mobile_input_maxlength_does_not_truncate_pasted_plus91_number(seeded, client):
    """A pasted '+91 98765 43210' (15 chars) must survive the HTML maxlength so
    landing.js's digit-strip-then-enforce-10 logic sees the whole paste (pt 11)."""
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    html = resp.content.decode()
    assert 'id="mobileInput"' in html
    assert 'maxlength="10"' not in html
    assert 'maxlength="15"' in html
    pasted = "+91 98765 43210"
    assert len(pasted) <= 15
    # JS still strips non-digits then enforces exactly-10 (pattern unchanged by this fix).
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "static" / "js" / "landing.js").read_text(encoding="utf-8")
    assert 'replace(/\\D/g, "")' in js
    assert "^[6-9]\\d{9}$" in js


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


def test_name_reveal_returns_first_name_when_customer_on_file(seeded, client):
    tenant = get_bootstrap_tenant()
    program = redirect_service.get_active_program(tenant)
    Customer.objects.create(
        tenant=tenant, program=program, partner=program.partner,
        client_id="RJ4521", first_name="Rahul", last_name="Sharma",
    )
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    nonce = ClickNonce.objects.get()
    resp = client.get(f"/api/click/referrer/RJ4521?nonce={nonce.nonce}", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_referrer"] is True
    assert data["first_name"] == "Rahul"
    # Surname is never leaked, in any form.
    assert "Sharma" not in resp.content.decode()


def test_name_reveal_returns_null_when_no_customer_on_file(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    nonce = ClickNonce.objects.get()
    resp = client.get(f"/api/click/referrer/RJ4521?nonce={nonce.nonce}", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_referrer"] is True
    assert data["first_name"] is None


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


# --- D4: repeat submissions (owner decision 2026-07-26) ---------------------

def test_repeat_submission_fills_blank_fields_but_never_overwrites(seeded):
    """Prod carried Prospect 5 created as "Deploy Verify" with a blank email; a later
    submission supplying a real name+email left it untouched while Zoho DID get the new
    values, so the two systems drifted. Fill blanks; never clobber a populated field."""
    from apps.referrals import redirect_service
    from apps.referrals.lead_service import capture_lead
    from apps.referrals.models import Prospect

    program = redirect_service.get_active_program(seeded)
    referral = redirect_service._lazy_get_or_create_referral(seeded, program, "RJ4521")
    capture_lead(tenant=seeded, referral=referral, name="First Name", mobile="9812345678",
                 email="", city="", consent=True)

    capture_lead(tenant=seeded, referral=referral, name="Overwrite Attempt",
                 mobile="9812345678", email="real@example.com", city="Pune", consent=True)

    p = Prospect.objects.get(mobile=normalize_phone("9812345678"))
    assert p.name == "First Name", "a populated field must NOT be overwritten"
    assert p.email == "real@example.com", "a BLANK field must be filled from the new submission"
    assert p.city == "Pune"


def test_one_lead_per_mobile_even_across_different_referrers(
    seeded, django_capture_on_commit_callbacks
):
    """D4: dedupe on the prospect alone. The old key was (referral, prospect), so a second
    referrer submitting the same number created a SECOND lead for the same human."""
    from apps.events.models import Event
    from apps.referrals import redirect_service
    from apps.referrals.lead_service import capture_lead
    from apps.referrals.models import Lead

    program = redirect_service.get_active_program(seeded)
    ref_a = redirect_service._lazy_get_or_create_referral(seeded, program, "RJ4521")
    ref_b = redirect_service._lazy_get_or_create_referral(seeded, program, "GW5500")

    lead_a = capture_lead(tenant=seeded, referral=ref_a, name="Riya", mobile="9812345678",
                          email="", city="", consent=True)
    # the duplicate-submission event is emitted on_commit, so capture + execute it
    with django_capture_on_commit_callbacks(execute=True):
        lead_b = capture_lead(tenant=seeded, referral=ref_b, name="Riya", mobile="9812345678",
                              email="", city="", consent=True)

    assert lead_a.pk == lead_b.pk, "same mobile must reuse the one lead"
    assert Lead.objects.filter(prospect=lead_a.prospect, deleted_at__isnull=True).count() == 1

    # the second referrer's attempt must stay VISIBLE, not vanish
    ev = Event.objects.filter(referral=ref_b, event_type=vocab.LEAD_CAPTURED).first()
    assert ev is not None, "the duplicate submission must be recorded on the new referral"
    assert ev.metadata.get("duplicate_of_lead") == lead_a.pk
    for key in ("name", "mobile", "email", "city"):
        assert key not in ev.metadata, "no PII in the event log (Round-2 #16)"
