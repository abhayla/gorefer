"""T-053 — the referral share hub (GET /hub/{token}).

What this locks down, in rough order of how much it would cost to get wrong:

  - THE TOKEN IS NEVER SHARED CONTENT. It appears in no share URL, in no prefill text
    and in no event payload. Asserted on the built targets, on the response bytes'
    share hrefs, and on the Event rows — three places, because this is the one defect
    that would hand a stranger somebody's records with a single forward.
  - guardrail 3: no partner code and no raw partner URL anywhere on the page, and none
    in the prefill either — the credit link `/r/wa/{id}` is the only destination.
  - the incentive claim comes from CONFIG: editing the cascade key changes the page.
  - the whole surface is absent when ENABLE_SHARE_HUB is off, and bad/expired/rotated
    tokens get the SAME friendly page /rr/ renders.
  - every button records a per-channel share event that the API actually accepts.
"""
from __future__ import annotations

import dataclasses
import re

import pytest
from django.core.management import call_command

from apps.accounts.hub import (
    NATIVE_SHARE_CHANNEL,
    SHARE_BUTTONS,
    _share_targets,
    hub_ctx,
)
from apps.accounts.records_link import mint_records_token, rotate_records_token
from apps.config.models import ConfigCentral
from apps.config.preferences import (
    REFERRER_REWARD_CLAIM,
    SHARE_HUB_BENEFITS,
    SHARE_HUB_GUIDANCE,
    SHARE_HUB_HEADLINE,
    SHARE_HUB_OG_IMAGE_URL,
)
from apps.events.models import PII_KEYS, Event
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

CID = "RJ4521"

pytestmark = pytest.mark.django_db

HUB_URLS = pytest.mark.urls("tests.urls_share_hub")


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _with_flag(monkeypatch, module: str, **overrides) -> None:
    """Swap the flags snapshot a module reads.

    `flags` is a FROZEN dataclass — deliberately, so nothing can mutate the process-wide
    snapshot at runtime. So a test replaces the module's reference with a copy rather
    than assigning to a field (which raises FrozenInstanceError).
    """
    from gorefer.flags import flags

    monkeypatch.setattr(f"{module}.flags", dataclasses.replace(flags, **overrides))


def _share_hrefs(body: str) -> list[str]:
    """Every href on a tagged share button, straight out of the rendered markup."""
    return re.findall(
        r"""<a\s+href=["']([^"']+)["'][^>]*data-share-channel=""", body, re.I
    )


# ------------------------------------------------------------------ the token invariant


def test_no_share_target_contains_the_token(seeded):
    """The builder cannot leak what it is never given — proven on its output."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token)

    for button in ctx["buttons"]:
        assert token not in button["href"], f"{button['code']} share URL carries the token"
    assert token not in ctx["share_message"]
    assert token not in ctx["my_link"]


@HUB_URLS
def test_rendered_share_buttons_carry_the_credit_link_not_the_token(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()

    hrefs = _share_hrefs(body)
    assert len(hrefs) == len(SHARE_BUTTONS), "a share button lost its tracked href"
    for href in hrefs:
        assert token not in href
    # …and the credit link IS what they carry (url-encoded inside the intent).
    assert any("RJ4521" in href for href in hrefs)


@HUB_URLS
def test_the_only_place_the_token_appears_is_the_records_cross_link(
    client, seeded, monkeypatch
):
    """The token is page access. The single legitimate re-use is the /rr/ cross-link —
    a link to another page of the referrer's own, never something they forward."""
    _with_flag(monkeypatch, "apps.accounts.hub", ENABLE_RECORDS_LINK=True)

    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()

    occurrences = body.count(token)
    assert occurrences == 1, f"token appears {occurrences}x; expected only the /rr/ cross-link"
    assert f"/rr/{token}" in body


@HUB_URLS
def test_the_view_event_is_pii_free_and_token_free(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    client.get(f"/hub/{token}")

    event = Event.objects.get(event_type="share_hub_viewed")
    assert event.tenant_id == seeded.id
    assert event.metadata == {"client_id": CID}
    assert not ({k.lower() for k in event.metadata} & PII_KEYS)
    assert token not in str(event.metadata)


# ------------------------------------------------------------------------- share targets


def test_every_button_gets_a_platform_web_intent():
    targets = _share_targets("hello https://gorefer.in/r/wa/RJ4521", "https://gorefer.in/r/wa/RJ4521")
    assert targets["wa"].startswith("https://wa.me/?text=")
    assert targets["telegram"].startswith("https://t.me/share/url?")
    assert targets["facebook"].startswith("https://www.facebook.com/sharer/sharer.php?u=")
    assert targets["x"].startswith("https://x.com/intent/post?text=")
    assert targets["linkedin"].startswith("https://www.linkedin.com/sharing/share-offsite/?url=")
    # No builder is missing: every declared button has a target.
    assert {b["code"] for b in SHARE_BUTTONS} <= set(targets)


def test_the_share_message_carries_the_channel_tagged_credit_link(seeded):
    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity))
    assert ctx["my_link"] == "https://gorefer.in/r/wa/RJ4521"
    assert ctx["my_link"] in ctx["share_message"]


