"""M13 — referrer self-service login (OAuth primary + OTP fallback + Path B).

Contract: docs/sprint2/S2-05-M13-Referrer-Login-Goal-Contract.md. Guardrails:
  - the OTP request accepts ONLY a Client ID; any phone field is rejected (ADR-035);
  - the OTP recipient is resolved ON-FILE (Customer → Zoho READ), never typed;
  - own-record scoping: a referrer session renders only its bound client_id;
  - self view masks IP (PII_MASK_FOR_CUSTOMER_VIEW); admin view stays full;
  - evidence (Path B) is size/type-capped and PURGED on approve AND reject (DPDP);
  - no partner code / raw Zerodha URL in any login-surface response (guardrail #3);
  - with ENABLE_CUSTOMER_LOGIN off (default), NONE of these URLs exist (no dead UI).
"""
import dataclasses

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.accounts import oauth
from apps.accounts import service as accounts_service
from apps.accounts.models import ReferrerAccount, VerificationRequest
from apps.accounts.onfile import OnFileRecord, auto_bind_matches
from apps.config import preferences as prefkeys
from apps.otp import hashing
from apps.otp.models import OtpChallenge
from apps.otp.recipient import resolve_onfile_recipient
from apps.referrals.models import Customer, ReferralProgram
from apps.tenants.models import Tenant

CID = "RJ4521"
ONFILE_MOBILE = "919876543210"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64  # enough bytes to be a plausible tiny upload


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


@pytest.fixture
def onfile_customer(seeded):
    """RJ4521 is on file as a PIFS customer (the resolver's FIRST source)."""
    program = ReferralProgram.objects.get(tenant=seeded)
    return Customer.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=CID, mobile=ONFILE_MOBILE, email="rajesh@example.com",
        first_name="Rajesh", last_name="Joshi",
    )


@pytest.fixture
def otp_on(monkeypatch):
    """Flip ENABLE_OTP_LOGIN in every module holding the frozen snapshot by name."""
    from apps.accounts import views as accounts_views
    from apps.otp import channels
    from gorefer import flags as flags_mod

    new = dataclasses.replace(flags_mod.flags, ENABLE_OTP_LOGIN=True)
    monkeypatch.setattr(flags_mod, "flags", new)
    monkeypatch.setattr(channels, "flags", new)
    monkeypatch.setattr(accounts_views, "flags", new)
    return new


