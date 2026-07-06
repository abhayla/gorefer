"""Seed idempotency, provider-agnostic program, and admin bootstrap (§5, §8, §10)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management import call_command

from apps.referrals.models import Partner, ProgramRedirectRule, ReferralProgram


def test_seed_program_creates_single_zerodha_row(db):
    call_command("seed_program")
    assert ReferralProgram.objects.count() == 1
    program = ReferralProgram.objects.get()
    assert program.name == "Zerodha"
    partner = Partner.objects.get()
    assert partner.code == "ZMPHZC"
    rule = ProgramRedirectRule.objects.get()
    # Destination template holds the partner-code + client_id placeholders (server-side only).
    assert "{partner_code}" in rule.destination_url_template
    assert "{client_id}" in rule.destination_url_template


def test_seed_program_is_idempotent(db):
    call_command("seed_program")
    call_command("seed_program")
    assert ReferralProgram.objects.count() == 1
    assert Partner.objects.count() == 1
    assert ProgramRedirectRule.objects.count() == 1


def test_bootstrap_admin_idempotent(db, monkeypatch, settings):
    settings.ADMIN_EMAIL = "admin@example.com"
    settings.ADMIN_PASSWORD_HASH = make_password("s3cret-not-committed")
    call_command("bootstrap_admin")
    call_command("bootstrap_admin")  # no-op second time
    User = get_user_model()
    assert User.objects.filter(email="admin@example.com").count() == 1
    user = User.objects.get(email="admin@example.com")
    assert user.is_superuser and user.is_staff
    # Password hash stored verbatim -> the plaintext still verifies.
    assert user.check_password("s3cret-not-committed")


def test_bootstrap_admin_refuses_without_hash(db, settings):
    from django.core.management.base import CommandError

    settings.ADMIN_EMAIL = "admin@example.com"
    settings.ADMIN_PASSWORD_HASH = ""
    with pytest.raises(CommandError):
        call_command("bootstrap_admin")
