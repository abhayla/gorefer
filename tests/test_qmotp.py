"""Q-M-OTP — pluggable OTP channel port (WhatsApp/Wati primary, admin-configurable).

Ports-and-adapters OTP delivery, admin-switchable via the ADR-022 config cascade with
NO code change. Behind ENABLE_OTP_LOGIN=false (demo → log-only). These are the six
acceptance guardrails from S2-03 §15 plus the config-surface wiring:

  (1) primary WhatsApp non-delivery AUTO-CASCADES to the configured fallback;
  (2) code stored HASHED, never logged plaintext, single-use;
  (3) demo mode (flags off) logs the intended send and sends NOTHING;
  (4) switching OTP_PRIMARY_CHANNEL via config takes effect with NO code change;
  (5) expired / used / over-attempt codes are rejected;
  (6) per-tenant + rate-limited.
"""
import logging

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.integrations.wati import status as wstatus
from apps.otp import adapters, hashing
from apps.otp.channels import resolve_channel
from apps.otp.models import OtpChallenge
from apps.otp.ports import (
    STATUS_DELIVERED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SUPPRESSED,
    DeliveryResult,
)
from apps.otp.recipient import resolve_onfile_recipient
from apps.otp.service import OtpRateLimited, OtpService
from apps.referrals.models import Customer, ReferralProgram
from apps.tenants.models import Tenant
from gorefer.flags import flags

IDENTITY = "RJ4521"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _set_flags(monkeypatch, **overrides):
    """Rebuild the frozen flags snapshot with overrides and patch it into every module
    that imported `flags` by reference (the snapshot is frozen, so we replace it)."""
    import dataclasses

    from apps.otp import channels
    from gorefer import flags as flags_mod

    new = dataclasses.replace(flags_mod.flags, **overrides)
    monkeypatch.setattr(flags_mod, "flags", new)
    monkeypatch.setattr(channels, "flags", new)
    # NB: the WATI adapter no longer holds a module-level `flags` to patch — its send
    # gate now reads the RESOLVED integration flag (admin Settings override -> env
    # default), so ENABLE_WATI_SEND is steered through the resolver below rather than
    # by swapping a frozen snapshot into that module.
    if "ENABLE_WATI_SEND" in overrides:
        import apps.config.integration_flags as ifl

        want = overrides["ENABLE_WATI_SEND"]
        monkeypatch.setattr(
            ifl, "resolve_flag",
            lambda key, **kw: want if key == ifl.ENABLE_WATI_SEND else ifl.env_default(key),
        )
    return new


@pytest.fixture
def otp_on(monkeypatch):
    """Turn the OTP master flag on. WATI stays OFF → the WhatsApp adapter runs through
    the M5 log-only Wati adapter (simulates a delivered terminal status) — the whole
    OTP flow is exercised offline with no network call."""
    _set_flags(monkeypatch, ENABLE_OTP_LOGIN=True)


@pytest.fixture
def service(seeded):
    """Service with a known on-file recipient (never a user-typed number)."""
    return OtpService(seeded, recipient_resolver=lambda i: "919876543210")


def _issue_and_read_code(service, identity=IDENTITY):
    """Issue a code and recover the plaintext by brute-forcing against the stored hash
    (only feasible in a test because the code space is small) — the app itself never
    recovers it. Returns (issue_result, plaintext_code)."""
    result = service.issue(identity)
    ch = OtpChallenge.objects.get(id=result.challenge_id)
    length = service._cfg[prefkeys.OTP_CODE_LENGTH]
    for n in range(10**length):
        cand = str(n).zfill(length)
        if hashing.verify_code(cand, identity=identity, salt=ch.salt, expected_hash=ch.code_hash):
            return result, cand
    raise AssertionError("could not recover code")


# ----------------------------------------------------- (2) hashed, single-use, no plaintext


