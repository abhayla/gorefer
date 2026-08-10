"""T-078 — email as a SECOND, SIMULTANEOUS OTP channel (Zoho Mail SMTP).

WhatsApp OTP delivery runs ~43% (Meta per-user marketing cap), so the same login
code now ALSO goes out by email. The properties that must hold:

  (1) FAN-OUT, not cascade: one challenge attempts BOTH legs, carrying the SAME code;
  (2) ON-FILE ONLY: the address comes from Customer/Zoho keyed by client_id — a
      user-supplied email can never redirect the code;
  (3) GATED: flag off => byte-identical to today (no email at all);
  (4) FAIL-SAFE: no on-file address, or no SMTP config, is a clean skip, not a crash,
      and an email failure never blocks (or is blocked by) the WhatsApp leg;
  (5) SECURITY: the code is still hashed+peppered+single-use+rate-limited, appears in
      the mail body only, and never in a log line;
  (6) copy is CONFIG (§6d / rail E-6) — subject + body resolve from the cascade.

Mail is asserted through Django's locmem backend (`django.core.mail.outbox`) — no
real SMTP is touched anywhere in this file.
"""
import dataclasses
import logging

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.otp import hashing
from apps.otp.adapters import EmailOtpAdapter
from apps.otp.channels import EMAIL_CHANNEL, resolve_channel
from apps.otp.models import OtpChallenge
from apps.otp.ports import STATUS_FAILED, STATUS_QUEUED, STATUS_SUPPRESSED, DeliveryResult
from apps.otp.recipient import resolve_onfile_email
from apps.otp.service import OtpService
from apps.referrals.models import Customer, ReferralProgram
from apps.tenants.models import Tenant

IDENTITY = "RJ4521"
ONFILE_EMAIL = "referrer.onfile@example.com"
ONFILE_PHONE = "919876543210"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _set_flags(monkeypatch, **overrides):
    """Replace the frozen flags snapshot everywhere it was imported by reference."""
    from apps.otp import channels
    from gorefer import flags as flags_mod

    new = dataclasses.replace(flags_mod.flags, **overrides)
    monkeypatch.setattr(flags_mod, "flags", new)
    monkeypatch.setattr(channels, "flags", new)
    return new


@pytest.fixture
def both_on(monkeypatch):
    """OTP master + email leg both on — the live configuration this task ships."""
    _set_flags(monkeypatch, ENABLE_OTP_LOGIN=True, ENABLE_EMAIL_OTP=True)


@pytest.fixture
def otp_only(monkeypatch):
    """Today's production shape: OTP on, email leg OFF."""
    _set_flags(monkeypatch, ENABLE_OTP_LOGIN=True, ENABLE_EMAIL_OTP=False)


@pytest.fixture
def customer_on_file(seeded):
    """A referrer with BOTH channels on file, keyed by client_id."""
    program = ReferralProgram.objects.get(tenant=seeded)
    Customer.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=IDENTITY, first_name="Rajesh", last_name="Joshi",
        mobile="9876543210", email=ONFILE_EMAIL,
    )
    return seeded


def _service(tenant, *, email_resolver=None):
    return OtpService(
        tenant,
        recipient_resolver=lambda i: ONFILE_PHONE,
        email_resolver=email_resolver or (lambda i: resolve_onfile_email(tenant, i)),
    )


def _recover_code(service, result, identity=IDENTITY):
    """Brute-force the plaintext from the stored hash — only possible in a test."""
    ch = OtpChallenge.objects.get(id=result.challenge_id)
    length = service._cfg[prefkeys.OTP_CODE_LENGTH]
    for n in range(10**length):
        cand = str(n).zfill(length)
        if hashing.verify_code(cand, identity=identity, salt=ch.salt, expected_hash=ch.code_hash):
            return cand
    raise AssertionError("could not recover code")


