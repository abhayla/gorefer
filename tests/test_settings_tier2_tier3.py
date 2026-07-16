"""Settings screen — Tier-2 notification routing + Tier-3 staged referrer defaults.

DA mission 2026-07-16 (the follow-on to the integration-flag checkboxes).

Tier 2 (admin, live now): WhatsApp notification-routing toggles (office / prospect /
referrer). Two claims matter and are tested here:
  1. Defaults are ON for all three, so adding the toggles changes NOTHING until an
     admin turns one off (today all three fire — doc-08 A6).
  2. Routing is SUPPRESSION-ONLY. Turning a role on can never override an existing
     suppression (opt-out, unknown referrer phone). A toggle that could force a send
     to an opted-out person would be a compliance bug, not a feature (BR-008/A4).

Tier 3 (staged, dormant): per-referrer landing_mode / notifications / language /
promo opt-out. Hidden AND inert until ENABLE_CUSTOMER_LOGIN — the cascade's user tier
is itself gated on that flag, so this is a real gate, not a hidden div.

NOTE on REFERRAL_INCENTIVE_CLAIM: deliberately NOT touched — it is in
COMPLIANCE_LOCKED_KEYS (ADR-014/022) and the tenant-editable twin
(`referrer_reward_claim`) already exists on this screen. See the QUESTION in
COORDINATION.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve
from apps.config.models import ConfigGlobal
from apps.tenants.models import Tenant

PREFS_URL = "/admin-panel/preferences"


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


def _form(**overrides):
    """A full preferences POST. Checkboxes: present == on, absent == off."""
    data = {
        "landing_mode": "page",
        "referrer_reward_claim": "10% brokerage share + 300 reward points",
        "support_helpline_phone": "+91 73888 82020",
        "wati_business_number": "917080642020",
        "share_channels": ["wa", "copy"],
        "share_show_reward": "on",
        "enable_assisted_referral": "on",
        # notification routing: all three on
        "notify_office": "on",
        "notify_prospect": "on",
        "notify_referrer": "on",
    }
    data.update(overrides)
    return data


# --- Tier 2: routing defaults must preserve today's behaviour --------------------

def test_notification_routing_defaults_all_on(seeded):
    """Adding the toggles must change nothing: today all three notifications fire."""
    routing = prefkeys.notification_routing(_tenant().id)
    assert routing == {"office": True, "prospect": True, "referrer": True}


def test_routing_toggle_persists_and_resolves(admin_client):
    admin_client.post(PREFS_URL, _form(notify_referrer=""))  # unchecked == off
    routing = prefkeys.notification_routing(_tenant().id)
    assert routing["referrer"] is False
    assert routing["office"] is True and routing["prospect"] is True
    assert resolve(prefkeys.NOTIFY_REFERRER, tenant_id=_tenant().id, default=True) is False


# --- Tier 2: the toggles actually gate the sends ---------------------------------

@pytest.mark.django_db
def test_routing_off_skips_that_notification_with_a_reason(seeded):
    """A role turned off must be recorded as SKIPPED WITH A REASON, not vanish.

    The funnel has to show the message did not go and why — a silently missing row
    would look identical to "never triggered".
    """
    from apps.integrations.models import Notification

    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=prefkeys.NOTIFY_OFFICE, value=False)
    referral, prospect = _make_referral_and_prospect()

    from apps.integrations.wati.notify import queue_lead_notifications

    queue_lead_notifications(
        tenant=_tenant(), referral=referral, prospect=prospect, client_id="RJ4521"
    )
    office = Notification.objects.get(referral=referral, recipient_role="office")
    assert office.status == "skipped"
    assert "turned off in settings" in office.skip_reason


@pytest.mark.django_db
def test_routing_on_cannot_override_an_opt_out(seeded):
    """THE compliance claim: routing is suppression-only.

    An opted-out prospect stays skipped for opt-out even with the toggle ON. If the
    toggle could clear that, an admin checkbox would be able to message someone who
    opted out (BR-008 / doc-08 A4) — a compliance bug, not a feature.
    """
    from apps.integrations.models import Notification

    referral, prospect = _make_referral_and_prospect(opted_out=True)

    from apps.integrations.wati.notify import queue_lead_notifications

    queue_lead_notifications(
        tenant=_tenant(), referral=referral, prospect=prospect, client_id="RJ4521"
    )
    n = Notification.objects.get(referral=referral, recipient_role="prospect")
    assert n.status == "skipped"
    assert "opted out" in n.skip_reason, (
        "routing must not be able to clear an opt-out suppression"
    )


@pytest.mark.django_db
def test_routing_on_cannot_invent_an_unknown_referrer_phone(seeded):
    """Same rule for the referrer: unknown phone => skip, never guess (BR-010)."""
    from apps.integrations.models import Notification

    referral, prospect = _make_referral_and_prospect()

    from apps.integrations.wati.notify import queue_lead_notifications

    queue_lead_notifications(
        tenant=_tenant(), referral=referral, prospect=prospect, client_id="UNKNOWN9"
    )
    n = Notification.objects.get(referral=referral, recipient_role="referrer")
    assert n.status == "skipped"
    assert "phone unknown" in n.skip_reason


def _make_referral_and_prospect(*, opted_out: bool = False):
    """Minimal referral + prospect for the notify path.

    Opt-out is set as an in-memory ATTRIBUTE, not a column: Sprint 1 has no opt-out
    field on Prospect yet — `notify._is_opted_out` reads it via getattr as a
    forward-compatible hook. Setting the attribute exercises that hook exactly as a
    real field would once it lands.
    """
    from apps.referrals.models import Prospect, Referral, ReferralIdentity, ReferralProgram

    tenant = _tenant()
    program = ReferralProgram.objects.filter(tenant=tenant).first()
    identity, _ = ReferralIdentity.objects.get_or_create(
        tenant=tenant, partner=program.partner, program=program,
        client_id="RJ4521", id_source="native",
    )
    prospect = Prospect.objects.create(
        tenant=tenant, name="Test Person", mobile="919812345670",
    )
    if opted_out:
        prospect.whatsapp_opt_out = True  # duck-typed hook (see docstring)
    # Referral carries no prospect FK (the prospect hangs off Lead); notify takes the
    # prospect as an explicit argument, which is what we pass below.
    referral = Referral.objects.create(
        tenant=tenant, referral_identity=identity, program=program,
        source="referral_link",
    )
    return referral, prospect


# --- Tier 3: staged — hidden AND inert until customer login ----------------------

def test_tier3_referrer_controls_hidden_until_customer_login(admin_client):
    """Constitution §4: no dead UI. A referrer cannot reach a screen to change these
    until customer login ships, so showing them would be exactly that."""
    body = admin_client.get(PREFS_URL).content.decode()
    assert 'name="referrer_landing_mode"' not in body
    assert 'name="referrer_language"' not in body
    assert 'name="referrer_notifications_on"' not in body
    assert 'name="referrer_promo_opt_out"' not in body


def test_tier3_referrer_controls_render_when_customer_login_on(admin_client, monkeypatch):
    import dataclasses

    from apps.dashboard import preferences_service as svc
    from gorefer import flags as flags_mod

    monkeypatch.setattr(
        svc, "flags", dataclasses.replace(flags_mod.flags, ENABLE_CUSTOMER_LOGIN=True)
    )
    body = admin_client.get(PREFS_URL).content.decode()
    assert 'name="referrer_landing_mode"' in body
    assert 'name="referrer_language"' in body


def test_tier3_not_written_while_customer_login_is_off(admin_client):
    """Writing them now would persist settings nobody can reach AND that the dormant
    user tier can't read — invisible and inert, i.e. silently misleading."""
    admin_client.post(PREFS_URL, _form(referrer_language="hi", referrer_promo_opt_out="on"))
    assert not ConfigGlobal.objects.filter(
        tenant_id=_tenant().id, key=prefkeys.REFERRER_LANGUAGE
    ).exists()


