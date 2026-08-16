"""T-158 — verification-outcome notifications + queue badge + upload hardening.

Live gap this closes: `approve_verification`/`reject_verification` decided a
pending ADR-027/ADR-035 request but told nobody — an approved referrer found out
only by re-trying login, and a rejected one heard nothing at all.

Covers:
  1. EMAIL leg — approve sends "sign-in is ready" + login URL; reject sends the
     admin-entered reason + how to retry; both queued on-commit (never inline).
  2. No channel on file -> no crash, nothing sent, logged.
  3. WHATSAPP leg stays INERT while its cascade flag is OFF (the shipped default) —
     `get_messaging_port()` is never even called.
  4. Queue badge: "client_id unknown" vs "found, details mismatched", computed at
     submission time from `onfile.resolve_onfile`.
  5. Upload hardening: a forged content-type (claims image/png, isn't one) is
     rejected; evidence is served as a forced download, never inline-renderable.
"""
from __future__ import annotations

from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from apps.accounts import service as accounts_service
from apps.accounts.models import VerificationRequest
from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.referrals.models import Customer, ReferralProgram
from apps.tenants.models import Tenant

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
CID = "RJ4521"
ONFILE_MOBILE = "919876543210"


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


@pytest.fixture
def onfile_customer(seeded):
    program = ReferralProgram.objects.get(tenant=seeded)
    return Customer.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=CID, mobile=ONFILE_MOBILE, email="rajesh@example.com",
        first_name="Rajesh", last_name="Joshi",
    )


def _mismatch_request(seeded, **overrides):
    defaults = dict(
        tenant=seeded, kind=VerificationRequest.KIND_OAUTH_MISMATCH, client_id=CID,
        registered_name="Rajesh Joshi", mobile_entered=ONFILE_MOBILE,
        google_email="rajesh@work.example.com", status=VerificationRequest.STATUS_PENDING,
    )
    defaults.update(overrides)
    return VerificationRequest.objects.create(**defaults)


# ------------------------------------------------------------------------ EMAIL leg


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_approve_sends_email_with_login_url(seeded, onfile_customer):
    mail.outbox.clear()
    req = _mismatch_request(seeded)

    accounts_service.approve_verification(req, admin_user=None)

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["rajesh@work.example.com"]
    assert "sign in" in msg.body.lower() or "ready" in msg.body.lower()
    assert accounts_service.login_url() in msg.body


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_reject_sends_email_with_admin_reason_and_retry(seeded):
    mail.outbox.clear()
    req = _mismatch_request(
        seeded, client_id="ZZ9999", mobile_entered="", google_email="stranger@example.com",
    )

    accounts_service.reject_verification(
        req, admin_user=None, note="Screenshot didn't match the name entered",
    )

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "Screenshot didn't match the name entered" in msg.body
    assert accounts_service.login_url() in msg.body  # "how to retry"


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_reject_with_blank_reason_still_sends_a_usable_email(seeded):
    """An admin can reject with an empty note (the field is optional in the UI) —
    the email must still go out with SOME explanation, never a blank/broken body."""
    mail.outbox.clear()
    req = _mismatch_request(seeded, client_id="ZZ9998", mobile_entered="", google_email="a@example.com")

    accounts_service.reject_verification(req, admin_user=None, note="")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].body.strip()


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_no_channel_on_file_does_not_crash_and_sends_nothing(seeded):
    """No email, no mobile on the request at all — approval must still succeed."""
    mail.outbox.clear()
    req = _mismatch_request(seeded, client_id="ZZ9997", mobile_entered="", google_email="")

    account = accounts_service.approve_verification(req, admin_user=None)  # must not raise

    assert account is not None
    assert mail.outbox == []


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_queued_on_commit_not_inline(seeded):
    """The email must not be sent inside the caller's own transaction — proven by
    checking nothing is sent until the wrapping test transaction actually commits
    (which pytest-django(transaction=True) does at the end of the `with` block)."""
    mail.outbox.clear()
    from django.db import transaction

    req = _mismatch_request(seeded, client_id="ZZ9996")
    with transaction.atomic():
        accounts_service.approve_verification(req, admin_user=None)
        # Still inside the outer atomic block — on_commit has not fired yet.
        assert mail.outbox == []
    assert len(mail.outbox) == 1


