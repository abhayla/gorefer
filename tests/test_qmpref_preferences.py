"""Q-M-PREF — Preferences / Settings screen (ADR-034).

The UI home for the per-tenant config cascade. Critically, LANDING_MODE is set HERE,
through the screen (POST /admin-panel/preferences), NOT via a backend override. The
ADR-032 compliance coupling — `direct` only when a live /d/{slug} exists — is enforced
AT THE SCREEN. Admin-only, tenant-scoped, config-over-code, Postgres-only, demo offline.

Acceptance (S2-03 §14):
  - Flip Landing mode → Direct via the screen persists landing_mode=direct AND live
    /r/wa/{id} then 302s straight to Zerodha (click recorded, Location clean).
  - `direct` refused in the UI when the tenant has no live /d/{slug}.
  - Each control persists + takes effect; admin-only; tenant-scoped; add/remove a
    partnership changes /d/{slug}.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve
from apps.config.models import ConfigGlobal
from apps.events.models import Event
from apps.referrals.models import Partner, ReferralProgram
from apps.tenants.models import Tenant

PREFS_URL = "/admin-panel/preferences"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


@pytest.fixture
def admin_client(seeded):
    User = get_user_model()
    User.objects.create_user(
        username="admin@pifs.in", email="admin@pifs.in", password="pw12345!", is_staff=True
    )
    c = Client()
    c.login(username="admin@pifs.in", password="pw12345!")
    return c


def _tenant():
    return Tenant.objects.get(slug="pifs")


def _base_form(**overrides):
    """A full preferences POST body (all controls) with sensible defaults."""
    data = {
        "landing_mode": "page",
        "referrer_reward_claim": "10% brokerage share + 300 reward points",
        "support_helpline_phone": "+91 73888 82020",
        "wati_business_number": "917080642020",
        "share_channels": ["wa", "copy"],
        # checkboxes: present == on, absent == off
        "share_show_reward": "on",
        "enable_assisted_referral": "on",
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------- admin-only + render


def test_preferences_requires_login(seeded):
    resp = Client().get(PREFS_URL)
    assert resp.status_code == 302
    assert "/admin-panel/login/" in resp.headers["Location"]


def test_preferences_requires_staff(seeded):
    User = get_user_model()
    User.objects.create_user(username="joe", password="pw12345!", is_staff=False)
    c = Client()
    c.login(username="joe", password="pw12345!")
    resp = c.get(PREFS_URL)
    assert resp.status_code == 302  # bounced to login


def test_preferences_renders_variant_c(admin_client):
    resp = admin_client.get(PREFS_URL)
    assert resp.status_code == 200
    body = resp.content.decode()
    # Matches the approved mockup's sections.
    assert "Preferences" in body
    assert "When someone taps your referral link" in body
    assert "Show landing page" in body and "Direct to Zerodha" in body
    assert "Enabled share channels" in body
    assert "gorefer.in/d/pifs" in body


# ---------------------------------------- ACCEPTANCE: flip to Direct THROUGH the screen


def test_flip_to_direct_via_screen_persists_and_takes_effect(
    admin_client, client_unused=None, django_capture_on_commit_callbacks=None
):
    # PIFS is seeded with an active Zerodha program => a live /d/pifs exists => Direct allowed.
    resp = admin_client.post(PREFS_URL, _base_form(landing_mode="direct"))
    assert resp.status_code == 200

    # Persisted at the TENANT (global) tier — through the screen, not a backend override.
    assert resolve(prefkeys.LANDING_MODE, tenant_id=_tenant().id) == "direct"
    assert ConfigGlobal.objects.filter(tenant=_tenant(), key="landing_mode", value="direct").exists()


@pytest.mark.django_db
def test_direct_set_via_screen_makes_wa_redirect_clean(admin_client, django_capture_on_commit_callbacks):
    # Flip to Direct through the screen...
    admin_client.post(PREFS_URL, _base_form(landing_mode="direct"))
    # ...then a live /r/wa/{id} 302s straight to Zerodha, click recorded, Location clean.
    visitor = Client()
    with django_capture_on_commit_callbacks(execute=True):
        resp = visitor.get("/r/wa/RJ4521", **HUMAN)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"
    loc = resp.headers["Location"]
    assert "s=" not in loc and "wa" not in loc.rsplit("r=", 1)[0]
    assert Event.objects.filter(event_type="click").exists()
    assert not Event.objects.filter(event_type="landing_viewed").exists()


# --------------------------------------- ACCEPTANCE: Direct REFUSED without a live /d/


def _tenant_without_live_disclosure():
    """Deactivate PIFS's only program → /d/pifs composes nothing → not 'live'."""
    ReferralProgram.objects.filter(tenant=_tenant()).update(status="inactive")


