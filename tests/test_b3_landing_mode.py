"""B3 — LANDING_MODE page|direct + derived MESSAGE_DISCLOSURE_LEVEL (ADR-032).

Per-tenant LANDING_MODE:
  - page   (default): /r/{id} renders the landing page.
  - direct          : /r/{id} logs the click on-commit then 302s straight to Zerodha,
                      skipping the landing (channel/?s stripped, code server-side).

Coupling (§3b, no bypass-without-disclosure gap): MESSAGE_DISCLOSURE_LEVEL is
DERIVED — full iff direct AND no live /d/{slug}; else light. A hand-set
direct+light+no-/d/ combination is refused.

Guardrails asserted (S2-03 §11 / S2-04 §B3).
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.config.models import ConfigGlobal
from apps.events.models import Event
from apps.referrals.landing_mode import (
    DISCLOSURE_FULL,
    DISCLOSURE_LIGHT,
    DisclosureCouplingError,
    assert_disclosure_coupling,
    resolve_landing_mode,
    resolve_message_disclosure_level,
)
from apps.tenants.models import Tenant


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}


def _tenant():
    return Tenant.objects.get(slug="pifs")


def _set(tenant, key, value):
    ConfigGlobal.objects.update_or_create(tenant=tenant, key=key, defaults={"value": value})


# --- LANDING_MODE=page (default) : renders the landing -----------------------

def test_default_mode_is_page_renders_landing(seeded, client):
    assert resolve_landing_mode(_tenant().id) == "page"
    resp = client.get("/r/RJ4521", **HUMAN)
    assert resp.status_code == 200  # landing page, not a redirect
    assert Event.objects.filter(event_type="landing_viewed").exists()


# --- LANDING_MODE=direct : logs click on-commit then 302, skips landing ------

def test_direct_mode_302s_and_skips_landing(seeded, client, django_capture_on_commit_callbacks):
    _set(_tenant(), "landing_mode", "direct")
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.get("/r/RJ4521", **HUMAN)
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"
    # click logged (on-commit), but NO landing_viewed (page skipped).
    assert Event.objects.filter(event_type="click").exists()
    assert not Event.objects.filter(event_type="landing_viewed").exists()


def test_direct_mode_strips_channel_from_302(seeded, client, django_capture_on_commit_callbacks):
    _set(_tenant(), "landing_mode", "direct")
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.get("/r/wa/RJ4521", **HUMAN)  # channel via path
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"
    assert "s=" not in loc and "wa" not in loc.rsplit("r=", 1)[0]
    # ...but the channel WAS attributed on the click.
    assert Event.objects.get(event_type="click").metadata.get("channel") == "WhatsApp"


def test_direct_mode_query_param_channel_also_stripped(
    seeded, client, django_capture_on_commit_callbacks
):
    _set(_tenant(), "landing_mode", "direct")
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.get("/r/RJ4521?s=fb", **HUMAN)
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"
    assert Event.objects.get(event_type="click").metadata.get("channel") == "Facebook"


def test_direct_mode_no_partner_code_leak_in_any_body(seeded, client):
    # A direct-mode redirect has an EMPTY body (302) — the code is only in Location.
    _set(_tenant(), "landing_mode", "direct")
    resp = client.get("/r/RJ4521", **HUMAN)
    assert "ZMPHZC" not in resp.content.decode()


def test_direct_mode_bot_creates_no_journey(seeded, client):
    _set(_tenant(), "landing_mode", "direct")
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="facebookexternalhit/1.1")
    # D2 (owner, 2026-07-26): a crawler now gets the PIFS link-preview card (200) instead of
    # a 302 — previously WhatsApp built its preview from the PARTNER's page. Still creates
    # no click/journey, which is the property this test really guards.
    assert resp.status_code == 200
    assert not Event.objects.filter(event_type="click").exists()


# --- derived MESSAGE_DISCLOSURE_LEVEL + coupling -----------------------------

def test_disclosure_level_light_when_page_mode(seeded):
    tenant = _tenant()
    assert resolve_message_disclosure_level(tenant) == DISCLOSURE_LIGHT


def test_disclosure_level_light_when_direct_but_live_disclosure_host(seeded):
    tenant = _tenant()
    _set(tenant, "landing_mode", "direct")
    # /d/{slug} host is enabled (default), so a direct link can link to it -> light.
    assert resolve_message_disclosure_level(tenant) == DISCLOSURE_LIGHT


def test_disclosure_level_full_when_direct_and_no_live_host(seeded):
    tenant = _tenant()
    _set(tenant, "landing_mode", "direct")
    _set(tenant, "disclosure_page_enabled", False)  # no live /d/ host
    assert resolve_message_disclosure_level(tenant) == DISCLOSURE_FULL


def test_coupling_refuses_direct_light_no_disclosure_host(seeded):
    tenant = _tenant()
    _set(tenant, "landing_mode", "direct")
    _set(tenant, "disclosure_page_enabled", False)
    _set(tenant, "message_disclosure_level", "light")  # illegal hand-set override
    with pytest.raises(DisclosureCouplingError):
        assert_disclosure_coupling(tenant)


def test_coupling_ok_when_direct_light_but_host_live(seeded):
    tenant = _tenant()
    _set(tenant, "landing_mode", "direct")
    _set(tenant, "message_disclosure_level", "light")
    # host is live (default enabled) -> light is fine, no raise.
    assert_disclosure_coupling(tenant)  # does not raise


def test_coupling_ok_when_page_mode(seeded):
    tenant = _tenant()
    _set(tenant, "message_disclosure_level", "light")
    assert_disclosure_coupling(tenant)  # page mode -> nothing to enforce
