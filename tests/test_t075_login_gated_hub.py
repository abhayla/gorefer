"""T-075 — the LOGIN-GATED share hub at the token-free `/hub` (Phase 1 of the
token -> login retirement).

Why this route exists: a `{{token}}` in a WhatsApp template button only resolves if
GoRefer's own sender mints it per recipient, so a Wati DASHBOARD broadcast — a path
people really use — ships a blank or broken link. A static `gorefer.in/hub` behind the
already-live M13 login works no matter who sent the message.

What is on trial:

1. THE GATE. Anonymous -> 302 to `/login/?next=/hub`, and after proving identity the
   referrer lands back on the hub, not on a generic dashboard.
2. NO TOKEN, ANYWHERE. Not in the URL, not in the response bytes, not in the form
   action, not in an event payload. This route's whole premise is not having one.
3. THE T-064 GUARANTEES, RE-HOMED. The opener edit is authenticated by the SESSION;
   the credit link and the disclosure tail are still appended server-side, the cap
   still applies, the text still never reaches the event log, and a session can only
   ever edit its OWN opener — because there is no identity input on the request.
4. SAME PAGE, ONE TEMPLATE. Brand, credit link, share buttons, benefits, images and
   disclosures all render from the session identity, not from a token-resolved one.
"""
from __future__ import annotations

import urllib.parse

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils.html import escape

from apps.accounts import opener as opener_service
from apps.accounts import service as accounts_service
from apps.accounts.hub import hub_ctx
from apps.accounts.models import ReferrerAccount, ReferrerShareOpener
from apps.accounts.records_link import mint_records_token
from apps.config.cascade import set_tenant
from apps.config.preferences import REFERRER_SHARE_OPENER_ENABLED
from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram
from apps.referrals.share_intent_service import disclosure_anchor
from apps.tenants.models import Tenant

CID = "RJ4521"
OTHER_CID = "ZZ9911"
HUB = "/hub"
OPENER = "/hub/opener"

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.urls_hub_login")]


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _account(tenant, client_id: str = CID) -> ReferrerAccount:
    """A bound referrer account, created the way the real OTP door creates one."""
    return accounts_service.get_or_create_account(
        tenant, client_id, bound_via=ReferrerAccount.BOUND_VIA_OTP, mobile="919876543210"
    )


def _logged_in(tenant, client_id: str = CID) -> Client:
    account = _account(tenant, client_id)
    client = Client()
    client.force_login(account.user)
    return client


# ------------------------------------------------------------------------- 1. the gate


def test_anonymous_is_sent_to_login_with_next(client, seeded):
    resp = client.get(HUB)
    assert resp.status_code == 302
    location = resp["Location"]
    assert location.startswith("/login/"), location
    assert urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["next"] == [HUB]


def test_login_page_sends_the_referrer_back_to_the_hub(client, seeded):
    """The whole point of `next`: the visitor lands where they were going, not on a
    generic dashboard. Driven through the REAL views (no hand-set session key)."""
    _account(seeded, CID)
    _identity(seeded, CID)
    # 1. anonymous hits the hub -> bounced to login, which remembers the destination
    login_url = client.get(HUB)["Location"]
    client.get(login_url)
    # 2. the referrer proves who they are (force_login stands in for the OTP/OAuth
    #    door, which is exercised end-to-end in tests/test_m13_login.py)
    account = ReferrerAccount.objects.get(tenant=seeded, client_id=CID)
    client.force_login(account.user)
    # 3. the login entry hands them straight on to the remembered destination
    resp = client.get("/login/")
    assert resp.status_code == 302 and resp["Location"] == HUB


def test_login_without_next_still_lands_on_my_referrals(client, seeded):
    """No regression for the M13 default path."""
    account = _account(seeded, CID)
    client.force_login(account.user)
    resp = client.get("/login/")
    assert resp.status_code == 302 and resp["Location"] == "/my/referrals"