def test_direct_refused_when_no_live_disclosure_page(admin_client):
    _tenant_without_live_disclosure()
    resp = admin_client.post(PREFS_URL, _base_form(landing_mode="direct"))
    assert resp.status_code == 200
    # Refused at the screen — forced back to page, NOT persisted as direct.
    assert resolve(prefkeys.LANDING_MODE, tenant_id=_tenant().id, default="page") == "page"
    # And the UI told the user why.
    assert b"disclosure page" in resp.content.lower()


def test_direct_segment_disabled_in_ui_without_live_disclosure(admin_client):
    _tenant_without_live_disclosure()
    resp = admin_client.get(PREFS_URL)
    body = resp.content.decode()
    # The Direct button is rendered disabled (cannot be chosen).
    assert "disabled" in body
    assert "unavailable until you have a live disclosure page" in body


# --------------------------------------------------- each control persists + takes effect


def test_reward_controls_persist_and_hide_on_landing(admin_client):
    # Turn the reward OFF + change the claim text.
    admin_client.post(
        PREFS_URL,
        _base_form(referrer_reward_claim="Flat 15% share"),  # share_show_reward omitted below
    )
    # First save keeps it on; now explicitly turn it off (absent checkbox).
    form = _base_form(referrer_reward_claim="Flat 15% share")
    form.pop("share_show_reward")
    admin_client.post(PREFS_URL, form)
    assert resolve(prefkeys.SHARE_SHOW_REWARD, tenant_id=_tenant().id) is False
    assert resolve(prefkeys.REFERRER_REWARD_CLAIM, tenant_id=_tenant().id) == "Flat 15% share"

    # Landing page reflects it: reward panel hidden.
    visitor = Client()
    resp = visitor.get("/r/RJ4521", **HUMAN)
    assert resp.status_code == 200
    assert b"Flat 15% share" not in resp.content  # hidden when show_reward is off


def test_reward_claim_shows_on_landing_when_on(admin_client):
    admin_client.post(PREFS_URL, _base_form(referrer_reward_claim="Earn 12% brokerage share"))
    visitor = Client()
    resp = visitor.get("/r/RJ4521", **HUMAN)
    assert b"Earn 12% brokerage share" in resp.content


def test_helpline_and_wati_number_persist_and_take_effect(admin_client):
    admin_client.post(
        PREFS_URL,
        _base_form(support_helpline_phone="+91 90000 11111", wati_business_number="919000022222"),
    )
    assert resolve(prefkeys.SUPPORT_HELPLINE_PHONE, tenant_id=_tenant().id) == "+91 90000 11111"
    assert resolve(prefkeys.WATI_BUSINESS_NUMBER, tenant_id=_tenant().id) == "919000022222"
    # Landing page renders the configured helpline + wa number.
    resp = Client().get("/r/RJ4521", **HUMAN)
    body = resp.content.decode()
    assert "+91 90000 11111" in body
    assert "919000022222" in body


def test_share_channels_allowlist_persists(admin_client):
    admin_client.post(PREFS_URL, _base_form(share_channels=["fb", "li"]))
    channels = resolve(prefkeys.SHARE_CHANNELS_ALLOWLIST, tenant_id=_tenant().id)
    assert "fb" in channels and "li" in channels
    # WhatsApp + Copy stay always-on even if not submitted.
    assert "wa" in channels and "copy" in channels