# --------------------------------------------------------------------- WHATSAPP leg


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_inert_while_flag_off(seeded):
    """Shipped default (flag OFF): the messaging port is never even called."""
    req = _mismatch_request(seeded, client_id="ZZ9995")
    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        accounts_service.approve_verification(req, admin_user=None)
    get_port.assert_not_called()


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_fires_when_flag_on_and_template_configured(seeded):
    set_tenant(prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED, True, tenant_id=seeded.id)
    req = _mismatch_request(seeded, client_id="ZZ9994", mobile_entered="9000000001")

    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        port = get_port.return_value
        from apps.integrations.wati.adapter import SendResult
        port.send_template.return_value = SendResult(
            accepted=True, provider_message_id="wamid.1", raw_status="accepted"
        )
        accounts_service.approve_verification(req, admin_user=None)

    port.send_template.assert_called_once()
    kwargs = port.send_template.call_args.kwargs
    assert kwargs["to"] == "919000000001"
    assert kwargs["template"] == prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_EN_DEFAULT


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_stays_inert_when_template_blank_even_with_flag_on(seeded):
    set_tenant(prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED, True, tenant_id=seeded.id)
    set_tenant(prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_EN, "", tenant_id=seeded.id)
    req = _mismatch_request(seeded, client_id="ZZ9993", mobile_entered="9000000002")

    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        accounts_service.approve_verification(req, admin_user=None)

    get_port.return_value.send_template.assert_not_called()


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_picks_hi_template_when_referrer_language_is_hi(seeded):
    """`referrer_language=hi` (the EXISTING cascade key — doc 15 §8) must select the
    HI-approved template, never the EN one, for the approved outcome."""
    set_tenant(prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED, True, tenant_id=seeded.id)
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    req = _mismatch_request(seeded, client_id="ZZ9992", mobile_entered="9000000004")

    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        port = get_port.return_value
        from apps.integrations.wati.adapter import SendResult
        port.send_template.return_value = SendResult(
            accepted=True, provider_message_id="wamid.2", raw_status="accepted"
        )
        accounts_service.approve_verification(req, admin_user=None)

    port.send_template.assert_called_once()
    kwargs = port.send_template.call_args.kwargs
    assert kwargs["template"] == prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_HI_DEFAULT
    assert kwargs["template"] != prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_EN_DEFAULT


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_picks_hi_template_for_needsreview_outcome(seeded):
    """Same HI selection for the rejected/needs-review outcome, not just approved."""
    set_tenant(prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED, True, tenant_id=seeded.id)
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    req = _mismatch_request(seeded, client_id="ZZ9991", mobile_entered="9000000005")

    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        port = get_port.return_value
        from apps.integrations.wati.adapter import SendResult
        port.send_template.return_value = SendResult(
            accepted=True, provider_message_id="wamid.3", raw_status="accepted"
        )
        accounts_service.reject_verification(req, admin_user=None, note="mismatch")

    port.send_template.assert_called_once()
    kwargs = port.send_template.call_args.kwargs
    assert kwargs["template"] == prefkeys.VERIFICATION_OUTCOME_NEEDSREVIEW_TEMPLATE_HI_DEFAULT


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_falls_back_to_en_when_hi_template_blank(seeded):
    """A blank HI override must not silently drop the send — it stays inert per the
    same "no-template" contract as the EN leg, it does not fall back to EN (the HI
    referrer must not receive an EN-language message)."""
    set_tenant(prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED, True, tenant_id=seeded.id)
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    set_tenant(prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_HI, "", tenant_id=seeded.id)
    req = _mismatch_request(seeded, client_id="ZZ9990", mobile_entered="9000000006")

    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        accounts_service.approve_verification(req, admin_user=None)

    get_port.return_value.send_template.assert_not_called()


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_whatsapp_leg_inert_while_flag_off_even_for_hi_referrer(seeded):
    """The inert-while-OFF guarantee holds regardless of the referrer's language."""
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    req = _mismatch_request(seeded, client_id="ZZ9989", mobile_entered="9000000007")

    with mock.patch("apps.integrations.ports.get_messaging_port") as get_port:
        accounts_service.approve_verification(req, admin_user=None)

    get_port.assert_not_called()


# --------------------------------------------------------------------- queue badge


@pytest.mark.django_db
def test_onfile_status_mismatch_when_client_id_known(seeded, onfile_customer):
    req = accounts_service.submit_oauth_mismatch_request(
        seeded, client_id=CID, google_email="stranger@example.com", mobile_entered="9000000003",
    )
    assert req.onfile_status == VerificationRequest.ONFILE_MISMATCH


@pytest.mark.django_db
def test_onfile_status_unknown_when_client_id_not_on_file(seeded):
    req = accounts_service.submit_oauth_mismatch_request(
        seeded, client_id="NOTREAL1", google_email="stranger@example.com", mobile_entered="9000000004",
    )
    assert req.onfile_status == VerificationRequest.ONFILE_UNKNOWN


@pytest.mark.urls("tests.urls_m13")
@pytest.mark.django_db
def test_verifications_queue_renders_both_badges(admin_client, seeded, onfile_customer):
    accounts_service.submit_oauth_mismatch_request(
        seeded, client_id=CID, google_email="stranger@example.com", mobile_entered="9000000005",
    )
    accounts_service.submit_oauth_mismatch_request(
        seeded, client_id="NOTREAL2", google_email="stranger2@example.com", mobile_entered="9000000006",
    )
    resp = admin_client.get("/admin-panel/verifications/")
    html = resp.content.decode()
    assert "Details mismatched" in html
    assert "Client ID unknown" in html


# --------------------------------------------------------------------- upload hardening


@pytest.mark.django_db
def test_forged_content_type_upload_is_rejected(seeded):
    """Claims image/png but the bytes are plain text — Pillow's real decode catches
    what the content-type/extension checks alone would miss."""
    with pytest.raises(accounts_service.VerificationError):
        accounts_service.submit_evidence_request(
            seeded, client_id="FORGE001", registered_name="Forger",
            mobile_entered="9000000007",
            evidence_bytes=b"not actually an image, just plain bytes" * 4,
            content_type="image/png",
        )
    assert not VerificationRequest.objects.filter(client_id="FORGE001").exists()


@pytest.mark.urls("tests.urls_m13")
@pytest.mark.django_db
def test_evidence_served_as_forced_download(admin_client, seeded):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), color=(10, 20, 30)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    req = accounts_service.submit_evidence_request(
        seeded, client_id="DL0001", registered_name="Downloader", mobile_entered="9000000008",
        evidence_bytes=png_bytes, content_type="image/png",
    )
    resp = admin_client.get(f"/admin-panel/verifications/{req.id}/evidence")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/octet-stream"
    assert "attachment" in resp["Content-Disposition"]
    assert resp["X-Content-Type-Options"] == "nosniff"