@HUB_URLS
def test_copy_and_native_share_controls_are_present(client, seeded):
    identity = _identity(seeded)
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()
    assert 'id="copyLinkBtn"' in body
    assert 'id="nativeShareBtn"' in body
    assert NATIVE_SHARE_CHANNEL in body


def test_every_button_channel_is_one_the_share_api_accepts():
    """A tap that the API rejects with 422 is a silently lost event — the button would
    look like it worked and the funnel would under-count."""
    from api.share import _CHANNELS
    from apps.accounts.hub import COPY_CHANNEL

    for button in SHARE_BUTTONS:
        assert button["event_channel"] in _CHANNELS, button["code"]
    assert NATIVE_SHARE_CHANNEL in _CHANNELS
    assert COPY_CHANNEL in _CHANNELS


@HUB_URLS
def test_a_share_tap_records_a_per_channel_event(client, seeded):
    identity = _identity(seeded)
    client.get(f"/hub/{mint_records_token(identity)}")
    for button in SHARE_BUTTONS:
        resp = client.post(
            "/api/share/",
            data={"client_id": CID, "channel": button["event_channel"]},
            content_type="application/json",
        )
        assert resp.status_code == 202, button["code"]

    channels = sorted(
        e.metadata["channel"]
        for e in Event.objects.filter(event_type="share_clicked")
    )
    assert channels == sorted(b["event_channel"] for b in SHARE_BUTTONS)


# ------------------------------------------------------------------------- config-driven