# ------------------------------------------------------------------ (1) fan-out


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_leg_sends_to_the_onfile_address_with_the_code(customer_on_file, both_on):
    svc = _service(customer_on_file)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    assert len(mail.outbox) == 1, "exactly one OTP email per challenge"
    msg = mail.outbox[0]
    assert msg.to == [ONFILE_EMAIL]
    assert code in msg.body, "the emailed message must carry the actual code"
    assert result.email_sent is True
    assert result.email_status == STATUS_QUEUED


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_both_legs_fire_on_one_challenge_with_the_same_code(customer_on_file, both_on, monkeypatch):
    """The defining property: WhatsApp is ATTEMPTED and email is ALSO sent — one
    challenge, one code, two independent channels (not a cascade)."""
    seen = {}

    from apps.otp import adapters as adapters_mod

    real_send = adapters_mod.WatiWhatsAppOtpAdapter.send

    def spy(self, *, recipient, code, ttl_seconds, context):
        seen["wa_code"] = code
        seen["wa_recipient"] = recipient
        return real_send(self, recipient=recipient, code=code, ttl_seconds=ttl_seconds, context=context)

    monkeypatch.setattr(adapters_mod.WatiWhatsAppOtpAdapter, "send", spy)

    svc = _service(customer_on_file)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    assert seen.get("wa_code") == code, "WhatsApp leg did not run with the challenge code"
    assert seen.get("wa_recipient") == ONFILE_PHONE
    assert len(mail.outbox) == 1
    assert code in mail.outbox[0].body, "the two legs must carry the SAME code"
    # And the code the user types verifies — whichever channel they read it from.
    assert svc.verify(IDENTITY, code).ok is True


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_failure_does_not_block_the_email(customer_on_file, both_on, monkeypatch):
    """A dead WhatsApp leg must still get the referrer a code by email — and the
    challenge must report delivered, so the login page does not tell them it failed."""
    from apps.otp import adapters as adapters_mod

    monkeypatch.setattr(
        adapters_mod.WatiWhatsAppOtpAdapter, "send",
        lambda self, **kw: DeliveryResult(status=STATUS_FAILED, error="simulated outage"),
    )
    monkeypatch.setattr(
        adapters_mod.ManualOtpAdapter, "send",
        lambda self, **kw: DeliveryResult(status=STATUS_FAILED, error="simulated outage"),
    )
    svc = _service(customer_on_file)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)

    assert len(mail.outbox) == 1, "email leg must run even when every WhatsApp channel failed"
    assert result.email_sent is True
    assert result.delivered is True, "an emailed code IS a delivered code"


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_failure_does_not_block_whatsapp(customer_on_file, both_on, monkeypatch):
    """The mirror: a raising mail server must not break the WhatsApp leg or the login."""
    from apps.otp import adapters as adapters_mod

    def boom(self, **kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(adapters_mod.EmailOtpAdapter, "send", boom)
    svc = _service(customer_on_file)
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    assert result.email_sent is False
    assert result.email_status == STATUS_FAILED
    # The WhatsApp leg still produced a usable challenge.
    assert result.delivered is True
    assert svc.verify(IDENTITY, code).ok is True


# ------------------------------------------------------- (2) ON-FILE ONLY


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_user_supplied_email_cannot_redirect_the_otp(customer_on_file, both_on):
    """The attack this rule exists for: the client_id is PUBLIC. Even when a hostile
    address is handed to the login flow, the code goes only to the on-file address."""
    attacker = "attacker@evil.example"
    # The view resolves the address from the client_id alone — this is that resolver.
    svc = _service(customer_on_file)
    mail.outbox.clear()
    svc.issue(IDENTITY)

    assert mail.outbox[0].to == [ONFILE_EMAIL]
    assert attacker not in "".join(mail.outbox[0].to)
    # And the resolver itself ignores anything but the client_id: it takes no address
    # argument at all, so there is no parameter through which one could be injected.
    assert resolve_onfile_email(customer_on_file, IDENTITY) == ONFILE_EMAIL
    assert resolve_onfile_email(customer_on_file, attacker) == ""


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_default_email_resolver_fails_closed(customer_on_file, both_on):
    """A caller that forgets to pass an email_resolver sends NOWHERE — never to a
    guessed or derived address."""
    svc = OtpService(customer_on_file, recipient_resolver=lambda i: ONFILE_PHONE)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)
    assert mail.outbox == []
    assert result.email_sent is False


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_no_onfile_email_skips_cleanly_and_whatsapp_still_sends(seeded, both_on, monkeypatch):
    """An unknown/emailless referrer: the email leg skips, nothing raises, and the
    WhatsApp leg is untouched."""
    from apps.otp import adapters as adapters_mod

    program = ReferralProgram.objects.get(tenant=seeded)
    Customer.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=IDENTITY, first_name="No", last_name="Email",
        mobile="9876543210", email="",
    )
    seen = {}
    real_send = adapters_mod.WatiWhatsAppOtpAdapter.send

    def spy(self, *, recipient, code, ttl_seconds, context):
        seen["ran"] = True
        return real_send(self, recipient=recipient, code=code, ttl_seconds=ttl_seconds, context=context)

    monkeypatch.setattr(adapters_mod.WatiWhatsAppOtpAdapter, "send", spy)

    svc = _service(seeded)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)

    assert mail.outbox == []
    assert seen.get("ran") is True, "WhatsApp must still send when there is no email on file"
    assert result.email_sent is False
    assert result.email_status == STATUS_SUPPRESSED
    assert result.delivered is True