def test_code_stored_hashed_never_plaintext(service, otp_on):
    result, code = _issue_and_read_code(service)
    ch = OtpChallenge.objects.get(id=result.challenge_id)
    # The stored hash is NOT the code, and no plaintext field holds the code.
    assert ch.code_hash and ch.code_hash != code
    assert code not in ch.code_hash
    row = ch.__dict__
    assert not any(isinstance(v, str) and v == code for v in row.values()), "plaintext leaked into a field"


def test_code_never_logged_plaintext(service, otp_on, caplog):
    with caplog.at_level(logging.INFO, logger="gorefer.otp"):
        result, code = _issue_and_read_code(service)
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert code not in joined, "plaintext OTP code appeared in logs"
    # We DO log a length, proving the adapter saw the code but did not print it.
    assert "code_len" in joined


def test_single_use(service, otp_on):
    result, code = _issue_and_read_code(service)
    assert service.verify(IDENTITY, code).ok is True
    # A second use of the same code fails (consumed).
    second = service.verify(IDENTITY, code)
    assert second.ok is False
    assert OtpChallenge.objects.get(id=result.challenge_id).status == OtpChallenge.STATUS_VERIFIED


# ------------------------------------------------ (M4/M5) OTP vs the live Wati contract

def test_otp_adapter_builds_ordered_template_params_and_reconciles(monkeypatch):
    """Fable5 M4: the OTP adapter must pass an ORDERED template_params list (so the
    live Wati adapter can place the code in {{1}}) AND reconcile terminal status by
    mobile+template (the live ack has no id). Capture what send_template receives."""
    from apps.integrations.wati.adapter import DeliveryResult as WatiDelivery
    from apps.integrations.wati.adapter import SendResult
    from apps.otp import adapters as otp_adapters

    captured = {}

    class _FakeWati:
        def send_template(self, *, to, template, params):
            captured["params"] = params
            return SendResult(accepted=True, provider_message_id=None, raw_status="accepted")

        def get_message_status(self, *, provider_message_id, recipient_mobile=None, template=None):
            captured["status_call"] = {"mobile": recipient_mobile, "template": template}
            from apps.integrations.wati import status as st
            return WatiDelivery(status=st.STATUS_DELIVERED, meta_error_code=None, classification=None)

        def get_template_status(self, *, template):
            from apps.integrations.wati.adapter import TemplateStatus
            return TemplateStatus(name=template, status="APPROVED", category="AUTHENTICATION")

    import apps.integrations.wati.adapter as wati_adapter_mod
    monkeypatch.setattr(wati_adapter_mod, "get_wati_adapter", lambda: _FakeWati())
    adapter = otp_adapters.WatiWhatsAppOtpAdapter()
    res = adapter.send(recipient="919999900001", code="123456", ttl_seconds=300,
                       context={"template": "gorefer_login_otp"})
    # Ordered template_params carrying the code (not a bare {"code":...} dict).
    tvars = captured["params"]["template_params"]
    assert isinstance(tvars, list) and tvars and tvars[0]["value"] == "123456"
    # Status reconciled with mobile + template, not the empty id alone.
    assert captured["status_call"]["mobile"] == "919999900001"
    assert captured["status_call"]["template"] == "gorefer_login_otp"
    from apps.otp.ports import STATUS_DELIVERED
    assert res.status == STATUS_DELIVERED


def test_logonly_wati_adapter_redacts_param_values(caplog):
    """Fable5 M5: with OTP on + WATI off, sends route through LogOnlyWatiAdapter, which
    must log param NAMES only — never the OTP code value."""
    from apps.integrations.wati.adapter import LogOnlyWatiAdapter

    with caplog.at_level(logging.INFO, logger="gorefer.wati"):
        LogOnlyWatiAdapter().send_template(
            to="919999900001", template="gorefer_login_otp",
            params={"template_params": [{"name": "code", "value": "654321"}]},
        )
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "654321" not in joined, "plaintext OTP code leaked from the log-only adapter"
    assert "code" in joined  # the NAME is fine to log