@HUB_URLS
def test_the_incentive_claim_comes_from_config_not_a_literal(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ConfigCentral.objects.update_or_create(
        key=REFERRER_REWARD_CLAIM, defaults={"value": "CLAIM-SENTINEL-FROM-CONFIG"}
    )
    body = client.get(f"/hub/{token}").content.decode()
    assert "CLAIM-SENTINEL-FROM-CONFIG" in body
    # The default claim is gone — the page followed config rather than adding to it.
    assert "10% brokerage share" not in body


@HUB_URLS
@pytest.mark.parametrize(
    "key,value,expected",
    [
        (SHARE_HUB_HEADLINE, "HEADLINE-SENTINEL", "HEADLINE-SENTINEL"),
        (SHARE_HUB_BENEFITS, ["BENEFIT-SENTINEL"], "BENEFIT-SENTINEL"),
        (SHARE_HUB_GUIDANCE, ["GUIDANCE-SENTINEL"], "GUIDANCE-SENTINEL"),
    ],
)
def test_every_copy_block_is_a_cascade_key(client, seeded, key, value, expected):
    """Rail E-6: the shipped copy is a placeholder pending owner review, so all of it
    has to be changeable without a deploy."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ConfigCentral.objects.update_or_create(key=key, defaults={"value": value})
    assert expected in client.get(f"/hub/{token}").content.decode()


@HUB_URLS
def test_the_link_preview_uses_a_config_keyed_brand_image(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)

    body = client.get(f"/hub/{token}").content.decode()
    assert 'property="og:image"' in body
    assert "/static/img/referral-preview-card.png" in body, (
        "the committed brand card is not served"
    )

    # An operator can point the key at an absolute CDN URL with no deploy.
    ConfigCentral.objects.update_or_create(
        key=SHARE_HUB_OG_IMAGE_URL, defaults={"value": "https://cdn.example.com/brand.png"}
    )
    body = client.get(f"/hub/{token}").content.decode()
    assert "https://cdn.example.com/brand.png" in body


@HUB_URLS
def test_og_url_does_not_leak_the_token(client, seeded):
    """`build_absolute_uri()` here would stamp a live credential into a meta tag that
    crawlers cache and preview surfaces echo."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    og_url = re.search(r"""<meta property=["']og:url["'] content=["']([^"']*)["']""", body)
    assert og_url is not None
    assert token not in og_url.group(1)
    assert "noindex" in body


# ---------------------------------------------------------------------------- guardrails


@HUB_URLS
def test_no_partner_code_or_zerodha_url_on_the_page_or_in_the_prefill(client, seeded, settings):
    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity))
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()

    for blob in (body, ctx["share_message"], ctx["my_link"]):
        assert settings.PARTNER_CODE not in blob
        assert "signup.zerodha.com" not in blob


@HUB_URLS
def test_the_compliance_block_is_auto_injected(client, seeded, settings):
    identity = _identity(seeded)
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()
    assert settings.AP_DISCLOSURE_BLOCK in body
    assert settings.MARKET_RISK_WARNING in body


@HUB_URLS
def test_the_page_is_read_only(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    assert "<form" not in client.get(f"/hub/{token}").content.decode().lower()
    assert client.post(f"/hub/{token}").status_code == 405


@HUB_URLS
def test_no_third_party_script_or_stylesheet(client, seeded):
    """Share buttons are plain anchors — no SDK. Every script/stylesheet stays same-origin
    so the page can still reach idle on a network that blackholes a CDN."""
    identity = _identity(seeded)
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()
    for src in re.findall(r"""<script[^>]+src=["']([^"']+)["']""", body, re.I):
        assert not src.startswith(("http://", "https://", "//")), src
    for tag in re.findall(r"""<link[^>]+rel=["']stylesheet["'][^>]*>""", body, re.I):
        href = re.search(r"""href=["']([^"']+)["']""", tag)
        assert href and not href.group(1).startswith(("http://", "https://", "//"))


# ------------------------------------------------------------------------ token failures


@HUB_URLS
@pytest.mark.parametrize("case", ["invalid", "rotated"])
def test_bad_tokens_get_the_same_friendly_404_as_the_records_page(client, seeded, case):
    identity = _identity(seeded)
    if case == "invalid":
        token = "garbage-token"
    else:
        token = mint_records_token(identity)
        rotate_records_token(identity)

    resp = client.get(f"/hub/{token}")
    assert resp.status_code == 404
    body = resp.content.decode()
    assert "This link has expired" in body
    assert "/login/" in body
    # Zero referrer data on the failure page.
    assert CID not in body


@HUB_URLS
def test_a_failed_open_records_no_event(client, seeded):
    client.get("/hub/garbage")
    assert not Event.objects.filter(event_type="share_hub_viewed").exists()


@HUB_URLS
def test_the_view_is_rate_limited(client, seeded, settings):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    # RATELIMIT_ENABLED defaults off in dev; the suite flips it on per-test (see
    # tests/test_ratelimit.py) — a rate limit that is never exercised is not a rate limit.
    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_RECORDS_MAX = 2
    for _ in range(2):
        assert client.get(f"/hub/{token}", REMOTE_ADDR="203.0.113.9").status_code == 200
    assert client.get(f"/hub/{token}", REMOTE_ADDR="203.0.113.9").status_code == 429


# ----------------------------------------------------------------------------- the flag


def test_route_is_absent_when_the_flag_is_off(client, seeded):
    from gorefer.flags import flags

    assert flags.ENABLE_SHARE_HUB is False
    assert client.get("/hub/anything").status_code == 404


@HUB_URLS
def test_route_is_present_when_the_flag_is_on(client, seeded):
    identity = _identity(seeded)
    assert client.get(f"/hub/{mint_records_token(identity)}").status_code == 200


def test_the_flag_mounts_exactly_one_new_get_route():
    """Structural proof of "one page, one GET": the gated urlconf adds /rr/ + /hub/ over
    base, and nothing else."""
    from gorefer.urls import urlpatterns as base
    from tests import urls_share_hub

    added = urls_share_hub.urlpatterns[len(base):]
    assert [pattern.name for pattern in added] == ["records_link", "share_hub"]


@HUB_URLS
def test_the_records_page_cross_links_back_to_the_hub(client, seeded, monkeypatch):
    """DoD: /rr/ gains a link to /hub/{token} — the same token, no second system."""
    _with_flag(monkeypatch, "apps.accounts.records", ENABLE_SHARE_HUB=True)

    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/rr/{token}").content.decode()
    assert f"/hub/{token}" in body
    assert "Share your referral link" in body


@HUB_URLS
def test_the_records_cross_link_is_absent_when_the_hub_is_off(client, seeded):
    """No dead links (Constitution §4) — the default flags have the hub off."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/rr/{token}").content.decode()
    assert "/hub/" not in body
