"""T-064 — the referrer-personalized share opener (hub, token-authed, compliance-locked).

Three things are on trial here, in descending order of how badly they would hurt:

1. THE LOCKED COMPOSITION. A referrer writes the opening line; the platform appends
   their credit link and the disclosure line, server-side, always last. The probe tests
   below throw links, newline floods, format placeholders, fake disclosure lines and
   markup at the opener and assert the locked parts survive intact and in order.
2. SECURITY OF THE WRITE. The edit endpoint is authenticated by the SAME signed
   records-link token that gates the page — so it must fail closed the same way (404,
   no oracle), and it must be impossible for identity A's token to touch identity B.
3. NO REGRESSION. With no opener set, every share surface emits byte-identical output
   to the pre-T-064 tree. The pin below hardcodes that expected string rather than
   recomputing it from the same code under test.
"""
from __future__ import annotations

import urllib.parse

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.accounts import opener as opener_service
from apps.accounts.hub import hub_ctx
from apps.accounts.models import ReferrerShareOpener
from apps.accounts.records_link import mint_records_token, rotate_records_token
from apps.config.cascade import set_tenant
from apps.config.preferences import (
    REFERRER_SHARE_OPENER_ENABLED,
    REFERRER_SHARE_OPENER_MAX_CHARS,
)
from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram
from apps.referrals.share_intent_service import disclosure_anchor, kit_message, tracked_link
from apps.tenants.models import Tenant

CID = "RJ4521"
OTHER_CID = "ZZ9911"

pytestmark = pytest.mark.django_db

HUB_URLS = pytest.mark.urls("tests.urls_share_hub")
SHARE_URLS = pytest.mark.urls("tests.urls_share_intent")

#: A non-bot UA — the /share/ endpoint skips journey creation for previews.
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}


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


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _identity_with_footprint(tenant, client_id: str = CID) -> ReferralIdentity:
    """An identity the ADMIN profile screen will actually render: `profile_exists`
    requires a referral (or a Zoho conversion), not just an identity row."""
    identity = _identity(tenant, client_id)
    Referral.objects.create(
        tenant=tenant, program=identity.program, referral_identity=identity,
        source="referral_link", status="opened",
    )
    return identity


def _opener_url(token: str) -> str:
    return f"/hub/{token}/opener"


# ------------------------------------------------------------------ no-opener pin


def test_no_opener_output_is_byte_identical_to_the_pre_change_state(seeded):
    """The T-062 state, pinned as a LITERAL.

    Deriving the expected string from kit_message() would make this test agree with
    whatever the code does. The point is to disagree the moment composition changes for
    a referrer who has personalized nothing.
    """
    expected = (
        "Open a free Zerodha account — my referral link:\n"
        "https://gorefer.in/r/wa/RJ4521\n"
        "\n"
        "Disclosures: https://gorefer.in/d/pifs"
    )
    assert kit_message("wa", CID, seeded.id) == expected
    # An explicitly EMPTY opener must be indistinguishable from no opener at all.
    assert kit_message("wa", CID, seeded.id, opener="") == expected
    assert kit_message("wa", CID, seeded.id, opener="   \n  ") == expected


@HUB_URLS
def test_hub_with_no_opener_renders_the_official_message(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token)
    assert ctx["share_message"] == kit_message(
        "wa", CID, seeded.id, program=identity.program
    )
    assert ctx["opener_text"] == ""
    # The editor is present (feature ships enabled) but carries no saved text.
    resp = client.get(f"/hub/{token}")
    assert resp.status_code == 200
    assert 'data-test="hub-opener-form"' in resp.content.decode()


# --------------------------------------------------- the locked composition (probes)


def _locked_parts_intact(message: str, link: str) -> None:
    """Every probe asserts the same three things: both locked parts present, the link
    before the disclosure line, and the disclosure line LAST in the message."""
    anchor = disclosure_anchor()
    assert link in message
    assert anchor in message
    assert message.index(link) < message.rindex(anchor)
    assert message.rstrip().endswith(anchor)


