"""Feature-flag module tests (implementation/10 §4)."""
from gorefer.flags import FeatureFlags, flags


def test_default_flags_match_spec():
    f = FeatureFlags()
    assert f.ENABLE_CUSTOMER_LOGIN is False
    assert f.ENABLE_WATI_SEND is False
    assert f.ENABLE_ZOHO_WRITE is False
    assert f.ENABLE_ASSET_GENERATOR is False
    assert f.ENABLE_ADMIN_DASHBOARD is True
    assert f.ENABLE_DEMO_MODE is True
    assert f.REFERRAL_INCENTIVE_CLAIM == "300 reward points + 10% brokerage share"


def test_env_override_parses_bool(monkeypatch):
    monkeypatch.setenv("ENABLE_WATI_SEND", "true")
    monkeypatch.setenv("ENABLE_ADMIN_DASHBOARD", "false")
    f = FeatureFlags.from_env()
    assert f.ENABLE_WATI_SEND is True
    assert f.ENABLE_ADMIN_DASHBOARD is False


def test_incentive_claim_is_single_swappable_field(monkeypatch):
    monkeypatch.setenv("REFERRAL_INCENTIVE_CLAIM", "custom claim")
    f = FeatureFlags.from_env()
    assert f.REFERRAL_INCENTIVE_CLAIM == "custom claim"


def test_process_flags_snapshot_importable():
    assert isinstance(flags, FeatureFlags)