@pytest.mark.parametrize(
    "hostile",
    ["//evil.example/x", "https://evil.example/x", "http:/evil", "/\\evil.example"],
)
def test_next_cannot_become_an_open_redirect(client, seeded, hostile):
    account = _account(seeded, CID)
    client.force_login(account.user)
    resp = client.get(f"/login/?next={urllib.parse.quote(hostile, safe='')}")
    assert resp.status_code == 302
    assert resp["Location"] == "/my/referrals", resp["Location"]


def test_opener_post_is_gated_too(client, seeded):
    _identity(seeded)
    resp = client.post(OPENER, {"opener": "hi"})
    assert resp.status_code == 302 and resp["Location"].startswith("/login/")
    assert not ReferrerShareOpener.objects.exists()


# -------------------------------------------------------------- 2. no token, anywhere


def test_hub_renders_for_the_session_identity(seeded):
    identity = _identity(seeded)
    html = _logged_in(seeded).get(HUB).content.decode()
    assert f"gorefer.in/r/wa/{CID}" in html
    assert identity.client_id in html


def test_no_token_string_appears_on_the_route(seeded):
    """A token minted for this very identity must not show up in the page — the
    session route has no token and must not grow one by accident."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = _logged_in(seeded).get(HUB).content.decode()
    assert token not in body
    # The opener form posts to the STATIC session endpoint, not a tokened one.
    assert f'action="{OPENER}"' in body
    assert "/hub/opener" in body
    assert "/rr/" not in body


def test_event_log_carries_no_token_and_no_pii(seeded):
    _identity(seeded)
    _logged_in(seeded).get(HUB)
    event = Event.objects.get(event_type="share_hub_viewed")
    assert event.metadata == {"client_id": CID}


def test_guardrail_3_no_partner_code_or_raw_partner_url(seeded):
    _identity(seeded)
    body = _logged_in(seeded).get(HUB).content.decode()
    assert "ZMPHZC" not in body
    assert "signup.zerodha.com" not in body


def test_share_hrefs_all_carry_the_credit_link(seeded):
    _identity(seeded)
    body = _logged_in(seeded).get(HUB).content.decode()
    ctx = hub_ctx(ReferralIdentity.objects.get(client_id=CID), "", session_mode=True)
    assert ctx["my_link"].endswith(f"/r/wa/{CID}")
    for button in ctx["buttons"]:
        assert urllib.parse.quote(CID, safe="") in button["href"], button["code"]
        assert escape(button["href"]) in body


# -------------------------------------------------- 3. the T-064 guarantees, re-homed


def test_session_opener_edit_saves_and_composes_locked(seeded):
    identity = _identity(seeded)
    client = _logged_in(seeded)
    resp = client.post(OPENER, {"opener": "Rajesh here — this is what I use."})
    assert resp.status_code == 302 and resp["Location"].startswith(HUB)

    row = ReferrerShareOpener.objects.get(identity=identity)
    assert row.text == "Rajesh here — this is what I use."

    message = hub_ctx(identity, "", session_mode=True)["share_message"]
    assert message.startswith("Rajesh here — this is what I use.")
    # The locked tail is appended AFTER the opener, server-side, always.
    assert f"gorefer.in/r/wa/{CID}" in message
    assert disclosure_anchor() in message


def test_session_opener_reset_clears_it(seeded):
    identity = _identity(seeded)
    client = _logged_in(seeded)
    client.post(OPENER, {"opener": "mine"})
    client.post(OPENER, {"opener": "mine", "action": "reset"})
    assert ReferrerShareOpener.objects.get(identity=identity).text == ""


def test_session_opener_respects_the_cap(seeded):
    identity = _identity(seeded)
    _logged_in(seeded).post(OPENER, {"opener": "x" * 5000})
    stored = ReferrerShareOpener.objects.get(identity=identity).text
    assert len(stored) == opener_service.max_chars(seeded.id)


def test_session_opener_text_never_reaches_the_event_log(seeded):
    _identity(seeded)
    secret = "MEET-ME-AT-SEVEN"
    _logged_in(seeded).post(OPENER, {"opener": secret})
    event = Event.objects.get(event_type="share_opener_edited")
    assert secret not in str(event.metadata)
    assert event.metadata["client_id"] == CID
    assert event.metadata["length"] == len(secret)
    assert event.metadata["reset"] is False


def test_a_session_can_only_edit_its_own_opener(seeded):
    """Cross-identity is impossible BY CONSTRUCTION: the endpoint takes no client_id,
    so there is nothing on the request to point at someone else's record. The probe
    posts every id-shaped field name anyway and asserts the other row is untouched."""
    mine = _identity(seeded, CID)
    theirs = _identity(seeded, OTHER_CID)
    opener_service.set_opener(theirs, "their words")

    _logged_in(seeded, CID).post(
        OPENER,
        {
            "opener": "my words",
            "client_id": OTHER_CID,
            "identity": theirs.pk,
            "identity_id": theirs.pk,
            "token": mint_records_token(theirs),
        },
    )
    assert ReferrerShareOpener.objects.get(identity=mine).text == "my words"
    assert ReferrerShareOpener.objects.get(identity=theirs).text == "their words"


def test_session_opener_renders_escaped(seeded):
    _identity(seeded)
    client = _logged_in(seeded)
    client.post(OPENER, {"opener": '<script>alert(1)</script>'})
    body = client.get(HUB).content.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_opener_editor_absent_and_write_404s_when_the_tenant_turns_it_off(seeded):
    _identity(seeded)
    set_tenant(REFERRER_SHARE_OPENER_ENABLED, False, tenant_id=seeded.id)
    client = _logged_in(seeded)
    body = client.get(HUB).content.decode()
    assert 'data-test="hub-opener-form"' not in body       # absent, not disabled (§4)
    assert client.post(OPENER, {"opener": "x"}).status_code == 404
    assert not ReferrerShareOpener.objects.exists()


def test_admin_reset_still_clears_a_session_written_opener(seeded):
    identity = _identity(seeded)
    _logged_in(seeded).post(OPENER, {"opener": "mine"})
    opener_service.clear_opener(identity)
    assert ReferrerShareOpener.objects.get(identity=identity).text == ""


# --------------------------------------------------- 4. bound but no identity row yet


def test_bound_referrer_without_an_identity_gets_a_clear_link_state(seeded):
    """Never a blank or broken hub: bound at login, never clicked, no Zoho conversion.
    Identities are created at CLICK time (ADR-008) — rendering must not create one."""
    assert not ReferralIdentity.objects.exists()
    resp = _logged_in(seeded).get(HUB)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'data-test="hub-unlinked"' in body
    assert "/login/verify-ownership" in body
    assert f"/r/wa/{CID}" not in body                   # no half-built credit link
    assert not ReferralIdentity.objects.exists()        # and none was created


def test_unlinked_opener_post_is_a_no_op(seeded):
    resp = _logged_in(seeded).post(OPENER, {"opener": "x"})
    assert resp.status_code == 302 and resp["Location"] == HUB
    assert not ReferrerShareOpener.objects.exists()


# ------------------------------------------------- 5. flags off -> no route (no dead UI)


@pytest.mark.urls("gorefer.urls")
def test_no_session_hub_route_under_the_default_flags(client, seeded):
    """Default flags have ENABLE_SHARE_HUB off, so neither session route exists at
    all — a 404, not a login bounce (Constitution §4: no dead route when off)."""
    from django.conf import settings

    assert not settings.FEATURE_FLAGS.get("ENABLE_SHARE_HUB", False)
    assert client.get(HUB).status_code == 404
    assert client.post(OPENER, {"opener": "x"}).status_code == 404


# --------------------------------------------------------- 6. language (T-061 parity)


def test_hindi_renders_on_the_session_route(seeded):
    _identity(seeded)
    body = _logged_in(seeded).get(f"{HUB}?lang=hi").content.decode()
    assert 'lang="hi"' in body
    assert "प्रतिभूति" in body


def test_referral_footprint_does_not_change_the_route(seeded):
    """A referrer with real activity renders the same page (no separate code path)."""
    identity = _identity(seeded)
    Referral.objects.create(
        tenant=seeded, program=identity.program, referral_identity=identity,
        source="referral_link", status="opened",
    )
    assert _logged_in(seeded).get(HUB).status_code == 200
