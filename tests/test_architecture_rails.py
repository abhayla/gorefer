"""Rails E-1 + E-2 (doc 16 §5, ADR-044): the compliance lock must guard reality.

E-1 (partial, Phase-0 scope): every COMPLIANCE_LOCKED key is seeded into central
by seed_program, so the lock never again protects rows that don't exist (doc 16
D-1: `ap_disclosure_block` was locked but never seeded, and none of the locked
keys had a production reader).

E-2: the rendered compliance surfaces track the LOCKED resolver — byte-identical
to the canonical settings values on a fresh database, live to a central-row edit,
and immune to a tenant-tier override attempt.
"""
from __future__ import annotations

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.config.models import COMPLIANCE_LOCKED_KEYS, ConfigCentral, ConfigGlobal
from apps.tenants.models import Tenant


@pytest.mark.django_db
def test_e1_every_locked_key_is_seeded():
    call_command("seed_program")
    seeded = set(
        ConfigCentral.objects.filter(key__in=COMPLIANCE_LOCKED_KEYS).values_list("key", flat=True)
    )
    missing = set(COMPLIANCE_LOCKED_KEYS) - seeded
    assert not missing, (
        f"compliance-locked keys with no seeded central row: {sorted(missing)} — "
        "a locked key without a row is the doc 16 D-1 defect recurring."
    )


@pytest.mark.django_db
def test_e2_render_is_byte_identical_to_settings_on_fresh_db(client):
    html = client.get("/").content.decode()
    assert settings.AP_DISCLOSURE_BLOCK in html
    assert settings.MARKET_RISK_WARNING in html


@pytest.mark.django_db
def test_e2_render_tracks_the_central_row(client):
    ConfigCentral.objects.update_or_create(
        key="ap_disclosure_block", defaults={"value": "CENTRAL-E2-DISCLOSURE-SENTINEL"}
    )
    html = client.get("/").content.decode()
    assert "CENTRAL-E2-DISCLOSURE-SENTINEL" in html, (
        "central compliance row edited but the rendered page did not follow — the "
        "render path is not reading the locked resolver (doc 16 D-1)."
    )


@pytest.mark.django_db
def test_e2_tenant_tier_cannot_alter_the_rendered_compliance_text(client):
    tenant = Tenant.objects.create(name="PIFS", slug="pifs")
    # Written via the ORM on purpose: set_tenant() already refuses locked keys, so
    # this simulates a hostile/buggy direct write. The resolver must ignore it.
    ConfigGlobal.objects.create(
        tenant=tenant, key="ap_disclosure_block", value="TENANT-WEAKENED-BLOCK"
    )
    html = client.get("/").content.decode()
    assert "TENANT-WEAKENED-BLOCK" not in html
    assert settings.AP_DISCLOSURE_BLOCK in html