# ------------------------------------------------ (1) cascade on primary non-delivery


def test_primary_nondelivery_cascades_to_fallback(service, otp_on, monkeypatch):
    """Force the WhatsApp (primary) adapter to fail its terminal check → the service
    cascades to the configured fallback (manual), which terminates the cascade."""
    from apps.otp import adapters

    def failing_send(self, *, recipient, code, ttl_seconds, context):
        return DeliveryResult(status=STATUS_FAILED, error="forced non-delivery")

    monkeypatch.setattr(adapters.WatiWhatsAppOtpAdapter, "send", failing_send)
    # default config: primary=whatsapp_wati, fallback=[manual]
    result = service.issue(IDENTITY)
    assert result.channel == "manual", "did not cascade to the configured fallback"
    assert result.delivery_status == STATUS_QUEUED  # manual handoff terminal


def test_cascade_falls_through_multiple(service, otp_on, monkeypatch):
    """primary=whatsapp (fail) → sms (stub, fails) → manual (handoff). Order honoured."""
    from apps.otp import adapters

    monkeypatch.setattr(
        adapters.WatiWhatsAppOtpAdapter, "send",
        lambda self, **kw: DeliveryResult(status=STATUS_FAILED, error="x"),
    )
    set_tenant(prefkeys.OTP_FALLBACK_CHANNELS, ["sms", "manual"], tenant_id=service.tenant_id)
    result = service.issue(IDENTITY)
    assert result.channel == "manual"


def test_raising_primary_cascades_not_crashes(service, otp_on, monkeypatch):
    """A channel that RAISES (e.g. live Wati HTTP not wired) must cascade, never crash
    the login flow — and the exception must not leak the code."""
    from apps.otp import adapters

    def boom(self, **kw):
        raise RuntimeError("live send not wired")

    monkeypatch.setattr(adapters.WatiWhatsAppOtpAdapter, "send", boom)
    result = service.issue(IDENTITY)  # must not raise
    assert result.channel == "manual"  # cascaded past the raising primary


# ---------------------------------------------- (3) demo mode logs + sends nothing


def test_demo_mode_sends_nothing(service, caplog):
    """Flags OFF (default) → every channel resolves to the demo adapter: it logs the
    intended send and sends nothing (STATUS_SUPPRESSED)."""
    assert flags.ENABLE_OTP_LOGIN is False
    with caplog.at_level(logging.INFO, logger="gorefer.otp"):
        result = service.issue(IDENTITY)
    assert result.delivery_status == STATUS_SUPPRESSED
    assert result.channel == "whatsapp_wati"  # intended primary, suppressed
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "SUPPRESSED" in logs


def test_demo_adapter_selected_when_flag_off(seeded):
    assert flags.ENABLE_OTP_LOGIN is False
    adapter = resolve_channel("whatsapp_wati")
    assert adapter.__class__.__name__ == "DemoOtpAdapter"


# ------------------------------- (4) switching OTP_PRIMARY_CHANNEL via config, no code


def test_switch_primary_channel_via_config_no_code(service, otp_on, caplog):
    """Changing OTP_PRIMARY_CHANNEL in the cascade (what the Preferences screen writes)
    changes which adapter sends — with NO code change."""
    # Default primary = whatsapp_wati.
    svc1 = OtpService(service.tenant, recipient_resolver=lambda i: "919876543210")
    assert svc1._cfg[prefkeys.OTP_PRIMARY_CHANNEL] == "whatsapp_wati"

    # Admin switches to manual through config.
    set_tenant(prefkeys.OTP_PRIMARY_CHANNEL, "manual", tenant_id=service.tenant_id)
    svc2 = OtpService(service.tenant, recipient_resolver=lambda i: "919876543210")
    result = svc2.issue(IDENTITY)
    assert result.channel == "manual", "config switch did not take effect"


