"""T-056 — the share hub header shows the BROKER/PROGRAM brand, not the partner-company
name (a live post-deploy defect found in the T-055 header).

`Partner` is the AP/business (PIFS) that owns the GoRefer tenant. `ReferralProgram` is
the broker/product the referral is FOR (Zerodha today, Angel One or PolicyBazaar
tomorrow). Prod data has both on one `ReferralIdentity`, and they differ — the T-055
tests didn't catch this because they invented their own seed shape instead of using
`seed_program`'s prod-shaped data. This file locks the fallback chain
(`apps.accounts.hub._brand_name`) and the multi-program property directly, so this
class of error cannot pass again.

`tests/test_t055_hub_partner_header.py` keeps the header/DOM/attribution coverage;
only its two assertions that hardcoded the wrong (partner.name) semantics were fixed
in place, per the T-056 contract.
"""
from __future__ import annotations

import types

import pytest
from django.core.management import call_command
from django.template.loader import render_to_string

from apps.accounts.hub import _brand_name, hub_ctx
from apps.accounts.records_link import mint_records_token
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


# ------------------------------------------------------------- multi-program property


@HUB_URLS
def test_second_program_on_same_partner_shows_its_own_brand_only(client, seeded):
    """Two programs under the same Partner render their own brand only — never each
    other's and never a hardcoded literal (the source-literal test already covers
    "Zerodha"; this proves a second, dynamically-created brand also renders clean)."""
    partner = ReferralProgram.objects.get(tenant=seeded).partner
    program2 = ReferralProgram.objects.create(
        tenant=seeded,
        partner=partner,
        name="groww",
        display_name="Groww",
        status="active",
        regulator="sebi_nse",
    )
    identity2 = ReferralIdentity.objects.create(
        tenant=seeded, program=program2, partner=partner, client_id="GRW9001"
    )
    token = mint_records_token(identity2)
    body = client.get(f"/hub/{token}").content.decode()

    import re

    header = re.search(r'data-test="hub-partner-header".*?</header>', body, re.S).group(0)
    assert "Groww" in header
    assert "Zerodha" not in header


# ---------------------------------------------------------------------- fallback chain


def _stub_identity(*, program=None, partner=None):
    return types.SimpleNamespace(
        tenant_id=None,  # overwritten by the caller once a real tenant exists
        client_id=CID,
        program=program,
        partner=partner,
    )


def test_brand_name_prefers_program_display_name():
    program = types.SimpleNamespace(display_name="Zerodha", name="zerodha")
    partner = types.SimpleNamespace(name="Passive Income Financial Solutions Pvt Ltd")
    identity = _stub_identity(program=program, partner=partner)
    assert _brand_name(identity) == "Zerodha"


def test_brand_name_falls_back_to_program_name_when_display_name_empty():
    program = types.SimpleNamespace(display_name="", name="zerodha")
    partner = types.SimpleNamespace(name="Passive Income Financial Solutions Pvt Ltd")
    identity = _stub_identity(program=program, partner=partner)
    assert _brand_name(identity) == "zerodha"


def test_brand_name_falls_back_to_partner_name_when_no_program_at_all():
    partner = types.SimpleNamespace(name="Passive Income Financial Solutions Pvt Ltd")
    identity = _stub_identity(program=None, partner=partner)
    assert _brand_name(identity) == "Passive Income Financial Solutions Pvt Ltd"


def test_brand_name_is_empty_when_neither_program_nor_partner_present():
    identity = _stub_identity(program=None, partner=None)
    assert _brand_name(identity) == ""


def test_empty_brand_name_renders_no_blank_element_in_the_header(seeded):
    """Guards the real template's `{% if brand_name %}` wrapper: an identity with
    neither program nor partner (the ultimate fallback) must not leave a blank chip
    in the header — it degrades to the headline + attribution line alone. `hub_ctx`
    only needs `.tenant_id`/`.client_id` off `identity` plus the two brand fields, so
    a stub stands in without touching the DB's NOT NULL program/partner columns."""
    identity = _stub_identity(program=None, partner=None)
    identity.tenant_id = seeded.id
    ctx = hub_ctx(identity, "unused-token")
    assert ctx["brand_name"] == ""

    body = render_to_string("accounts/share_hub.html", ctx)
    header = body[body.index('data-test="hub-partner-header"') : body.index("</header>")]
    assert "hub-brand" not in header
    assert "hub-partner-header" in header


# ------------------------------------------------------------- attribution line intact


@HUB_URLS
def test_attribution_line_still_renders_and_differs_from_the_brand(client, seeded):
    """The page must not read as "<brand> via PIFS" where <brand> IS PIFS — brand and
    attribution are distinct strings, and both are present."""
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token)

    assert ctx["brand_name"]
    assert ctx["partner_attribution"]
    assert ctx["brand_name"] != ctx["partner_attribution"]

    body = client.get(f"/hub/{token}").content.decode()
    assert ctx["brand_name"] in body
    assert ctx["partner_attribution"] in body
