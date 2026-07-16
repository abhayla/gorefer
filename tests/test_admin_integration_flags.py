"""Admin Settings — integration flags as checkboxes (DA mission 2026-07-16).

Abhay's ask: flip ENABLE_WATI_SEND / ENABLE_ZOHO_WRITE / ENABLE_ZOHO_READ from the
Settings UI, no .env edit or redeploy. That moves them from env-only into the config
cascade, with env as the fallback default.

The two claims that actually matter, and why:

1. **Prod state is unchanged by shipping this.** A fresh install has no override row,
   so all three still resolve to the env default (OFF). If that were wrong, merging
   this would silently arm real WhatsApp sends and real Zoho writes.
2. **The read-sites obey the resolved value, not raw env.** If a gate kept reading
   `flags.X`, the checkbox would be a LIE — an operator could see "off" while the
   system kept sending. That is worse than having no checkbox at all.

Plus: the confirm-gate on the risky two, off->on only; admin-only; no dead UI.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.config.integration_flags import (
    ENABLE_WATI_SEND,
    ENABLE_ZOHO_READ,
    ENABLE_ZOHO_WRITE,
    INTEGRATION_FLAG_KEYS,
    RISKY_FLAG_KEYS,
    flag_source,
    integration_flags_view,
    resolve_flag,
)
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
    """A full preferences POST body. Checkboxes: present == on, absent == off."""
    data = {
        "landing_mode": "page",
        "referrer_reward_claim": "10% brokerage share + 300 reward points",
        "support_helpline_phone": "+91 73888 82020",
        "wati_business_number": "917080642020",
        "share_channels": ["wa", "copy"],
        "share_show_reward": "on",
        "enable_assisted_referral": "on",
    }
    data.update(overrides)
    return data


# --- 1. shipping this must not change prod state ---------------------------------

def test_no_override_resolves_to_env_default_off(seeded):
    """THE safety claim: a fresh checkbox arms nothing.

    No override row => the env default stands. All three ship OFF, exactly as before.
    """
    assert not ConfigGlobal.objects.filter(key__in=INTEGRATION_FLAG_KEYS).exists()
    for key in INTEGRATION_FLAG_KEYS:
        assert resolve_flag(key, tenant_id=_tenant().id) is False
        assert flag_source(key, tenant_id=_tenant().id) == "env"


def test_env_default_is_honoured_when_no_override(seeded, monkeypatch):
    """With no override, the env is the floor — an env-on flag resolves ON."""
    import apps.config.integration_flags as ifl
    from gorefer import flags as flags_mod

    monkeypatch.setenv("ENABLE_ZOHO_READ", "true")
    monkeypatch.setattr(ifl, "flags", flags_mod.FeatureFlags.from_env())
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is True


def test_override_beats_the_env_default_in_both_directions(seeded, monkeypatch):
    """The override is authoritative — including turning OFF something env has ON.

    The off direction matters most: it is the kill switch for a live problem.
    """
    import apps.config.integration_flags as ifl
    from gorefer import flags as flags_mod

    monkeypatch.setenv("ENABLE_ZOHO_READ", "true")
    monkeypatch.setattr(ifl, "flags", flags_mod.FeatureFlags.from_env())

    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=ENABLE_ZOHO_READ, value=False)
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is False
    assert flag_source(ENABLE_ZOHO_READ, tenant_id=_tenant().id) == "override"


# --- 2. the read-sites must obey the RESOLVED value ------------------------------

def test_zoho_write_adapter_obeys_the_override_not_raw_env(seeded):
    """If get_zoho_adapter() read raw env, the checkbox would be a lie."""
    from apps.integrations.zoho.adapter import LogOnlyZohoAdapter, get_zoho_adapter

    assert isinstance(get_zoho_adapter(), LogOnlyZohoAdapter)  # env default off

    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=ENABLE_ZOHO_WRITE, value=True)
    # Flag on + no creds => the LIVE adapter is selected and refuses to construct.
    # That RuntimeError is the proof the override reached the selector.
    with pytest.raises(RuntimeError, match="not configured"):
        get_zoho_adapter()


def test_zoho_read_adapter_obeys_the_override_not_raw_env(seeded):
    from apps.integrations.zoho.read import LogOnlyZohoReadAdapter, get_zoho_read_adapter

    assert isinstance(get_zoho_read_adapter(), LogOnlyZohoReadAdapter)

    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=ENABLE_ZOHO_READ, value=True)
    with pytest.raises(RuntimeError, match="not configured"):
        get_zoho_read_adapter()


def test_wati_adapter_obeys_the_override_not_raw_env(seeded):
    from apps.integrations.wati.adapter import LogOnlyWatiAdapter, get_wati_adapter

    assert isinstance(get_wati_adapter(), LogOnlyWatiAdapter)

    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=ENABLE_WATI_SEND, value=True)
    # Flag on + no WATI creds => the LIVE adapter is selected and refuses to construct.
    # That refusal is the proof the override reached the selector (a raw-env read would
    # have quietly returned the log-only adapter instead).
    with pytest.raises(RuntimeError):
        get_wati_adapter()


# --- 3. the screen persists the toggles ------------------------------------------

def test_toggle_persists_through_the_screen(admin_client):
    """Zoho READ is the plain (ungated) toggle — no confirm needed."""
    resp = admin_client.post(PREFS_URL, _form(enable_zoho_read="on"))
    assert resp.status_code in (200, 302)
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is True
    assert flag_source(ENABLE_ZOHO_READ, tenant_id=_tenant().id) == "override"


def test_unchecking_persists_off(admin_client):
    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=ENABLE_ZOHO_READ, value=True)
    admin_client.post(PREFS_URL, _form())  # enable_zoho_read absent == off
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is False


# --- 4. the confirm-gate on the risky two ----------------------------------------

@pytest.mark.parametrize("field,key", [
    ("enable_wati_send", ENABLE_WATI_SEND),
    ("enable_zoho_write", ENABLE_ZOHO_WRITE),
])
def test_turning_on_without_confirmation_is_refused(admin_client, field, key):
    """Server-side gate. The dialog is UI convenience; a hand-rolled POST (or a JS-off
    browser) must NOT be able to start real sends/writes without confirming."""
    admin_client.post(PREFS_URL, _form(**{field: "on"}))  # no confirm_* field
    assert resolve_flag(key, tenant_id=_tenant().id) is False, (
        f"{key} turned ON without confirmation"
    )


@pytest.mark.parametrize("field,key", [
    ("enable_wati_send", ENABLE_WATI_SEND),
    ("enable_zoho_write", ENABLE_ZOHO_WRITE),
])
def test_turning_on_with_confirmation_succeeds(admin_client, field, key):
    admin_client.post(PREFS_URL, _form(**{field: "on", f"confirm_{field}": "on"}))
    assert resolve_flag(key, tenant_id=_tenant().id) is True


@pytest.mark.parametrize("field,key", [
    ("enable_wati_send", ENABLE_WATI_SEND),
    ("enable_zoho_write", ENABLE_ZOHO_WRITE),
])
def test_turning_OFF_is_never_gated(admin_client, field, key):
    """The kill switch must never need a confirmation. An operator stopping a live
    problem cannot be made to jump through a dialog."""
    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=key, value=True)
    admin_client.post(PREFS_URL, _form())  # field absent == off, no confirm sent
    assert resolve_flag(key, tenant_id=_tenant().id) is False


def test_already_on_stays_on_without_reconfirming(admin_client):
    """Not a transition => not re-gated. Otherwise every unrelated save would either
    nag or silently switch sending off."""
    ConfigGlobal.objects.create(tenant_id=_tenant().id, key=ENABLE_WATI_SEND, value=True)
    admin_client.post(PREFS_URL, _form(enable_wati_send="on"))  # no confirm_*
    assert resolve_flag(ENABLE_WATI_SEND, tenant_id=_tenant().id) is True


def test_zoho_read_is_not_confirm_gated(admin_client):
    """Read-only: it cannot send or write anything, so a dialog would be noise."""
    assert ENABLE_ZOHO_READ not in RISKY_FLAG_KEYS
    admin_client.post(PREFS_URL, _form(enable_zoho_read="on"))  # no confirm_*
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is True


def test_refusal_surfaces_a_notice_rather_than_failing_silently(admin_client):
    from apps.dashboard.preferences_service import save_preferences

    notices = save_preferences(_tenant(), _form(enable_wati_send="on"))
    assert any("NOT turned on" in n for n in notices), (
        "a refused toggle must tell the operator why, not silently no-op"
    )


# --- 5. the screen renders value + source ----------------------------------------

def test_view_reports_value_and_source(seeded):
    rows = {r["key"]: r for r in integration_flags_view(_tenant().id)}
    assert set(rows) == set(INTEGRATION_FLAG_KEYS)
    assert rows[ENABLE_ZOHO_READ]["source"] == "env"
    assert rows[ENABLE_ZOHO_READ]["value"] is False
    assert rows[ENABLE_WATI_SEND]["requires_confirm"] is True
    assert rows[ENABLE_ZOHO_READ]["requires_confirm"] is False


def test_screen_renders_the_three_toggles(admin_client):
    body = admin_client.get(PREFS_URL).content.decode()
    for field in ("enable_wati_send", "enable_zoho_write", "enable_zoho_read"):
        assert f'name="{field}"' in body, f"{field} checkbox missing from the screen"


def test_no_dead_ui_customer_login_and_otp_are_not_exposed(admin_client):
    """Constitution §4: expose only what works. These features have not shipped, so
    their flags must not appear as toggles."""
    body = admin_client.get(PREFS_URL).content.decode()
    assert 'name="enable_customer_login"' not in body
    assert 'name="enable_otp_login"' not in body


# --- 6. admin-only ---------------------------------------------------------------

def test_flags_are_not_settable_by_a_non_admin(seeded):
    User = get_user_model()
    User.objects.create_user(username="joe", password="pw12345!", is_staff=False)
    c = Client()
    c.login(username="joe", password="pw12345!")
    c.post(PREFS_URL, _form(enable_zoho_read="on"))
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is False


def test_anonymous_cannot_set_flags(seeded):
    Client().post(PREFS_URL, _form(enable_zoho_read="on"))
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is False


# --- 7. fail-safe ----------------------------------------------------------------

def test_resolution_failure_falls_back_to_env_default(seeded, monkeypatch):
    """A broken lookup must never crash the redirect path — and must fall back to the
    deployed default, which can never silently turn an integration ON."""
    import apps.config.integration_flags as ifl

    def boom(*a, **kw):
        raise RuntimeError("db gone")

    monkeypatch.setattr(ifl, "_override_row", boom)
    assert resolve_flag(ENABLE_ZOHO_READ, tenant_id=_tenant().id) is False
    assert flag_source(ENABLE_ZOHO_READ, tenant_id=_tenant().id) == "env"