def test_invalid_primary_channel_falls_back_to_default(service):
    """A garbage stored primary never routes to a nonexistent adapter."""
    set_tenant(prefkeys.OTP_PRIMARY_CHANNEL, "carrier-pigeon", tenant_id=service.tenant_id)
    cfg = prefkeys.get_preferences(service.tenant_id)
    assert cfg[prefkeys.OTP_PRIMARY_CHANNEL] == "whatsapp_wati"


# ---------------------------------------- (5) expired / used / over-attempt rejected


def test_expired_code_rejected(service, otp_on):
    result, code = _issue_and_read_code(service)
    ch = OtpChallenge.objects.get(id=result.challenge_id)
    ch.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    ch.save(update_fields=["expires_at"])
    out = service.verify(IDENTITY, code)
    assert out.ok is False and out.reason == "expired"


def test_wrong_then_over_attempt_rejected(service, otp_on):
    set_tenant(prefkeys.OTP_MAX_VERIFY_ATTEMPTS, 3, tenant_id=service.tenant_id)
    svc = OtpService(service.tenant, recipient_resolver=lambda i: "919876543210")
    result, code = _issue_and_read_code(svc)
    for _ in range(3):
        assert svc.verify(IDENTITY, "000000" if code != "000000" else "111111").ok is False
    # Exhausted — even the CORRECT code is now rejected.
    out = svc.verify(IDENTITY, code)
    assert out.ok is False and out.reason in {"exhausted", "no_code"}
    assert OtpChallenge.objects.get(id=result.challenge_id).status == OtpChallenge.STATUS_EXHAUSTED


def test_verify_with_no_active_code(service, otp_on):
    assert service.verify(IDENTITY, "123456").reason == "no_code"


# ------------------------------------------------ (6) per-tenant + rate-limited


def test_rate_limited_per_identity(service, otp_on):
    set_tenant(prefkeys.OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR, 3, tenant_id=service.tenant_id)
    set_tenant(prefkeys.OTP_RESEND_COOLDOWN_SECONDS, 0, tenant_id=service.tenant_id)
    svc = OtpService(service.tenant, recipient_resolver=lambda i: "919876543210")
    for _ in range(3):
        svc.issue(IDENTITY)
    with pytest.raises(OtpRateLimited):
        svc.issue(IDENTITY)


def test_resend_cooldown(service, otp_on):
    set_tenant(prefkeys.OTP_RESEND_COOLDOWN_SECONDS, 60, tenant_id=service.tenant_id)
    svc = OtpService(service.tenant, recipient_resolver=lambda i: "919876543210")
    svc.issue(IDENTITY)
    with pytest.raises(OtpRateLimited):
        svc.issue(IDENTITY)  # within cooldown


def test_per_tenant_isolation(seeded, otp_on):
    """A challenge in tenant A is invisible to a service scoped to tenant B."""
    other = Tenant.objects.create(slug="other", name="Other", is_active=True)
    svc_a = OtpService(seeded, recipient_resolver=lambda i: "919876543210")
    svc_b = OtpService(other, recipient_resolver=lambda i: "919000000000")
    result, code = _issue_and_read_code(svc_a)
    # Tenant B cannot verify tenant A's code (no active challenge in B's scope).
    assert svc_b.verify(IDENTITY, code).reason == "no_code"
    # And rate-limit counts are per-tenant (B issuing does not consume A's budget).
    assert OtpChallenge.objects.filter(tenant=seeded, identity=IDENTITY).count() == 1
    assert OtpChallenge.objects.filter(tenant=other, identity=IDENTITY).count() == 0


# ---------------------------------------------- recipient = ON-FILE only (Path A)


