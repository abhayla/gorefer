"""T-124 W1 — messaging-engine digest/alert config keys.

Covers: each new key resolves to its stated default when unset and to an override
when set (mirrors how apps/config's cascade is exercised elsewhere — set_tenant +
resolve), and the Preferences screen's "Messaging engine" section save/load
round-trips through a real POST.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve, set_tenant
from apps.tenants.resolve import get_bootstrap_tenant


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


@pytest.fixture
def admin_client(tenant):
    User = get_user_model()
    User.objects.create_user(
        username="admin@pifs.in", email="admin@pifs.in", password="pw12345!", is_staff=True
    )
    c = Client()
    c.login(username="admin@pifs.in", password="pw12345!")
    return c


# --- default resolution ---------------------------------------------------------------


@pytest.mark.parametrize("key, default", [
    (prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST, prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT),
    (prefkeys.MESSAGING_DIGEST_RECIPIENTS, prefkeys.MESSAGING_DIGEST_RECIPIENTS_DEFAULT),
    (prefkeys.MESSAGING_DIGEST_ALERTS_ENABLED, prefkeys.MESSAGING_DIGEST_ALERTS_ENABLED_DEFAULT),
    (
        prefkeys.MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT,
        prefkeys.MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT,
    ),
    (prefkeys.MESSAGING_DIGEST_ALERT_RECOVERY_HITS, prefkeys.MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT),
])
def test_key_resolves_to_default_when_unset(tenant, key, default):
    defaults = prefkeys.central_defaults()
    assert resolve(key, tenant_id=tenant.id, default=defaults[key]) == default


@pytest.mark.parametrize("key, override", [
    (prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST, 14),
    (prefkeys.MESSAGING_DIGEST_RECIPIENTS, "919999999999"),
    (prefkeys.MESSAGING_DIGEST_ALERTS_ENABLED, True),
    (prefkeys.MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT, 55),
    (prefkeys.MESSAGING_DIGEST_ALERT_RECOVERY_HITS, 3),
])
def test_key_resolves_to_override_when_set(tenant, key, override):
    set_tenant(key, override, tenant_id=tenant.id)
    defaults = prefkeys.central_defaults()
    assert resolve(key, tenant_id=tenant.id, default=defaults[key]) == override


def test_get_preferences_includes_messaging_engine_keys(tenant):
    prefs = prefkeys.get_preferences(tenant.id)
    assert prefs[prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST] == prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT
    assert prefs[prefkeys.MESSAGING_DIGEST_RECIPIENTS] == prefkeys.MESSAGING_DIGEST_RECIPIENTS_DEFAULT
    assert prefs[prefkeys.MESSAGING_DIGEST_ALERTS_ENABLED] is False


# --- Preferences screen round-trip ------------------------------------------------------


def test_preferences_screen_renders_messaging_engine_section(admin_client):
    resp = admin_client.get("/admin-panel/preferences")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Messaging engine" in html
    assert prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST in html
    assert prefkeys.MESSAGING_DIGEST_RECIPIENTS in html


def test_preferences_post_saves_and_reloads_messaging_engine_fields(admin_client, tenant):
    resp = admin_client.post("/admin-panel/preferences", {
        prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST: "18",
        prefkeys.MESSAGING_DIGEST_RECIPIENTS: "917000000000,918000000000",
        prefkeys.MESSAGING_DIGEST_ALERTS_ENABLED: "on",
        prefkeys.MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT: "45",
        prefkeys.MESSAGING_DIGEST_ALERT_RECOVERY_HITS: "7",
        # Landing mode + other required-by-view fields, so the rest of the form save
        # path doesn't reject the whole POST for unrelated reasons.
        "landing_mode": "page",
    })
    assert resp.status_code == 200
    assert b"Preferences saved" in resp.content

    prefs = prefkeys.get_preferences(tenant.id)
    assert prefs[prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST] == 18
    assert prefs[prefkeys.MESSAGING_DIGEST_RECIPIENTS] == "917000000000,918000000000"
    assert prefs[prefkeys.MESSAGING_DIGEST_ALERTS_ENABLED] is True
    assert prefs[prefkeys.MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT] == 45
    assert prefs[prefkeys.MESSAGING_DIGEST_ALERT_RECOVERY_HITS] == 7

    # A second GET reflects the saved values (the "load" half of round-trip).
    resp2 = admin_client.get("/admin-panel/preferences")
    html = resp2.content.decode()
    assert "917000000000,918000000000" in html


def test_preferences_post_rejects_out_of_range_int_and_keeps_previous(admin_client, tenant):
    set_tenant(prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST, 9, tenant_id=tenant.id)
    resp = admin_client.post("/admin-panel/preferences", {
        prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST: "99",  # out of 0-23 bounds
        "landing_mode": "page",
    })
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "must be between" in html
    prefs = prefkeys.get_preferences(tenant.id)
    assert prefs[prefkeys.MESSAGING_DIGEST_SEND_HOUR_IST] == 9  # unchanged


# --- digest recipients: per-entry mobile-number validation at SAVE time (T-163 pt 31) ---


def test_digest_recipients_rejects_a_bad_entry_and_names_it(admin_client, tenant):
    set_tenant(
        prefkeys.MESSAGING_DIGEST_RECIPIENTS, "919999999999", tenant_id=tenant.id
    )
    resp = admin_client.post("/admin-panel/preferences", {
        prefkeys.MESSAGING_DIGEST_RECIPIENTS: "917000000000, not-a-number",
        "landing_mode": "page",
    })
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Recipient 2" in html
    assert "does not look like a valid mobile number" in html

    # Left unchanged — the whole submitted list is rejected, not partially saved.
    prefs = prefkeys.get_preferences(tenant.id)
    assert prefs[prefkeys.MESSAGING_DIGEST_RECIPIENTS] == "919999999999"


def test_digest_recipients_saves_a_good_comma_separated_list(admin_client, tenant):
    resp = admin_client.post("/admin-panel/preferences", {
        prefkeys.MESSAGING_DIGEST_RECIPIENTS: "917000000000, 9888888888",
        "landing_mode": "page",
    })
    assert resp.status_code == 200
    assert b"Preferences saved" in resp.content

    prefs = prefkeys.get_preferences(tenant.id)
    assert prefs[prefkeys.MESSAGING_DIGEST_RECIPIENTS] == "917000000000, 9888888888"
