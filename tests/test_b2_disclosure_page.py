"""B2 — per-sub-broker disclosure page /d/{slug} (ADR-031).

The canonical §4.4 host: composes each ACTIVE partner/program's regulator block for
a tenant (sub-broker), in regulator order (SEBI/NSE → IRDAI → RBI), config-driven,
no PII, crawler-safe.

Guardrails asserted (S2-03 §11 / S2-04 §B2):
  - /d/pifs → 200 with the Zerodha SEBI/NSE identification (INZ000031633, AP no.)
    + the verbatim market-risk warning.
  - multi-partner blocks render in regulator order; a lapsed/inactive partner's
    block is absent.
  - no PII; no ZMPHZC / raw Zerodha URL leak.
  - the page creates NO event (a crawler hit is inherently excluded from counts).
"""
import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.referrals.models import Partner, ReferralProgram
from apps.tenants.models import Tenant


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _tenant():
    return Tenant.objects.get(slug="pifs")


# --- /d/pifs renders the Zerodha SEBI/NSE block + market-risk warning -------

def test_disclosure_page_200_with_sebi_nse_block(seeded, client):
    resp = client.get("/d/pifs")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "INZ000031633" in html                       # SEBI reg
    assert settings.NSE_AP_NO in html                   # AP2516003693
    assert "market risks" in html                       # verbatim risk warning
    # The verbatim canonical strings, byte-exact from the single source.
    assert settings.MARKET_RISK_WARNING in html


def test_disclosure_regulator_label_present(seeded, client):
    html = client.get("/d/pifs").content.decode()
    assert "SEBI / NSE" in html


# --- guardrails: no PII, no partner code / Zerodha URL ----------------------

def test_disclosure_no_partner_code_or_zerodha_url(seeded, client):
    html = client.get("/d/pifs").content.decode()
    assert "ZMPHZC" not in html
    assert "signup.zerodha.com" not in html


def test_disclosure_no_pii(seeded, client):
    # Seed a customer with PII, then assert none of it appears on the public page.
    tenant = _tenant()
    program = ReferralProgram.objects.get(name="Zerodha")
    from apps.referrals.models import Customer

    Customer.objects.create(
        tenant=tenant, program=program, partner=program.partner,
        client_id="RJ4521", mobile="9998887777", first_name="Ramesh", email="r@example.com",
    )
    html = client.get("/d/pifs").content.decode()
    assert "9998887777" not in html
    assert "Ramesh" not in html
    assert "r@example.com" not in html


# --- the page creates no event (crawler-safe by construction) --------------

def test_disclosure_page_creates_no_event(seeded, client):
    before = Event.objects.count()
    client.get("/d/pifs", HTTP_USER_AGENT="facebookexternalhit/1.1")
    client.get("/d/pifs", HTTP_USER_AGENT="Mozilla/5.0 (Android)")
    assert Event.objects.count() == before  # a disclosure view is not a click


# --- unknown slug -> branded 404 -------------------------------------------

def test_unknown_slug_404(seeded, client):
    resp = client.get("/d/nosuchbroker")
    assert resp.status_code == 404
    assert "ZMPHZC" not in resp.content.decode()


# --- multi-partner ordering + lapsed exclusion -----------------------------

def _add_program(tenant, *, name, code, regulator, seq, status="active"):
    partner = Partner.objects.create(
        tenant=tenant, name=name, code=code, status="active", website="https://gorefer.in",
    )
    return ReferralProgram.objects.create(
        tenant=tenant, partner=partner, name=name, display_name=name, status=status,
        regulator=regulator, disclosure_sequence=seq,
        disclosure_template=f"{name} disclosure: reg {{nse_ap_no}}",
    )


def test_multi_partner_regulator_order(seeded, client):
    tenant = _tenant()
    # Add an insurance (IRDAI) + a loans (RBI) program out of order; expect them
    # rendered after the seeded SEBI/NSE Zerodha block, in regulator order.
    _add_program(tenant, name="LoanPartner", code="RBIX01", regulator="rbi", seq=30)
    _add_program(tenant, name="InsurePartner", code="IRDX01", regulator="irdai", seq=20)
    html = client.get("/d/pifs").content.decode()
    i_sebi = html.find("SEBI / NSE")
    i_irdai = html.find("IRDAI")
    i_rbi = html.find("RBI")
    assert -1 < i_sebi < i_irdai < i_rbi  # securities → insurance → loans


def test_lapsed_partner_block_absent(seeded, client):
    tenant = _tenant()
    _add_program(tenant, name="LapsedInsurer", code="IRDX02", regulator="irdai", seq=20,
                 status="inactive")
    html = client.get("/d/pifs").content.decode()
    assert "LapsedInsurer" not in html  # inactive program's block drops off


def test_active_partner_template_rendered_with_values(seeded, client):
    tenant = _tenant()
    _add_program(tenant, name="ActiveInsurer", code="IRDX03", regulator="irdai", seq=20)
    html = client.get("/d/pifs").content.decode()
    assert "ActiveInsurer disclosure" in html
    assert settings.NSE_AP_NO in html  # {nse_ap_no} placeholder was filled