def test_tier3_persists_when_customer_login_on(admin_client, monkeypatch):
    import dataclasses

    from apps.dashboard import preferences_service as svc
    from gorefer import flags as flags_mod

    monkeypatch.setattr(
        svc, "flags", dataclasses.replace(flags_mod.flags, ENABLE_CUSTOMER_LOGIN=True)
    )
    admin_client.post(PREFS_URL, _form(referrer_language="hi", referrer_promo_opt_out="on"))
    prefs = prefkeys.get_referrer_preferences(_tenant().id, None)
    assert prefs[prefkeys.REFERRER_LANGUAGE] == "hi"
    assert prefs[prefkeys.REFERRER_PROMO_OPT_OUT] is True


def test_tier3_defaults_are_sane_and_inherit(seeded):
    prefs = prefkeys.get_referrer_preferences(_tenant().id, None)
    assert prefs[prefkeys.REFERRER_LANDING_MODE] == ""  # inherit the tenant default
    assert prefs[prefkeys.REFERRER_LANGUAGE] == "en"
    assert prefs[prefkeys.REFERRER_NOTIFICATIONS_ON] is True
    assert prefs[prefkeys.REFERRER_PROMO_OPT_OUT] is False


def test_tier3_rejects_an_unknown_language(seeded):
    ConfigGlobal.objects.create(
        tenant_id=_tenant().id, key=prefkeys.REFERRER_LANGUAGE, value="klingon"
    )
    prefs = prefkeys.get_referrer_preferences(_tenant().id, None)
    assert prefs[prefkeys.REFERRER_LANGUAGE] == "en", "unknown language must fall back"


def test_tier3_unknown_landing_mode_falls_back_to_inherit(seeded):
    ConfigGlobal.objects.create(
        tenant_id=_tenant().id, key=prefkeys.REFERRER_LANDING_MODE, value="teleport"
    )
    prefs = prefkeys.get_referrer_preferences(_tenant().id, None)
    assert prefs[prefkeys.REFERRER_LANDING_MODE] == "", "unknown mode must inherit, not guess"


def test_tier3_referrer_direct_cannot_bypass_the_disclosure_gate(admin_client, monkeypatch):
    """ADR-032: `direct` needs a live /d/{slug}. A per-referrer preference must not be
    a side door around that gate."""
    import dataclasses

    from apps.dashboard import preferences_service as svc
    from gorefer import flags as flags_mod

    monkeypatch.setattr(
        svc, "flags", dataclasses.replace(flags_mod.flags, ENABLE_CUSTOMER_LOGIN=True)
    )
    monkeypatch.setattr(svc, "has_live_disclosure_page", lambda tenant: False)
    admin_client.post(PREFS_URL, _form(referrer_landing_mode="direct"))
    prefs = prefkeys.get_referrer_preferences(_tenant().id, None)
    assert prefs[prefkeys.REFERRER_LANDING_MODE] == "", "direct slipped past ADR-032"


# --- admin-only ------------------------------------------------------------------

def test_routing_not_settable_by_non_admin(seeded):
    User = get_user_model()
    User.objects.create_user(username="joe", password="pw12345!", is_staff=False)
    c = Client()
    c.login(username="joe", password="pw12345!")
    c.post(PREFS_URL, _form(notify_office=""))
    assert prefkeys.notification_routing(_tenant().id)["office"] is True


def test_routing_not_settable_anonymously(seeded):
    Client().post(PREFS_URL, _form(notify_office=""))
    assert prefkeys.notification_routing(_tenant().id)["office"] is True