def test_zoho_email_is_read_from_the_onfile_contact(seeded, monkeypatch):
    """Source 2: the M9 Zoho READ adapter's Contact.Email (already in the field set)."""
    import apps.config.integration_flags as ifl
    from apps.integrations import ports
    from apps.integrations.zoho.read import LogOnlyZohoReadAdapter

    monkeypatch.setattr(ifl, "resolve_flag", lambda key, **kw: key == ifl.ENABLE_ZOHO_READ)
    # Fixture-backed read adapter (no live creds, no network) — its RJ4521 Contact
    # carries the Email that the M9 field set already pulls.
    monkeypatch.setattr(ports, "get_crm_read_port", lambda: LogOnlyZohoReadAdapter())
    assert resolve_onfile_email(seeded, "RJ4521") == "rajesh.joshi.demo@example.com"
    # Unknown ClientId -> unmatched contact -> "" (never a guess).
    assert resolve_onfile_email(seeded, "ZZ0000") == ""


def test_zoho_read_outage_degrades_to_no_email(seeded, monkeypatch):
    import apps.config.integration_flags as ifl
    from apps.integrations import ports

    monkeypatch.setattr(ifl, "resolve_flag", lambda key, **kw: key == ifl.ENABLE_ZOHO_READ)

    class Exploding:
        def fetch_contact_by_client_id(self, *, client_id):
            raise RuntimeError("zoho down")

    monkeypatch.setattr(ports, "get_crm_read_port", lambda: Exploding())
    assert resolve_onfile_email(seeded, "RJ4521") == ""


# --------------------------------------------------------------- (3) the flag gate


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_flag_off_sends_no_email_at_all(customer_on_file, otp_only):
    """ENABLE_EMAIL_OTP off => today's behaviour exactly: WhatsApp only."""
    svc = _service(customer_on_file)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)

    assert mail.outbox == [], "flag off but an email was sent"
    assert result.email_sent is False
    assert result.email_status == "", "the leg must not even run"
    assert result.delivered is True  # WhatsApp path unchanged


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_flag_on_but_otp_master_off_sends_nothing(customer_on_file, monkeypatch):
    """Demo mode wins: with the OTP master flag off nothing real is sent anywhere."""
    _set_flags(monkeypatch, ENABLE_OTP_LOGIN=False, ENABLE_EMAIL_OTP=True)
    svc = _service(customer_on_file)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)

    assert mail.outbox == []
    assert result.email_sent is False
    assert result.delivery_status == STATUS_SUPPRESSED


# ------------------------------------------------------ (4) SMTP-unset fail-safe


@override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="")
def test_smtp_unconfigured_is_a_clean_noop_not_a_crash(customer_on_file, both_on):
    """The state prod is in until the owner pastes the Zoho app password: SMTP backend
    selected, no host. The leg must skip, not raise, and login must still work."""
    svc = _service(customer_on_file)
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    assert result.email_status == STATUS_SUPPRESSED
    assert result.email_sent is False
    assert result.delivered is True
    assert svc.verify(IDENTITY, code).ok is True


@override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.zoho.in")
def test_configured_smtp_host_is_considered_live(customer_on_file, both_on, monkeypatch):
    """With a host set, the adapter DOES attempt a send (here intercepted, so no
    network call) — proving the no-op above is the unconfigured case only."""
    sent = {}

    def fake_send(self, fail_silently=False):
        sent["to"] = list(self.to)
        return 1

    monkeypatch.setattr("django.core.mail.EmailMessage.send", fake_send)
    svc = _service(customer_on_file)
    result = svc.issue(IDENTITY)

    assert sent.get("to") == [ONFILE_EMAIL]
    assert result.email_sent is True