def test_recipient_from_customer_never_user_typed(seeded):
    program = ReferralProgram.objects.filter(tenant=seeded).first()
    Customer.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=IDENTITY, mobile="9876543210",
    )
    assert resolve_onfile_recipient(seeded, IDENTITY) == "919876543210"
    # Unknown client_id → "" (falls back to assisted, never guesses).
    assert resolve_onfile_recipient(seeded, "UNKNOWN99") == ""


# ---------------------------------------------- config seeded + editable on screen


def test_otp_config_keys_seeded(seeded):
    cfg = prefkeys.get_preferences(seeded.id)
    assert cfg[prefkeys.OTP_PRIMARY_CHANNEL] == "whatsapp_wati"
    assert cfg[prefkeys.OTP_FALLBACK_CHANNELS] == ["manual"]
    assert cfg[prefkeys.OTP_CODE_LENGTH] == 6
    assert cfg[prefkeys.OTP_CODE_TTL_SECONDS] == 300
    assert cfg[prefkeys.OTP_MAX_VERIFY_ATTEMPTS] == 5
    assert cfg[prefkeys.OTP_RESEND_COOLDOWN_SECONDS] == 60
    assert cfg[prefkeys.OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR] == 5


@pytest.fixture
def admin_client(seeded):
    from django.contrib.auth import get_user_model
    from django.test import Client

    User = get_user_model()
    User.objects.create_user(
        username="admin@pifs.in", email="admin@pifs.in", password="pw12345!", is_staff=True
    )
    c = Client()
    c.login(username="admin@pifs.in", password="pw12345!")
    return c


def test_preferences_screen_persists_otp_config(admin_client, seeded):
    """The 'easily configurable for admin' requirement: POSTing the Preferences form
    persists the OTP channel/order/limits to the tenant tier (config-over-code)."""
    resp = admin_client.post(
        "/admin-panel/preferences",
        data={
            "landing_mode": "page",
            "otp_primary_channel": "manual",
            "otp_fallback_channels": ["whatsapp_wati", "sms"],
            "otp_whatsapp_template": "gorefer_login_otp_v2",
            "otp_code_length": "6",
            "otp_code_ttl_seconds": "120",
            "otp_max_verify_attempts": "4",
            "otp_resend_cooldown_seconds": "45",
            "otp_rate_limit_per_identity_per_hour": "7",
        },
        **HUMAN,
    )
    assert resp.status_code == 200
    cfg = prefkeys.get_preferences(seeded.id)
    assert cfg[prefkeys.OTP_PRIMARY_CHANNEL] == "manual"
    assert cfg[prefkeys.OTP_FALLBACK_CHANNELS] == ["whatsapp_wati", "sms"]
    assert cfg[prefkeys.OTP_WHATSAPP_TEMPLATE] == "gorefer_login_otp_v2"
    assert cfg[prefkeys.OTP_CODE_TTL_SECONDS] == 120
    assert cfg[prefkeys.OTP_MAX_VERIFY_ATTEMPTS] == 4
    assert cfg[prefkeys.OTP_RESEND_COOLDOWN_SECONDS] == 45
    assert cfg[prefkeys.OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR] == 7


def test_preferences_screen_clamps_bad_otp_values(admin_client, seeded):
    """A bad admin entry (TTL=0, attempts=0) is clamped, never disabling OTP security."""
    admin_client.post(
        "/admin-panel/preferences",
        data={
            "landing_mode": "page",
            "otp_code_ttl_seconds": "0",
            "otp_max_verify_attempts": "0",
        },
        **HUMAN,
    )
    cfg = prefkeys.get_preferences(seeded.id)
    assert cfg[prefkeys.OTP_CODE_TTL_SECONDS] >= 60
    assert cfg[prefkeys.OTP_MAX_VERIFY_ATTEMPTS] >= 1


