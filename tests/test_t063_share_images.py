"""T-063 — share images on the hub (native-share files + download posters).

Config-driven, EMPTY by default (Constitution §4: no image UI until the owner points
these at a compliance-reviewed asset). Two independent enforcement points share ONE
same-origin check (`apps.accounts.hub.resolve_share_image_url`): the Preferences
screen at save time, and the hub at render time — so a value written straight to the
DB can't slip a cross-origin image past what the screen would have rejected.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.accounts.hub import hub_ctx, resolve_share_image_url
from apps.accounts.records_link import mint_records_token
from apps.config.cascade import set_tenant
from apps.config.preferences import SHARE_HUB_IMAGE_1_URL, SHARE_HUB_IMAGE_2_URL
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

CID = "RJ4521"

pytestmark = pytest.mark.django_db

HUB_URLS = pytest.mark.urls("tests.urls_share_hub")
PREFS_URL = "/admin-panel/preferences"


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


# --------------------------------------------------------- resolve_share_image_url


def test_bare_static_path_resolves_same_origin():
    assert resolve_share_image_url("img/share-poster-1.png") == "/static/img/share-poster-1.png"


def test_site_relative_path_passes_through():
    assert resolve_share_image_url("/media/posters/one.png") == "/media/posters/one.png"


def test_absolute_url_on_public_base_is_accepted(settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    assert (
        resolve_share_image_url("https://gorefer.in/static/img/poster.png")
        == "https://gorefer.in/static/img/poster.png"
    )


def test_cross_origin_absolute_url_is_rejected(settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    assert resolve_share_image_url("https://evil.example.com/poster.png") == ""


def test_scheme_relative_url_is_rejected():
    assert resolve_share_image_url("//evil.example.com/poster.png") == ""


def test_blank_resolves_to_blank():
    assert resolve_share_image_url("") == ""
    assert resolve_share_image_url("   ") == ""


# ---------------------------------------------------------------------------- hub_ctx


def test_no_images_configured_yields_empty_share_images(seeded):
    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity))
    assert ctx["share_images"] == []


def test_configured_images_appear_in_hub_ctx(seeded):
    identity = _identity(seeded)
    set_tenant(SHARE_HUB_IMAGE_1_URL, "img/poster-1.png", tenant_id=seeded.id)
    set_tenant(SHARE_HUB_IMAGE_2_URL, "img/poster-2.png", tenant_id=seeded.id)
    ctx = hub_ctx(identity, mint_records_token(identity))
    urls = [i["url"] for i in ctx["share_images"]]
    assert urls == ["/static/img/poster-1.png", "/static/img/poster-2.png"]
    assert all(i["filename"] for i in ctx["share_images"])


def test_a_directly_written_cross_origin_value_is_dropped_at_render(seeded, settings):
    """Defense-in-depth: even bypassing the Preferences screen, render time rejects it."""
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    identity = _identity(seeded)
    set_tenant(SHARE_HUB_IMAGE_1_URL, "https://evil.example.com/poster.png", tenant_id=seeded.id)
    ctx = hub_ctx(identity, mint_records_token(identity))
    assert ctx["share_images"] == []


# ------------------------------------------------------------------------ hub render


@HUB_URLS
def test_no_download_buttons_when_unconfigured(client, seeded):
    identity = _identity(seeded)
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()
    assert 'data-test="hub-share-images"' not in body
    assert 'data-test="hub-download-image"' not in body


@HUB_URLS
def test_download_buttons_present_when_configured(client, seeded):
    identity = _identity(seeded)
    set_tenant(SHARE_HUB_IMAGE_1_URL, "img/poster-1.png", tenant_id=seeded.id)
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()
    assert 'data-test="hub-share-images"' in body
    assert body.count('data-test="hub-download-image"') == 1
    assert '/static/img/poster-1.png' in body
    assert 'download="poster-1.png"' in body


@HUB_URLS
def test_share_images_data_is_plumbed_to_js(client, seeded):
    identity = _identity(seeded)
    set_tenant(SHARE_HUB_IMAGE_1_URL, "img/poster-1.png", tenant_id=seeded.id)
    body = client.get(f"/hub/{mint_records_token(identity)}").content.decode()
    assert 'id="shareImages"' in body
    assert "/static/img/poster-1.png" in body


@HUB_URLS
def test_the_token_never_appears_in_the_share_images_payload(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    set_tenant(SHARE_HUB_IMAGE_1_URL, "img/poster-1.png", tenant_id=seeded.id)
    set_tenant(SHARE_HUB_IMAGE_2_URL, "img/poster-2.png", tenant_id=seeded.id)
    ctx = hub_ctx(identity, token)
    for image in ctx["share_images"]:
        assert token not in image["url"]
        assert token not in image["filename"]


@HUB_URLS
def test_download_label_is_bilingual(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    set_tenant(SHARE_HUB_IMAGE_1_URL, "img/poster-1.png", tenant_id=seeded.id)
    en_body = client.get(f"/hub/{token}").content.decode()
    hi_body = client.get(f"/hub/{token}?lang=hi").content.decode()
    assert "Download poster" in en_body
    assert "डाउनलोड" in hi_body


# --------------------------------------------------------------- Preferences screen


def test_preferences_saves_a_same_origin_image_path(admin_client, seeded):
    resp = admin_client.post(PREFS_URL, data=_base_form(share_hub_image_1_url="img/poster-1.png"))
    assert resp.status_code in (200, 302)
    assert resolve_share_image_url("img/poster-1.png")
    from apps.config.cascade import resolve

    assert resolve(SHARE_HUB_IMAGE_1_URL, tenant_id=seeded.id, default="") == "img/poster-1.png"


def test_preferences_rejects_a_cross_origin_image_url(admin_client, seeded):
    resp = admin_client.post(
        PREFS_URL, data=_base_form(share_hub_image_1_url="https://evil.example.com/poster.png")
    )
    assert resp.status_code in (200, 302)
    from apps.config.cascade import resolve

    # Rejected — never persisted as the cross-origin value.
    assert resolve(SHARE_HUB_IMAGE_1_URL, tenant_id=seeded.id, default="") == ""


def test_preferences_leaves_both_image_fields_blank_by_default(admin_client, seeded):
    admin_client.post(PREFS_URL, data=_base_form())
    from apps.config.cascade import resolve

    assert resolve(SHARE_HUB_IMAGE_1_URL, tenant_id=seeded.id, default="SENTINEL") == ""
    assert resolve(SHARE_HUB_IMAGE_2_URL, tenant_id=seeded.id, default="SENTINEL") == ""