# --------------------------------------------------------------- (5) security


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_code_is_never_logged_in_plaintext_by_the_email_leg(customer_on_file, both_on, caplog):
    svc = _service(customer_on_file)
    mail.outbox.clear()
    with caplog.at_level(logging.INFO, logger="gorefer.otp"):
        result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert code not in joined, "plaintext OTP code appeared in logs"
    assert "code_len" in joined, "the email adapter should log a length, proving it saw the code"
    # The full on-file address is masked in logs too (audit, not harvest).
    assert ONFILE_EMAIL not in joined


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_db_never_stores_the_plaintext_code(customer_on_file, both_on):
    svc = _service(customer_on_file)
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)
    ch = OtpChallenge.objects.get(id=result.challenge_id)
    assert not any(isinstance(v, str) and code in v for v in ch.__dict__.values() if v)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_one_email_per_challenge_and_the_rate_limiter_covers_it(customer_on_file, both_on):
    """The second channel must not become an amplification vector: the email leg fires
    once per challenge and inherits the existing per-identity hourly cap."""
    tenant = customer_on_file
    set_tenant(prefkeys.OTP_RESEND_COOLDOWN_SECONDS, 0, tenant_id=tenant.id)
    set_tenant(prefkeys.OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR, 3, tenant_id=tenant.id)
    svc = _service(tenant)
    mail.outbox.clear()

    for _ in range(3):
        svc.issue(IDENTITY)
    assert len(mail.outbox) == 3, "exactly one email per issued challenge"

    from apps.otp.service import OtpRateLimited

    with pytest.raises(OtpRateLimited):
        svc.issue(IDENTITY)
    assert len(mail.outbox) == 3, "a rate-limited challenge must send no email"


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_body_states_expiry_and_the_ignore_line_and_carries_no_pii(customer_on_file, both_on):
    svc = _service(customer_on_file)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)
    body = mail.outbox[0].body
    ttl_minutes = max(1, svc._cfg[prefkeys.OTP_CODE_TTL_SECONDS] // 60)

    assert f"{ttl_minutes} minute" in body, "the email must state the live TTL, not a hardcoded one"
    assert "ignore this email" in body.lower()
    assert "Passive Income Financial Solutions" in body, "sender identity line required"
    # Minimal + transactional: no name, no client_id, no phone, no account details.
    assert "Rajesh" not in body
    assert IDENTITY not in body
    assert ONFILE_PHONE not in body
    assert result.email_sent is True


# ------------------------------------------------------------ (6) copy is config


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_subject_and_body_come_from_the_config_cascade(customer_on_file, both_on):
    tenant = customer_on_file
    set_tenant(prefkeys.OTP_EMAIL_SUBJECT, "PIFS code inside", tenant_id=tenant.id)
    set_tenant(
        prefkeys.OTP_EMAIL_BODY_TEMPLATE,
        "CUSTOM-COPY {code} / {minutes}m / {sender_identity}",
        tenant_id=tenant.id,
    )
    svc = _service(tenant)  # built AFTER the override, as the login view does per request
    mail.outbox.clear()
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    assert mail.outbox[0].subject == "PIFS code inside"
    assert mail.outbox[0].body.startswith("CUSTOM-COPY ")
    assert code in mail.outbox[0].body


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_bad_admin_placeholder_falls_back_to_known_good_copy(customer_on_file, both_on):
    """A typo in the body template must never lock anyone out of login."""
    tenant = customer_on_file
    set_tenant(prefkeys.OTP_EMAIL_BODY_TEMPLATE, "broken {nosuchvar}", tenant_id=tenant.id)
    svc = _service(tenant)
    mail.outbox.clear()
    result = svc.issue(IDENTITY)
    code = _recover_code(svc, result)

    assert result.email_sent is True
    assert code in mail.outbox[0].body


# ------------------------------------------------------------- registry + adapter


def test_email_channel_is_registered_and_demo_gated(monkeypatch):
    _set_flags(monkeypatch, ENABLE_OTP_LOGIN=True, ENABLE_EMAIL_OTP=True)
    assert isinstance(resolve_channel(EMAIL_CHANNEL), EmailOtpAdapter)

    from apps.otp.adapters import DemoOtpAdapter

    _set_flags(monkeypatch, ENABLE_OTP_LOGIN=False, ENABLE_EMAIL_OTP=True)
    assert isinstance(resolve_channel(EMAIL_CHANNEL), DemoOtpAdapter)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_adapter_honours_the_shared_port_contract():
    """Same signature + DeliveryResult contract as every other OTP adapter."""
    mail.outbox.clear()
    out = EmailOtpAdapter().send(
        recipient=ONFILE_EMAIL, code="123456", ttl_seconds=300,
        context={"subject": "S", "body_template": "{code}/{minutes}/{sender_identity}"},
    )
    assert isinstance(out, DeliveryResult)
    assert out.status == STATUS_QUEUED
    assert mail.outbox[0].subject == "S"
    assert mail.outbox[0].body.startswith("123456/5/")

    # Blank recipient -> suppressed, never an exception, never a send.
    mail.outbox.clear()
    blank = EmailOtpAdapter().send(recipient="", code="123456", ttl_seconds=300, context={})
    assert blank.status == STATUS_SUPPRESSED
    assert mail.outbox == []