def _stub_wati_otp_adapter(monkeypatch, *, delivery_status, meta_error_code=None):
    """Patch the Wati adapter the OTP adapter resolves, and record what was sent.

    `WatiWhatsAppOtpAdapter.send()` does `from apps.integrations.wati.adapter import
    get_wati_adapter` INSIDE the method, so the patch target is the SOURCE module — a
    patch on `apps.otp.adapters` would rebind nothing and the live adapter would run.
    The stub returns the REAL `SendResult` / `DeliveryResult` dataclasses so the test is
    checked against the actual adapter contract, not an assumed shape.
    """
    from apps.integrations.wati import adapter as wati_adapter

    sent = {}

    class _Stub:
        def send_template(self, **kw):
            sent.update(kw)
            return wati_adapter.SendResult(
                accepted=True, provider_message_id="", raw_status="accepted"
            )

        def get_message_status(self, **kw):
            return wati_adapter.DeliveryResult(
                status=delivery_status, meta_error_code=meta_error_code, classification=None
            )

        def get_template_status(self, *, template):
            # T-161 pt 15: GuardedMessagingPort now probes approval before every
            # send — the OTP template IS approved in production, so the stub
            # reports it as such (same convention as records_link_send's fakes).
            return wati_adapter.TemplateStatus(name=template, status="APPROVED", category="AUTHENTICATION")

    monkeypatch.setattr(wati_adapter, "get_wati_adapter", lambda: _Stub())
    return sent


def test_whatsapp_otp_not_yet_delivered_is_QUEUED_not_a_failure(monkeypatch):
    """The adapter checked terminal delivery MICROSECONDS after sending.

    WhatsApp delivery takes seconds, so the check always failed and the WhatsApp channel
    always cascaded to `manual`. Found 2026-07-26: OtpChallenge id=1 was the first challenge
    ever recorded on prod and had already fallen back — no login OTP had ever been delivered
    over WhatsApp. Not-yet-delivered must report QUEUED (accepted, unproven), never FAILED.
    """
    # 'accepted' is what the LIVE adapter returns when getMessages has no terminal row yet —
    # the exact status that used to cascade every real login OTP to `manual`.
    _stub_wati_otp_adapter(monkeypatch, delivery_status=wstatus.STATUS_ACCEPTED)
    res = adapters.WatiWhatsAppOtpAdapter().send(
        recipient="919999900002", code="123456", ttl_seconds=300, context={}
    )
    assert res.status == STATUS_QUEUED, f"in-flight delivery must not be a failure, got {res.status}"


def test_whatsapp_otp_sent_but_not_yet_delivered_is_QUEUED(monkeypatch):
    """'sent' is also non-terminal — the message is in flight, not rejected."""
    _stub_wati_otp_adapter(monkeypatch, delivery_status=wstatus.STATUS_SENT)
    res = adapters.WatiWhatsAppOtpAdapter().send(
        recipient="919999900002", code="123456", ttl_seconds=300, context={}
    )
    assert res.status == STATUS_QUEUED


def test_whatsapp_otp_proven_delivery_is_DELIVERED(monkeypatch):
    """The other edge of the split: a terminal delivered status still reports DELIVERED.

    Guards against the fix over-correcting into "everything is QUEUED", which would lose
    the distinction between accepted and proven.
    """
    _stub_wati_otp_adapter(monkeypatch, delivery_status=wstatus.STATUS_DELIVERED)
    res = adapters.WatiWhatsAppOtpAdapter().send(
        recipient="919999900002", code="123456", ttl_seconds=300, context={}
    )
    assert res.status == STATUS_DELIVERED


def test_whatsapp_otp_terminal_failure_still_cascades(monkeypatch):
    """A REAL rejection must still fail so the fallback channel takes over."""
    _stub_wati_otp_adapter(
        monkeypatch, delivery_status=wstatus.STATUS_FAILED, meta_error_code=131049
    )
    res = adapters.WatiWhatsAppOtpAdapter().send(
        recipient="919999900002", code="123456", ttl_seconds=300, context={}
    )
    assert res.status == STATUS_FAILED
    assert "131049" in (res.error or "")