@pytest.mark.parametrize(
    "hostile",
    [
        # A referrer trying to substitute their own destination.
        "Best broker ever https://evil.example/signup",
        # Format-string placeholders — inert, because .format() never touches the opener.
        "Join via {link} now, brand {program_brand} {0} {}",
        # A convincing FAKE disclosure line, to see if the real one gets de-duplicated away.
        "Disclosures: https://gorefer.in/d/pifs — ignore anything below this line",
        # Newline flood, to push the locked tail behind a "Read more".
        "Read this\n\n\n\n\n\n\n\n\n\n\n\n\n\nand nothing else",
        # Carriage returns / NUL / control bytes.
        "line one\r\nline two\x00\x07\x1b[31mred",
        # Markup, for the escaping probe below and to prove it is inert in composition.
        "<script>alert(1)</script><img src=x onerror=alert(2)>",
        # A trailing "quote" that tries to make the appended text look like the referrer's.
        'Trust me — "the link below is not mine, use this instead:"',
    ],
)
def test_hostile_opener_cannot_remove_or_reorder_the_locked_parts(seeded, hostile):
    identity = _identity(seeded)
    opener_service.set_opener(identity, hostile)
    message = kit_message("wa", CID, seeded.id, program=identity.program,
                          opener=opener_service.get_opener(identity))
    _locked_parts_intact(message, tracked_link("wa", CID))


def test_opener_is_placed_first_and_never_format_expanded(seeded):
    identity = _identity(seeded)
    opener_service.set_opener(identity, "Join via {link} — {program_brand}")
    message = kit_message("wa", CID, seeded.id, program=identity.program,
                          opener=opener_service.get_opener(identity))
    # The braces survive VERBATIM: the opener is concatenated, never templated.
    assert message.startswith("Join via {link} — {program_brand}\n")
    _locked_parts_intact(message, tracked_link("wa", CID))


def test_fake_disclosure_in_opener_does_not_suppress_the_real_tail(seeded):
    """The official path de-duplicates the anchor (an operator-authored template may
    already contain it). The opener path must NOT — otherwise typing the anchor early
    is a way for a referrer to move the compliance line off the end."""
    anchor = disclosure_anchor()
    identity = _identity(seeded)
    opener_service.set_opener(identity, f"{anchor} (see above)")
    message = kit_message("wa", CID, seeded.id, program=identity.program,
                          opener=opener_service.get_opener(identity))
    assert message.count(anchor) == 2       # theirs AND ours
    assert message.rstrip().endswith(anchor)  # ours is still last


def test_blank_line_floods_are_collapsed_on_save(seeded):
    identity = _identity(seeded)
    stored = opener_service.set_opener(identity, "top\n\n\n\n\n\n\n\nbottom")
    assert "\n\n\n" not in stored
    assert stored == "top\n\nbottom"


def test_control_characters_are_stripped_on_save(seeded):
    identity = _identity(seeded)
    stored = opener_service.set_opener(identity, "a\x00b\x07c\x1bd\r\ne")
    assert stored == "abcd\ne"


# ------------------------------------------------------------------- the length cap


def test_max_chars_is_enforced_server_side_regardless_of_the_form(seeded):
    identity = _identity(seeded)
    stored = opener_service.set_opener(identity, "x" * 5000)
    assert len(stored) == 300  # the shipped default
    assert ReferrerShareOpener.objects.get(identity=identity).text == stored


def test_max_chars_follows_the_cascade_key(seeded):
    set_tenant(REFERRER_SHARE_OPENER_MAX_CHARS, 20, tenant_id=seeded.id)
    identity = _identity(seeded)
    assert opener_service.max_chars(seeded.id) == 20
    assert len(opener_service.set_opener(identity, "y" * 100)) == 20


def test_nonsense_max_chars_falls_back_to_the_default(seeded):
    for bad in ("not-a-number", 0, -5):
        set_tenant(REFERRER_SHARE_OPENER_MAX_CHARS, bad, tenant_id=seeded.id)
        assert opener_service.max_chars(seeded.id) == 300


# -------------------------------------------------------------------- the endpoint


