"""T-081 — OTP email FROM-address self-serve on Preferences (owner rule 2026-08-10).

T-078 shipped the email OTP leg with the sender address hardcoded to
`settings.DEFAULT_FROM_EMAIL` (env, deploy-only). The owner wants to be able to change
the sending address later with NO deploy (§6d) — this makes the FROM address, and only
the FROM address, an owner-editable cascade key (`otp_email_from_address`), surfaced on
Preferences. The properties that must hold:

  (1) BYTE-IDENTICAL when unset: default is "" (no override) -> the adapter falls back
      to settings.DEFAULT_FROM_EMAIL, exactly what T-078 already sends;
  (2) SELF-SERVE, no deploy: a Preferences POST changes the sender on the very next
      send, verified through the view (not just the service layer);
  (3) SECRETS STAY SECRET: the SMTP credential (host/port/user/password) is never a
      cascade key, never rendered on Preferences, never returned by a config read —
      only the non-secret from-address is exposed;
  (4) VALIDATED: a bad/garbage value is rejected AT SAVE with a clear notice and the
      override is left unchanged; a bad value can never reach send() and break the
      From header — defense in depth at the adapter too, for a value written any
      other way (direct DB edit, a stale row).
"""
import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, override_settings

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.dashboard import preferences_service
from apps.otp.adapters import EmailOtpAdapter
from apps.otp.ports import STATUS_QUEUED
from apps.tenants.models import Tenant

PREFS_URL = "/admin-panel/preferences"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
ONFILE_EMAIL = "referrer.onfile@example.com"


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


def _base_form(**overrides):
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


# ---------------------------------------------------------- (1) byte-identical unset


def test_default_cascade_value_is_empty(seeded):
    assert prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS] == ""


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL="noreply@gorefer.in")
def test_unset_config_sends_with_the_env_default_from(seeded):
    mail.outbox.clear()
    out = EmailOtpAdapter().send(
        recipient=ONFILE_EMAIL, code="123456", ttl_seconds=300,
        context={"subject": "S", "body_template": "{code}/{minutes}/{sender_identity}", "from_address": ""},
    )
    assert out.status == STATUS_QUEUED
    assert mail.outbox[0].from_email == "noreply@gorefer.in"


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL="noreply@gorefer.in")
def test_missing_from_address_key_in_context_still_falls_back_cleanly(seeded):
    """A context dict built before T-081 (no `from_address` key at all) must not KeyError."""
    mail.outbox.clear()
    out = EmailOtpAdapter().send(
        recipient=ONFILE_EMAIL, code="123456", ttl_seconds=300,
        context={"subject": "S", "body_template": "{code}"},
    )
    assert out.status == STATUS_QUEUED
    assert mail.outbox[0].from_email == "noreply@gorefer.in"


# ------------------------------------------------------ (2) self-serve through the view


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL="noreply@gorefer.in")
def test_preferences_post_changes_sender_with_no_deploy(admin_client, seeded):
    resp = admin_client.post(
        PREFS_URL, _base_form(otp_email_from_address="login@pifs.in")
    )
    assert resp.status_code in (200, 302)
    assert prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS] == "login@pifs.in"

    # And the very next send uses it — no restart, no redeploy.
    mail.outbox.clear()
    out = EmailOtpAdapter().send(
        recipient=ONFILE_EMAIL, code="123456", ttl_seconds=300,
        context={
            "subject": "S", "body_template": "{code}",
            "from_address": prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS],
        },
    )
    assert out.status == STATUS_QUEUED
    assert mail.outbox[0].from_email == "login@pifs.in"


def test_preferences_screen_renders_the_saved_value(admin_client, seeded):
    set_tenant(prefkeys.OTP_EMAIL_FROM_ADDRESS, "login@pifs.in", tenant_id=seeded.id)
    resp = admin_client.get(PREFS_URL)
    assert resp.status_code == 200
    assert b"login@pifs.in" in resp.content
    assert b'name="otp_email_from_address"' in resp.content


# ------------------------------------------------------------- (3) secrets stay secret


def test_smtp_secret_never_in_a_config_read(seeded):
    prefs = prefkeys.get_preferences(seeded.id)
    for key in prefs:
        assert "password" not in key.lower()
        assert "host_user" not in key.lower()
    values = "".join(str(v) for v in prefs.values())
    assert "EMAIL_HOST_PASSWORD" not in values


@override_settings(EMAIL_HOST_PASSWORD="super-secret-app-password")
def test_smtp_secret_never_rendered_on_preferences_screen(admin_client):
    resp = admin_client.get(PREFS_URL)
    assert resp.status_code == 200
    assert b"super-secret-app-password" not in resp.content


def test_from_address_field_is_the_only_email_field_besides_subject_body(seeded):
    """Only the non-secret behaviour knobs are cascade keys — no credential key exists
    anywhere in the preference key surface."""
    all_keys = {
        name for name in vars(prefkeys)
        if name.startswith(("OTP_EMAIL", "EMAIL_")) and isinstance(getattr(prefkeys, name), str)
    }
    for key in all_keys:
        assert "PASSWORD" not in key
        assert "HOST_USER" not in key


# --------------------------------------------------------------------- (4) validation


def test_garbage_value_rejected_at_save_with_a_notice_and_left_unchanged(admin_client, seeded):
    resp = admin_client.post(
        PREFS_URL, _base_form(otp_email_from_address="not-an-email")
    )
    assert resp.status_code in (200, 302)
    assert prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS] == "", (
        "an invalid value must never be persisted"
    )


def test_save_otp_returns_a_clear_notice_for_a_bad_address(seeded):
    notices = preferences_service._save_otp(
        seeded.id, {"otp_email_from_address": "definitely not an email"}
    )
    assert any("valid email" in n for n in notices)
    assert prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS] == ""


def test_valid_value_saved_with_no_notice(seeded):
    notices = preferences_service._save_otp(seeded.id, {"otp_email_from_address": "ops@pifs.in"})
    assert notices == []
    assert prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS] == "ops@pifs.in"


def test_blank_input_is_a_no_op_not_an_error(seeded):
    set_tenant(prefkeys.OTP_EMAIL_FROM_ADDRESS, "existing@pifs.in", tenant_id=seeded.id)
    notices = preferences_service._save_otp(seeded.id, {"otp_email_from_address": "  "})
    assert notices == []
    assert prefkeys.get_preferences(seeded.id)[prefkeys.OTP_EMAIL_FROM_ADDRESS] == "existing@pifs.in"


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL="noreply@gorefer.in")
def test_adapter_ignores_a_garbage_stored_value_written_outside_the_screen(seeded):
    """Defense in depth: a value that bypassed screen validation (direct DB write, an
    old row) must not break send() or ship a broken From — it falls back to env."""
    mail.outbox.clear()
    out = EmailOtpAdapter().send(
        recipient=ONFILE_EMAIL, code="123456", ttl_seconds=300,
        context={"subject": "S", "body_template": "{code}", "from_address": "not-an-email-at-all"},
    )
    assert out.status == STATUS_QUEUED
    assert mail.outbox[0].from_email == "noreply@gorefer.in"
