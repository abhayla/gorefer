"""3-tier config cascade + compliance lock (ADR-022)."""
import pytest

from apps.config.cascade import resolve
from apps.config.models import ConfigCentral, ConfigGlobal
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="PIFS", slug="pifs")


def test_central_baseline_resolves(db):
    ConfigCentral.objects.create(key="attribution_window_days", value=60)
    assert resolve("attribution_window_days") == 60


def test_global_overrides_central(db, tenant):
    ConfigCentral.objects.create(key="theme_color", value="blue")
    ConfigGlobal.objects.create(tenant=tenant, key="theme_color", value="green")
    assert resolve("theme_color", tenant_id=tenant.id) == "green"
    # Without a tenant, central still wins.
    assert resolve("theme_color") == "blue"


def test_compliance_key_cannot_be_weakened_by_lower_tier(db, tenant):
    ConfigCentral.objects.create(key="referral_incentive_claim", value="OFFICIAL claim")
    # A tenant tries to override a compliance-locked key — must be ignored.
    ConfigGlobal.objects.create(tenant=tenant, key="referral_incentive_claim", value="MISLEADING claim")
    assert resolve("referral_incentive_claim", tenant_id=tenant.id) == "OFFICIAL claim"


def test_missing_key_raises_without_default(db):
    with pytest.raises(KeyError):
        resolve("does_not_exist")


def test_missing_key_returns_default(db):
    assert resolve("does_not_exist", default="fallback") == "fallback"