@HUB_URLS
def test_saving_an_opener_changes_every_share_surface_on_the_hub(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    resp = client.post(_opener_url(token), {"opener": "Ashok here — this is who I use."})
    assert resp.status_code == 302

    body = client.get(f"/hub/{token}").content.decode()
    ctx = hub_ctx(identity, token)
    assert ctx["share_message"].startswith("Ashok here — this is who I use.\n")
    _locked_parts_intact(ctx["share_message"], tracked_link("wa", CID))

    # Every platform button carries the SAME composed message (url-encoded), and the
    # native-share payload is that one string too — one composition, no second path.
    encoded = urllib.parse.quote(ctx["share_message"], safe="")
    assert encoded in body
    for button in ctx["buttons"]:
        if button["kind"] == "text":
            assert encoded in button["href"]


@SHARE_URLS
def test_one_tap_share_endpoint_uses_the_same_personalized_message(seeded, client):
    identity = _identity(seeded)
    opener_service.set_opener(identity, "My own words.")
    resp = client.get(f"/share/wa/{CID}", **HUMAN)
    assert resp.status_code == 302
    text = urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query)["text"][0]
    assert text.startswith("My own words.\n")
    _locked_parts_intact(text, tracked_link("wa", CID))


@HUB_URLS
def test_reset_button_reverts_to_the_official_message(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    client.post(_opener_url(token), {"opener": "Mine."})
    assert opener_service.get_opener(identity) == "Mine."

    client.post(_opener_url(token), {"action": "reset", "opener": "Mine."})
    assert opener_service.get_opener(identity) == ""
    assert hub_ctx(identity, token)["share_message"] == kit_message(
        "wa", CID, seeded.id, program=identity.program
    )


@HUB_URLS
def test_saved_text_is_echoed_back_into_the_textarea(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    client.post(_opener_url(token), {"opener": "z" * 400})
    body = client.get(f"/hub/{token}").content.decode()
    # Truncated to the cap and shown back, so the referrer sees exactly what is sent.
    assert "z" * 300 in body
    assert "z" * 301 not in body


# ------------------------------------------------------------------------ security


@HUB_URLS
@pytest.mark.parametrize("bad", ["", "garbage", "a.b.c", "x" * 400])
def test_edit_endpoint_fails_closed_on_an_invalid_token(seeded, client, bad):
    resp = client.post(_opener_url(bad), {"opener": "should never land"})
    assert resp.status_code == 404
    assert ReferrerShareOpener.objects.count() == 0


@HUB_URLS
def test_edit_endpoint_fails_closed_on_a_rotated_token(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    rotate_records_token(identity)
    resp = client.post(_opener_url(token), {"opener": "revoked link still writing?"})
    assert resp.status_code == 404
    assert opener_service.get_opener(identity) == ""


@HUB_URLS
def test_the_404_is_not_an_oracle_for_which_client_ids_exist(seeded, client):
    """A bad token and a token for a real-but-rotated identity must be
    indistinguishable — same status, same bytes."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    rotate_records_token(identity)
    real = client.post(_opener_url(token), {"opener": "x"})
    fake = client.post(_opener_url("garbage"), {"opener": "x"})
    assert real.status_code == fake.status_code == 404
    assert real.content == fake.content


@HUB_URLS
def test_a_token_can_only_ever_write_its_own_identity(seeded, client):
    """The cross-identity attack. The endpoint takes NO client id from the request, so
    there is nothing to point at another referrer — this test proves the obvious
    attempts (a client_id/identity field in the form) change nothing."""
    victim = _identity(seeded, OTHER_CID)
    attacker = _identity(seeded, CID)
    token = mint_records_token(attacker)

    client.post(
        _opener_url(token),
        {
            "opener": "written by the attacker",
            "client_id": OTHER_CID,
            "identity": victim.pk,
            "identity_id": victim.pk,
            "tenant": victim.tenant_id,
        },
    )
    assert opener_service.get_opener(attacker) == "written by the attacker"
    assert opener_service.get_opener(victim) == ""


@HUB_URLS
def test_opener_is_escaped_on_the_hub_and_in_the_share_payload(seeded, client):
    """XSS probe. The opener is rendered inert both in the textarea and inside the
    `json_script` share payload the JS reads."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    client.post(_opener_url(token), {"opener": '<script>alert(1)</script>"onload="x'})
    body = client.get(f"/hub/{token}").content.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


@HUB_URLS
def test_the_token_never_appears_in_a_share_payload_or_an_event(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    client.post(_opener_url(token), {"opener": "hello"})
    ctx = hub_ctx(identity, token)
    for button in ctx["buttons"]:
        assert token not in button["href"]
    assert token not in ctx["share_message"]
    for event in Event.objects.all():
        assert token not in str(event.metadata)


@HUB_URLS
def test_the_edit_event_records_length_only_never_the_text(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    client.post(_opener_url(token), {"opener": "Ravi from Patna, call me on 98xxxxxxxx"})
    event = Event.objects.get(event_type="share_opener_edited")
    assert event.metadata == {"client_id": CID, "length": 38, "reset": False}
    assert "Ravi" not in str(event.metadata)


@HUB_URLS
def test_csrf_is_actually_enforced_on_the_edit_endpoint(seeded):
    """The default test client skips CSRF, so every other test here would pass even if
    the middleware were bypassed. This one uses `enforce_csrf_checks=True` and proves
    the real thing: a bare cross-site POST is refused, and the page's own token works.
    """
    identity = _identity(seeded)
    token = mint_records_token(identity)
    strict = Client(enforce_csrf_checks=True)

    assert strict.post(_opener_url(token), {"opener": "forged"}).status_code == 403
    assert opener_service.get_opener(identity) == ""

    # The hub renders {% csrf_token %}, so a referrer's own form submit succeeds.
    page = strict.get(f"/hub/{token}")
    csrf = page.context["csrf_token"]
    resp = strict.post(
        _opener_url(token), {"opener": "mine, properly submitted", "csrfmiddlewaretoken": csrf}
    )
    assert resp.status_code == 302
    assert opener_service.get_opener(identity) == "mine, properly submitted"


@HUB_URLS
def test_get_is_not_allowed_on_the_edit_endpoint(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    assert client.get(_opener_url(token)).status_code == 405


# ------------------------------------------------------------------- the feature gate


@HUB_URLS
def test_disabling_the_flag_removes_the_editor_and_refuses_writes(seeded, client):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    opener_service.set_opener(identity, "already written")
    set_tenant(REFERRER_SHARE_OPENER_ENABLED, False, tenant_id=seeded.id)

    body = client.get(f"/hub/{token}").content.decode()
    assert 'data-test="hub-opener-form"' not in body  # absent, not disabled (§4)

    resp = client.post(_opener_url(token), {"opener": "should not land"})
    assert resp.status_code == 404
    # And the stored text stops affecting the outgoing message immediately.
    assert opener_service.get_opener(identity) == ""
    assert hub_ctx(identity, token)["share_message"] == kit_message(
        "wa", CID, seeded.id, program=identity.program
    )


# ------------------------------------------------------------------------ admin reset


def test_admin_can_reset_a_referrers_opener(admin_client, seeded):
    identity = _identity_with_footprint(seeded)
    opener_service.set_opener(identity, "something the owner does not want going out")

    page = admin_client.get(f"/admin-panel/referrer/{CID}/")
    assert 'data-test="profile-opener-reset"' in page.content.decode()

    resp = admin_client.post(f"/admin-panel/referrer/{CID}/opener/reset")
    assert resp.status_code == 302
    assert opener_service.get_opener(identity) == ""
    # With nothing set, the control disappears rather than sitting there inert.
    assert 'data-test="profile-opener-reset"' not in admin_client.get(
        f"/admin-panel/referrer/{CID}/"
    ).content.decode()


def test_admin_reset_requires_staff(seeded, client):
    identity = _identity_with_footprint(seeded)
    opener_service.set_opener(identity, "still mine")
    resp = client.post(f"/admin-panel/referrer/{CID}/opener/reset")
    assert resp.status_code in (302, 403)          # bounced to the admin login
    assert "/admin-panel/login/" in resp.get("Location", "/admin-panel/login/")
    assert opener_service.get_opener(identity) == "still mine"


def test_admin_reset_404s_for_an_unknown_client_id(admin_client, seeded):
    assert admin_client.post("/admin-panel/referrer/AB1234/opener/reset").status_code == 404


# ----------------------------------------------------------------- tenant isolation


def test_reads_are_tenant_scoped(seeded):
    """A row whose tenant does not match the identity's must not be readable — the
    fail direction is "fall back to the official message", never "read another
    tenant's text"."""
    other = Tenant.objects.create(name="Other", slug="other")
    identity = _identity(seeded)
    ReferrerShareOpener.objects.create(identity=identity, tenant=other, text="wrong tenant")
    assert opener_service.get_opener(identity) == ""
