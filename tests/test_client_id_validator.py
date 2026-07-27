"""client_id format validator (ADR-008 / Gap 3 — format only, no ownership check)."""
import pytest

from apps.referrals.validators import InvalidClientId, validate_client_id


@pytest.mark.parametrize(
    "raw,expected", [("RJ4521", "RJ4521"), ("da1707", "DA1707"), ("  RJ4521  ", "RJ4521")]
)
def test_valid_ids_normalize_uppercase(raw, expected):
    assert validate_client_id(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "", "   ", None,
        "RJ-4521", "RJ 4521", "RJ/4521", "<script>",
        "abc",          # 3 chars — below the spec's 4-char minimum (A-min)
        "a" * 17,       # 17 chars — above the spec's 16-char maximum (A-min)
        "a" * 21,       # oversized
    ],
)
def test_invalid_ids_rejected(bad):
    with pytest.raises(InvalidClientId):
        validate_client_id(bad)


@pytest.mark.parametrize("ok", ["RJ45", "a" * 16, "DA1707"])
def test_boundary_lengths_accepted(ok):
    # 4 and 16 chars are the inclusive bounds (06-API §4.1).
    assert validate_client_id(ok) == ok.upper()


# --- per-partner STRICT rule (owner decision 2026-07-27) ---------------------
#
# The loose spec rule above stays for LOOKUP paths. Paths that CREATE an identity
# (/r/, /share/, the Wati webhook) validate against the partner's own pattern, because
# the loose rule let a leaked chatbot menu label become a real referrer called `TALK`.

from apps.referrals.validators import (  # noqa: E402
    ZERODHA_CLIENT_ID_PATTERN,
    resolve_client_id_pattern,
    validate_client_id_for,
)

# Every real client id observed in production (2026-07-27).
REAL_PROD_IDS = [
    "AB1234", "CQX688", "DA1707", "EKU497", "FWW808", "GW5500", "MK9033",
    "RJ4521", "SG2210", "YT9788", "YTW629", "YW0175", "ZD9598", "ZZ8962",
]

# Junk that reached production through the loose rule, or our own test ids.
JUNK_IDS = ["ABHAY", "TALK", "E2E0726", "E2EBOTVERIFY", "FCLIVE01", "PRODWA01", "REVW2607"]


@pytest.mark.parametrize("cid", REAL_PROD_IDS)
def test_every_real_production_id_survives_the_strict_rule(cid):
    """The whole risk of tightening is breaking a REAL referrer's link.

    This is the regression guard for that: all 14 distinct real client ids observed in
    prod on 2026-07-27, asserted individually so a future pattern change names the one
    it would break.
    """
    assert validate_client_id(cid, pattern=ZERODHA_CLIENT_ID_PATTERN) == cid


@pytest.mark.parametrize("cid", JUNK_IDS)
def test_junk_ids_are_refused_by_the_strict_rule(cid):
    with pytest.raises(InvalidClientId):
        validate_client_id(cid, pattern=ZERODHA_CLIENT_ID_PATTERN)


def test_strict_rule_is_exactly_six_starting_with_a_letter():
    """Owner-specified shape: 6 chars, first a LETTER, rest letters or digits."""
    for ok in ("A12345", "ABCDEF", "RJ4521", "Z9Z9Z9"):
        assert validate_client_id(ok, pattern=ZERODHA_CLIENT_ID_PATTERN) == ok
    for bad in ("12345A", "A1234", "A123456"):  # digit-first, 5 chars, 7 chars
        with pytest.raises(InvalidClientId):
            validate_client_id(bad, pattern=ZERODHA_CLIENT_ID_PATTERN)


def test_a_pattern_can_only_narrow_never_widen():
    """A misconfigured pattern must not admit what the SPEC rule already rejects."""
    with pytest.raises(InvalidClientId):
        validate_client_id("RJ 4521", pattern=r"^.*$")   # space — illegal chars
    with pytest.raises(InvalidClientId):
        validate_client_id("abc", pattern=r"^.*$")       # 3 chars — under the minimum


def test_a_broken_pattern_degrades_to_the_spec_rule_instead_of_blocking_everything():
    """An unparseable regex in config must not 400 every link for that partner.

    Failing OPEN here is deliberate and narrow: the spec rule still applies, so the
    blast radius of a config typo is "strictness lost", not "referrals down".
    """
    assert validate_client_id("RJ4521", pattern=r"^[unclosed") == "RJ4521"


@pytest.mark.django_db
def test_pattern_is_configuration_resolved_per_partner(settings):
    """CLAUDE.md §6d — the pattern is config, keyed by the partner's OWN code."""
    from django.core.management import call_command

    from apps.config.cascade import set_tenant
    from apps.referrals.validators import PATTERN_KEY
    from apps.tenants.models import Tenant

    call_command("seed_program")
    tenant = Tenant.objects.get(slug="pifs")

    # Seeded centrally for the active partner.
    assert resolve_client_id_pattern(tenant.id, settings.PARTNER_CODE) == ZERODHA_CLIENT_ID_PATTERN
    # An unknown partner falls back to the generic key (none set) -> no extra constraint.
    assert resolve_client_id_pattern(tenant.id, "NOSUCH") == ""
    # A tenant-level generic default applies when no per-partner key exists.
    set_tenant(PATTERN_KEY, r"^[A-Z]{4}$", tenant_id=tenant.id)
    assert resolve_client_id_pattern(tenant.id, "NOSUCH") == r"^[A-Z]{4}$"
    # ...but the per-partner key still WINS over the generic one.
    assert resolve_client_id_pattern(tenant.id, settings.PARTNER_CODE) == ZERODHA_CLIENT_ID_PATTERN


@pytest.mark.django_db
def test_validate_for_tenant_uses_the_active_partners_pattern():
    from django.core.management import call_command

    from apps.tenants.models import Tenant

    call_command("seed_program")
    tenant = Tenant.objects.get(slug="pifs")
    assert validate_client_id_for(tenant, "da1707") == "DA1707"
    with pytest.raises(InvalidClientId):
        validate_client_id_for(tenant, "ABHAY")


@pytest.mark.django_db
def test_no_program_configured_falls_back_to_the_spec_rule():
    """A config gap must never take the redirect path down."""
    assert validate_client_id_for(None, "ABHAY") == "ABHAY"