def test_assisted_referral_toggle_persists(admin_client):
    form = _base_form()
    form.pop("enable_assisted_referral")  # off
    admin_client.post(PREFS_URL, form)
    assert resolve(prefkeys.ENABLE_ASSISTED_REFERRAL, tenant_id=_tenant().id) is False
    admin_client.post(PREFS_URL, _base_form(enable_assisted_referral="on"))
    assert resolve(prefkeys.ENABLE_ASSISTED_REFERRAL, tenant_id=_tenant().id) is True


# ------------------------------------------------ partnerships change /d/{slug}


def test_add_partnership_appears_on_disclosure_page(admin_client):
    admin_client.post(
        f"{PREFS_URL}/partnership",
        {"action": "add", "name": "HDFC Life", "regulator": "irdai"},
    )
    prog = ReferralProgram.objects.filter(tenant=_tenant(), name="HDFC Life").first()
    assert prog is not None and prog.status == "active"
    # The new block now composes on /d/pifs.
    resp = Client().get("/d/pifs")
    assert resp.status_code == 200
    assert b"IRDAI" in resp.content


def test_deactivate_partnership_removes_block_from_disclosure_page(admin_client):
    # Add a second (so PIFS keeps a live disclosure host) then deactivate it.
    admin_client.post(
        f"{PREFS_URL}/partnership",
        {"action": "add", "name": "Bajaj Finserv", "regulator": "rbi"},
    )
    prog = ReferralProgram.objects.get(tenant=_tenant(), name="Bajaj Finserv")
    assert b"RBI" in Client().get("/d/pifs").content
    admin_client.post(
        f"{PREFS_URL}/partnership",
        {"action": "deactivate", "program_id": str(prog.id)},
    )
    prog.refresh_from_db()
    assert prog.status == "inactive"
    # Its regulator block drops off /d/pifs (RBI gone; Zerodha SEBI/NSE remains).
    body = Client().get("/d/pifs").content
    assert b"RBI" not in body


def test_cannot_deactivate_last_partnership_while_direct(admin_client):
    # Go Direct (allowed — PIFS has a live disclosure page), then try to strand it.
    admin_client.post(PREFS_URL, _base_form(landing_mode="direct"))
    zerodha = ReferralProgram.objects.get(tenant=_tenant(), name="Zerodha")
    resp = admin_client.post(
        f"{PREFS_URL}/partnership",
        {"action": "deactivate", "program_id": str(zerodha.id)},
    )
    zerodha.refresh_from_db()
    assert zerodha.status == "active"  # refused
    assert b"last active partnership" in resp.content.lower()


# ------------------------------------------------------- tenant isolation


def test_tenant_scoped_no_cross_tenant_write(admin_client):
    # A second tenant with its own program.
    other = Tenant.objects.create(name="Other Broker", slug="other")
    partner = Partner.objects.create(tenant=other, name="Other", code="OTHERX", status="active")
    ReferralProgram.objects.create(
        tenant=other, partner=partner, name="OtherProg", status="active", regulator="sebi_nse"
    )
    # Saving PIFS preferences writes ONLY PIFS's tenant tier.
    admin_client.post(PREFS_URL, _base_form(support_helpline_phone="+91 88888 88888"))
    assert not ConfigGlobal.objects.filter(tenant=other, key="support_helpline_phone").exists()
    # `other` still resolves the central default, unaffected by PIFS's override.
    assert resolve(prefkeys.SUPPORT_HELPLINE_PHONE, tenant_id=other.id) != "+91 88888 88888"


# ------------------------------------------------------- config-over-code / no backend flip


def test_landing_mode_is_not_a_settings_flag(seeded):
    # ADR-034: landing_mode lives in the cascade, not a Django setting/env flag.
    from django.conf import settings

    assert not hasattr(settings, "LANDING_MODE")
