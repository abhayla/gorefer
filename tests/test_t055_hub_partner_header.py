"""T-055 — the share hub gets a PARTNER header + a real share hierarchy.

Owner review of the live page (2026-08-08): the partner was invisible and nothing
pushed sharing. This locks down the fix, in the order it would cost to get wrong:

  - the partner NAME is read from the Partner DB record via the identity — never a
    literal — proven by renaming the row and watching the header change;
  - no partner-branded <img> anywhere (ADR-014: no logo, no resemblance);
  - the header + share hierarchy render in a fixed DOM order via data-test landmarks;
  - the T-053 security invariants (token never in a share href/prefill/event; the
    credit link is what every button carries) still hold — this task changed
    presentation only, never share-URL construction.

Deliberately a NEW file: tests/test_t053_share_hub.py is unmodified per the T-055
contract — this file only ADDS coverage for the new header + hierarchy.
"""
from __future__ import annotations

import re

import pytest
from django.core.management import call_command

from apps.accounts.hub import SHARE_BUTTONS, hub_ctx
from apps.accounts.records_link import mint_records_token
from apps.config.models import ConfigCentral
from apps.config.preferences import SHARE_HUB_PARTNER_ATTRIBUTION
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


# ------------------------------------------------------------------- partner header


@HUB_URLS
def test_prod_shaped_data_renders_program_brand_not_partner_company_name(client, seeded):
    """T-056: prod has Partner='Passive Income Financial Solutions Pvt Ltd' (PIFS, the
    AP) and ReferralProgram.display_name='Zerodha' (the broker) on the SAME identity —
    `seed_program` already seeds exactly this shape. The header must show the broker
    brand, never the partner-company name (that would read "PIFS ... via PIFS")."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()

    header = re.search(
        r'data-test="hub-partner-header".*?</header>', body, re.S
    ).group(0)
    assert identity.program.display_name in header
    assert identity.partner.name not in header


@HUB_URLS
def test_renaming_the_program_display_name_changes_the_rendered_header(client, seeded):
    """Proof the brand is DB-driven, not a code literal (CLAUDE.md §4)."""
    identity = _identity(seeded)
    token = mint_records_token(identity)

    ReferralProgram.objects.filter(pk=identity.program_id).update(display_name="Angel One")
    body = client.get(f"/hub/{token}").content.decode()

    header = re.search(
        r'data-test="hub-partner-header".*?</header>', body, re.S
    ).group(0)
    assert "Angel One" in header
    assert "Zerodha" not in header


def test_no_partner_name_literal_in_hub_module_source():
    import inspect

    import apps.accounts.hub as hub_module

    source = inspect.getsource(hub_module)
    assert "Zerodha" not in source


@HUB_URLS
def test_no_img_tag_on_the_page(client, seeded):
    """ADR-014: no partner logo/trademark — the page uses text + attribution only."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert "<img" not in body.lower()


@HUB_URLS
def test_pifs_attribution_is_present_and_config_driven(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert "PIFS" in body

    ConfigCentral.objects.update_or_create(
        key=SHARE_HUB_PARTNER_ATTRIBUTION, defaults={"value": "ATTRIBUTION-SENTINEL"}
    )
    body = client.get(f"/hub/{token}").content.decode()
    assert "ATTRIBUTION-SENTINEL" in body


# ------------------------------------------------------------------------- hierarchy


@HUB_URLS
def test_dom_landmark_order_is_header_link_cta_copy_channels_benefits_disclosures(
    client, seeded, settings
):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()

    landmarks = [
        'data-test="hub-partner-header"',
        'data-test="hub-my-link"',
        'data-test="hub-primary-cta"',
        'data-test="hub-copy-link"',
        'data-test="hub-secondary-channels"',
        'data-test="hub-benefits"',
        settings.AP_DISCLOSURE_BLOCK,
    ]
    positions = [body.index(marker) for marker in landmarks]
    assert positions == sorted(positions), "hub landmark order was scrambled"


@HUB_URLS
def test_the_primary_cta_is_whatsapp_and_is_a_single_large_button(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()

    match = re.search(
        r'<a[^>]+data-share-channel="([^"]+)"[^>]+data-test="hub-primary-cta"',
        body,
    )
    assert match is not None
    assert match.group(1) == "whatsapp"
    assert body.count('data-test="hub-primary-cta"') == 1


@HUB_URLS
def test_secondary_row_holds_the_remaining_channels_not_whatsapp(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()

    row = re.search(
        r'data-test="hub-secondary-channels".*?</div>', body, re.S
    ).group(0)
    secondary_channels = re.findall(r'data-share-channel="([^"]+)"', row)
    expected = sorted(
        b["event_channel"] for b in SHARE_BUTTONS if b["code"] != "wa"
    ) + ["native_share"]
    assert sorted(secondary_channels) == sorted(expected)
    assert "whatsapp" not in secondary_channels


# ---------------------------------------------------------- T-053 invariants, unmoved


@HUB_URLS
def test_share_hierarchy_change_does_not_alter_the_credit_link_or_token_safety(
    client, seeded
):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token)
    body = client.get(f"/hub/{token}").content.decode()

    for button in ctx["buttons"]:
        assert token not in button["href"]
    assert "RJ4521" in ctx["primary_button"]["href"] or "RJ4521" in body
    hrefs = re.findall(r"""<a\s+href=["']([^"']+)["'][^>]*data-share-channel=""", body)
    assert len(hrefs) == len(SHARE_BUTTONS)
    for href in hrefs:
        assert token not in href