@pytest.fixture
def oauth_conf(settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "test-secret"
    return settings


def _recover_code(challenge: OtpChallenge, length: int) -> str:
    for n in range(10**length):
        cand = str(n).zfill(length)
        if hashing.verify_code(
            cand, identity=challenge.identity, salt=challenge.salt,
            expected_hash=challenge.code_hash,
        ):
            return cand
    raise AssertionError("could not recover code")


def _login_via_otp(client, seeded):
    """Drive the real OTP door end-to-end; returns the bound account."""
    resp = client.post("/login/otp/request", {"client_id": CID}, **HUMAN)
    assert resp.status_code == 200
    ch = OtpChallenge.objects.get(tenant=seeded, identity=CID, status="active")
    code = _recover_code(ch, prefkeys.get_preferences(seeded.id)[prefkeys.OTP_CODE_LENGTH])
    resp = client.post("/login/otp/verify", {"client_id": CID, "code": code}, **HUMAN)
    assert resp.status_code == 302 and resp["Location"] == "/my/referrals"
    return ReferrerAccount.objects.get(tenant=seeded, client_id=CID)


# ------------------------------------------------- flag OFF: the surface doesn't exist


def test_login_surface_absent_when_flag_off(client, db):
    """Default flags (ENABLE_CUSTOMER_LOGIN=false): no login URL, no dead UI."""
    for url in ("/login/", "/my/referrals", "/login/verify-ownership"):
        assert client.get(url).status_code == 404, url


def test_home_has_no_referrer_login_link_when_flag_off(client, db):
    html = client.get("/").content.decode()
    assert "My Referrals — sign in" not in html


# ----------------------------------------------------------- OTP door (Path A, ADR-035)


@pytest.mark.urls("tests.urls_m13")
def test_otp_request_rejects_any_typed_phone(client, seeded, onfile_customer, otp_on):
    """ADR-035 hard rule: a phone field in the OTP request is refused outright."""
    resp = client.post(
        "/login/otp/request", {"client_id": CID, "mobile": "9999999999"}, **HUMAN
    )
    assert resp.status_code == 400
    assert not OtpChallenge.objects.exists()


@pytest.mark.urls("tests.urls_m13")
def test_otp_goes_to_onfile_number_never_typed(client, seeded, onfile_customer, otp_on):
    resp = client.post("/login/otp/request", {"client_id": CID}, **HUMAN)
    assert resp.status_code == 200
    ch = OtpChallenge.objects.get(tenant=seeded, identity=CID)
    assert ch.recipient == ONFILE_MOBILE
    # The page confirms the masked recipient but NEVER the full number.
    html = resp.content.decode()
    assert ONFILE_MOBILE not in html and ONFILE_MOBILE[2:] not in html
    assert ONFILE_MOBILE[-3:] in html


@pytest.mark.urls("tests.urls_m13")
def test_otp_unknown_client_id_offers_path_b(client, seeded, otp_on):
    """No on-file channel → Path B, never a guessed number (ADR-035)."""
    resp = client.post("/login/otp/request", {"client_id": "ZZ9999"}, **HUMAN)
    assert resp.status_code == 302
    assert resp["Location"].startswith("/login/verify-ownership")
    assert not OtpChallenge.objects.exists()


@pytest.mark.urls("tests.urls_m13")
def test_otp_verify_binds_and_logs_in(client, seeded, onfile_customer, otp_on):
    account = _login_via_otp(client, seeded)
    assert account.bound_via == ReferrerAccount.BOUND_VIA_OTP
    assert account.mobile == ONFILE_MOBILE
    assert not account.user.is_staff
    assert not account.user.has_usable_password()  # no password door, ever
    resp = client.get("/my/referrals")
    assert resp.status_code == 200


@pytest.mark.urls("tests.urls_m13")
def test_otp_wrong_code_does_not_login(client, seeded, onfile_customer, otp_on):
    client.post("/login/otp/request", {"client_id": CID}, **HUMAN)
    resp = client.post("/login/otp/verify", {"client_id": CID, "code": "000000x"}, **HUMAN)
    assert resp.status_code == 400
    assert not ReferrerAccount.objects.exists()
    assert client.get("/my/referrals").status_code == 302  # still anonymous


@pytest.mark.urls("tests.urls_m13")
def test_otp_door_404_when_otp_flag_off(client, seeded, onfile_customer):
    """Customer-login on but ENABLE_OTP_LOGIN off → the OTP endpoints don't serve."""
    assert client.post("/login/otp/request", {"client_id": CID}, **HUMAN).status_code == 404


# ------------------------------------------------- Q-M-OTP-2: Zoho on-file resolution


def test_onfile_resolver_reads_zoho_when_enabled(seeded, monkeypatch):
    """Q-M-OTP-2 wired: Customer miss → Zoho Contact Mobile (fixture adapter), normalized."""
    import apps.config.integration_flags as ifl
    from apps.integrations.zoho import read as zoho_read

    monkeypatch.setattr(
        ifl, "resolve_flag",
        lambda key, **kw: True if key == ifl.ENABLE_ZOHO_READ else ifl.env_default(key),
    )
    monkeypatch.setattr(zoho_read, "get_zoho_read_adapter", zoho_read.LogOnlyZohoReadAdapter)
    assert resolve_onfile_recipient(seeded, CID) == "919876504321"  # fixture Mobile, 91-prefixed
    assert resolve_onfile_recipient(seeded, "ZZ9999") == ""  # unmatched → Path B, never guessed


def test_onfile_resolver_stays_dark_when_zoho_read_off(seeded):
    assert resolve_onfile_recipient(seeded, CID) == ""


# ----------------------------------------------------- Google OAuth door (ADR-027)


@pytest.mark.urls("tests.urls_m13")
def test_oauth_start_404_without_credentials(client, db):
    assert client.get("/login/google/start").status_code == 404


@pytest.mark.urls("tests.urls_m13")
def test_oauth_start_redirects_to_google_with_state(client, db, oauth_conf):
    resp = client.get("/login/google/start")
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge=" in resp["Location"]
    assert client.session[oauth.SESSION_STATE] in resp["Location"]


@pytest.mark.urls("tests.urls_m13")
def test_oauth_callback_rejects_forged_state(client, db, oauth_conf):
    client.get("/login/google/start")
    resp = client.get("/login/google/callback", {"code": "abc", "state": "FORGED"})
    assert resp.status_code == 400


def _fake_google(monkeypatch, email="rajesh@example.com"):
    monkeypatch.setattr(oauth, "_post_form", lambda url, fields: {"access_token": "tok"})
    monkeypatch.setattr(
        oauth, "_get_json",
        lambda url, bearer: {"email": email, "email_verified": True, "name": "Rajesh", "sub": "g1"},
    )


def _oauth_to_bind(client, monkeypatch, email="rajesh@example.com"):
    _fake_google(monkeypatch, email)
    client.get("/login/google/start")
    state = client.session[oauth.SESSION_STATE]
    resp = client.get("/login/google/callback", {"code": "abc", "state": state})
    return resp


@pytest.mark.urls("tests.urls_m13")
def test_oauth_first_login_auto_binds_on_email_match(
    client, seeded, onfile_customer, oauth_conf, monkeypatch
):
    """ADR-027: Google email matches the on-file email → auto-bind, no queue."""
    resp = _oauth_to_bind(client, monkeypatch)
    assert resp.status_code == 302 and resp["Location"] == "/login/bind"
    resp = client.post("/login/bind", {"client_id": CID})
    assert resp.status_code == 302 and resp["Location"] == "/my/referrals"
    account = ReferrerAccount.objects.get(tenant=seeded, client_id=CID)
    assert account.bound_via == ReferrerAccount.BOUND_VIA_OAUTH_AUTO
    assert account.google_email == "rajesh@example.com"
    assert not VerificationRequest.objects.exists()


@pytest.mark.urls("tests.urls_m13")
def test_oauth_binds_on_mobile_match_when_email_differs(
    client, seeded, onfile_customer, oauth_conf, monkeypatch
):
    resp = _oauth_to_bind(client, monkeypatch, email="other@example.com")
    assert resp["Location"] == "/login/bind"
    resp = client.post("/login/bind", {"client_id": CID, "mobile": "98765 43210"})
    assert resp.status_code == 302 and resp["Location"] == "/my/referrals"


@pytest.mark.urls("tests.urls_m13")
def test_oauth_mismatch_goes_to_admin_queue_not_bind(
    client, seeded, onfile_customer, oauth_conf, monkeypatch
):
    """ADR-027: no match → pending-verification, NEVER a silent bind."""
    _oauth_to_bind(client, monkeypatch, email="stranger@example.com")
    resp = client.post("/login/bind", {"client_id": CID, "mobile": "9000000000"})
    assert resp.status_code == 200 and b"pending" in resp.content.lower()
    assert not ReferrerAccount.objects.exists()
    req = VerificationRequest.objects.get()
    assert req.kind == VerificationRequest.KIND_OAUTH_MISMATCH
    assert req.status == VerificationRequest.STATUS_PENDING


@pytest.mark.urls("tests.urls_m13")
def test_oauth_returning_account_skips_bind(client, seeded, onfile_customer, oauth_conf, monkeypatch):
    accounts_service.get_or_create_account(
        seeded, CID, bound_via=ReferrerAccount.BOUND_VIA_OAUTH_AUTO,
        google_email="rajesh@example.com",
    )
    resp = _oauth_to_bind(client, monkeypatch)
    assert resp.status_code == 302 and resp["Location"] == "/my/referrals"


def test_auto_bind_never_matches_empty_onfile():
    """Empty on-file values must never 'match' empty/any input."""
    empty = OnFileRecord(client_id=CID)
    assert not auto_bind_matches(empty, google_email="", entered_mobile="")
    assert not auto_bind_matches(empty, google_email="a@b.c", entered_mobile="9876543210")


# ------------------------------------------------------------- Path B (evidence, DPDP)


@pytest.mark.urls("tests.urls_m13")
def test_pathb_upload_and_admin_approve_binds_and_purges(
    client, admin_client, seeded, otp_on
):
    up = SimpleUploadedFile("console.png", PNG, content_type="image/png")
    resp = client.post(
        "/login/verify-ownership",
        {"client_id": "ZZ9999", "registered_name": "Zed Zaveri",
         "mobile": "90000 00001", "evidence": up},
        **HUMAN,
    )
    assert resp.status_code == 200 and b"pending" in resp.content.lower()
    req = VerificationRequest.objects.get()
    assert req.evidence is not None and req.evidence_size == len(PNG)

    # Staff can view the evidence while pending; it is never publicly routed.
    ev = admin_client.get(f"/admin-panel/verifications/{req.id}/evidence")
    assert ev.status_code == 200 and ev["Content-Type"] == "image/png"

    resp = admin_client.post(
        f"/admin-panel/verifications/{req.id}/decide", {"action": "approve"}
    )
    assert resp.status_code == 302
    req.refresh_from_db()
    assert req.status == VerificationRequest.STATUS_APPROVED
    assert req.evidence is None and req.evidence_purged_at is not None  # DPDP purge
    # Bound + on file: the account exists and the NEXT login is Path A (Customer row).
    account = ReferrerAccount.objects.get(tenant=seeded, client_id="ZZ9999")
    assert account.bound_via == ReferrerAccount.BOUND_VIA_ADMIN
    assert resolve_onfile_recipient(seeded, "ZZ9999") == "919000000001"
    # Purged evidence 404s even for staff.
    assert admin_client.get(f"/admin-panel/verifications/{req.id}/evidence").status_code == 404


@pytest.mark.urls("tests.urls_m13")
def test_pathb_reject_purges_and_does_not_bind(client, admin_client, seeded, otp_on):
    up = SimpleUploadedFile("console.png", PNG, content_type="image/png")
    client.post(
        "/login/verify-ownership",
        {"client_id": "ZZ9999", "registered_name": "Zed Zaveri", "evidence": up},
        **HUMAN,
    )
    req = VerificationRequest.objects.get()
    admin_client.post(
        f"/admin-panel/verifications/{req.id}/decide", {"action": "reject", "note": "unreadable"}
    )
    req.refresh_from_db()
    assert req.status == VerificationRequest.STATUS_REJECTED
    assert req.evidence is None and req.evidence_purged_at is not None
    assert not ReferrerAccount.objects.exists()
    assert not Customer.objects.filter(client_id="ZZ9999").exists()


@pytest.mark.urls("tests.urls_m13")
def test_pathb_rejects_non_image_upload(client, seeded, otp_on):
    up = SimpleUploadedFile("evil.pdf", b"%PDF-1.4", content_type="application/pdf")
    resp = client.post(
        "/login/verify-ownership",
        {"client_id": "ZZ9999", "registered_name": "Zed", "evidence": up},
        **HUMAN,
    )
    assert resp.status_code == 400
    assert not VerificationRequest.objects.exists()


# --------------------------------------------- self view: scoping + masking (ADR-026)


@pytest.mark.urls("tests.urls_m13")
def test_my_referrals_masks_ip_admin_stays_full(
    client, admin_client, seeded, onfile_customer, otp_on
):
    # A real click (lazy journey) captured with a known IP.
    client.get(f"/r/{CID}", **HUMAN)
    _login_via_otp(client, seeded)

    mine = client.get("/my/referrals").content.decode()
    assert HUMAN["REMOTE_ADDR"] not in mine, "self view leaked the raw IP"
    assert CID in mine and "Share on WhatsApp" in mine
    assert "Referral Explorer" not in mine  # admin chrome hidden (ADR-026)

    admin = admin_client.get(f"/admin-panel/referrer/{CID}/").content.decode()
    assert HUMAN["REMOTE_ADDR"] in admin, "admin view must stay full-detail"


@pytest.mark.urls("tests.urls_m13")
def test_referrer_session_cannot_reach_admin_surfaces(client, seeded, onfile_customer, otp_on):
    """Own-record scoping is structural: /my/referrals has no id parameter, and the
    admin profile of ANY referrer redirects a non-staff session to the admin login."""
    _login_via_otp(client, seeded)
    resp = client.get("/admin-panel/referrer/DA1707/")
    assert resp.status_code == 302 and "login" in resp["Location"]


@pytest.mark.urls("tests.urls_m13")
def test_login_surfaces_carry_no_partner_code_or_zerodha_url(
    client, seeded, onfile_customer, otp_on, oauth_conf
):
    """Guardrail #3 extended to every new client-facing login surface."""
    pages = [
        client.get("/login/"),
        client.post("/login/otp/request", {"client_id": CID}, **HUMAN),
        client.get("/login/verify-ownership"),
    ]
    for resp in pages:
        html = resp.content.decode()
        assert "ZMPHZC" not in html
        assert "signup.zerodha.com" not in html


@pytest.mark.urls("tests.urls_m13")
def test_my_referrals_with_activity_carries_no_partner_code(
    client, admin_client, seeded, onfile_customer, otp_on
):
    """Guardrail #3 on the LOGGED-IN self view — the surface the test above missed.

    Found live on prod 2026-07-26 (during D8): `/my/referrals` rendered PIFS's Zerodha
    partner code `ZMPHZC` as a badge on the "Referral links" card, because the self
    view and the admin Referral Profile share one template (ADR-026) and it renders
    `{{ card.partner_code }}`.

    Two reasons the existing coverage did not catch it, both reproduced here:
      1. the guardrail-3 test above only visits ANONYMOUS login surfaces;
      2. `per_link_cards` returns [] with no activity, so even visiting /my/referrals
         while logged in renders NO card — a click is REQUIRED to expose the badge.
    So this test drives a real click first, then asserts the card is actually on the
    page (otherwise it would pass vacuously) before asserting the code is absent.
    """
    client.get(f"/r/{CID}", **HUMAN)
    _login_via_otp(client, seeded)

    html = client.get("/my/referrals").content.decode()
    # The card must be RENDERED — otherwise the assertion below proves nothing.
    assert "Referral links" in html and "Zerodha" in html
    assert "ZMPHZC" not in html, "partner code leaked into the referrer self view"
    assert "signup.zerodha.com" not in html

    # The ADMIN screen is not client-facing and keeps the full detail (ADR-026).
    admin = admin_client.get(f"/admin-panel/referrer/{CID}/").content.decode()
    assert "ZMPHZC" in admin, "admin profile must still show the partner code"


@pytest.mark.urls("tests.urls_m13")
def test_my_referrals_works_with_zero_activity(client, seeded, onfile_customer, otp_on):
    """A just-bound referrer with no clicks sees their link, not an error."""
    _login_via_otp(client, seeded)
    resp = client.get("/my/referrals")
    assert resp.status_code == 200
    assert f"gorefer.in/r/{CID}" in resp.content.decode()


# --- ADR-026 shared-template sweep: nothing admin-only may reach the customer role ---

@pytest.mark.urls("tests.urls_m13")
def test_customer_view_context_carries_no_pii_and_no_partner_code(
    client, seeded, onfile_customer, otp_on
):
    """Whole-context guard on the ONE template shared by admin and customer (ADR-026).

    The `ZMPHZC` leak (fixed 2026-07-26) happened because a field the ADMIN screen wants
    was rendered unconditionally, and the customer view inherited it. That is a structural
    hazard of one-template-two-roles, not a one-off: ANY field added to the shared context
    reaches the customer unless someone remembers to strip it.

    So this asserts over the ENTIRE serialized customer context rather than a field list —
    a new leaky field fails here without anyone having to think of it.

    Audited 2026-07-27 and clean by construction: `referred_people` projects only
    name/city/profession/partner/status/opened/reward (no mobile, email or IP), and
    `_mask_clicks` blanks the IP the admin view keeps.
    """
    import json
    import re

    from apps.accounts.selfview import my_referrals_ctx
    from apps.dashboard import profile

    client.get(f"/r/{CID}", **HUMAN)
    ctx = my_referrals_ctx(seeded, CID)
    blob = json.dumps(ctx, default=str)

    assert "ZMPHZC" not in blob, "partner code reached the customer context"
    assert "signup.zerodha.com" not in blob, "raw partner URL reached the customer context"
    assert not re.findall(r"(?<!\d)[6-9]\d{9}(?!\d)", blob), "a mobile number reached the customer"
    assert not re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", blob), "an email reached the customer"
    assert HUMAN["REMOTE_ADDR"] not in blob, "raw IP reached the customer"

    # Every people row must carry ONLY the non-contact projection.
    allowed = {"name", "name_known", "city", "profession", "partner", "status", "opened", "reward"}
    for row in profile.referred_people(seeded, CID):
        assert set(row) <= allowed, f"referred_people grew a field: {set(row) - allowed}"

    # And the admin view must still keep what it needs — this is a scoping guard, not a
    # blanket redaction that would quietly degrade the staff screen.
    admin_clicks = profile.clicks_rows(seeded, CID)
    if admin_clicks:
        assert "ip" in admin_clicks[0], "admin click rows must retain the IP"
