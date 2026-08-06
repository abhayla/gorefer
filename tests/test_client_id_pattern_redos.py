"""T-048 — ReDoS guard on the admin-editable `client_id_pattern`.

`client_id_pattern` is CONFIGURATION an operator edits, and it is then run against
attacker-supplied input on the public `/r/{client_id}` path. Python's `re` has no
timeout, so a pattern with a nested quantifier backtracks exponentially and pins the
worker thread handling that request.

The guard screens the pattern statically and, when it is unsafe, reuses the EXISTING
safe-degrade path — fall back to the loose spec rule and log loudly — so a bad config
never 400s a real referral link. Both halves are asserted here: it must not hang, and
it must still let a valid id through.
"""
from __future__ import annotations

import time

import pytest
from django.test import Client

from apps.config.cascade import set_tenant
from apps.referrals.validators import (
    MAX_PATTERN_LENGTH,
    InvalidClientId,
    is_safe_pattern,
    validate_client_id,
)

# The classic catastrophic-backtracking shapes.
PATHOLOGICAL = ["(a+)+$", "^(a|a)*$", "^((ab)*)+$", "^(a+)+(b+)+$", "^(\\w+\\s?)*$"]
# Real-world patterns that must stay usable.
SAFE = [
    r"^[A-Z][A-Z0-9]{5}$",          # the live Zerodha pattern
    r"^(RJ|DA)[0-9]{4}$",           # unquantified alternation is fine
    r"^[A-Za-z0-9]{4,16}$",
    r"[a-z]+",
]


@pytest.mark.parametrize("pattern", PATHOLOGICAL)
def test_pathological_patterns_are_rejected(pattern):
    assert is_safe_pattern(pattern) is False


@pytest.mark.parametrize("pattern", SAFE)
def test_real_patterns_stay_allowed(pattern):
    assert is_safe_pattern(pattern) is True


def test_oversized_pattern_is_rejected():
    assert is_safe_pattern("a" * (MAX_PATTERN_LENGTH + 1)) is False


@pytest.mark.parametrize("pattern", PATHOLOGICAL)
def test_unsafe_pattern_degrades_to_the_spec_rule_without_hanging(pattern):
    """The behaviour contract: no hang, and the spec-valid id is ACCEPTED, not rejected.

    Degrading (not rejecting) is deliberate and pre-existing — a broken/unsafe pattern
    must never take the redirect path down for every referrer.
    """
    started = time.monotonic()
    assert validate_client_id("aaaaaaaaaaaaaaab", pattern=pattern) == "AAAAAAAAAAAAAAAB"
    assert time.monotonic() - started < 1.0


def test_safe_pattern_still_narrows(db):
    """The guard must not weaken a good pattern: a non-matching id is still refused."""
    assert validate_client_id("RJ4521", pattern=r"^[A-Z][A-Z0-9]{5}$") == "RJ4521"
    with pytest.raises(InvalidClientId):
        validate_client_id("ZZ", pattern=r"^[A-Z][A-Z0-9]{5}$")


def test_redirect_survives_a_pathological_configured_pattern(db):
    """END-TO-END: a hostile pattern in live config cannot hang `/r/{client_id}`."""
    from django.core.management import call_command

    from apps.tenants.resolve import get_bootstrap_tenant

    call_command("seed_program")
    tenant = get_bootstrap_tenant()
    set_tenant("client_id_pattern__ZMPHZC", "(a+)+$", tenant_id=tenant.id)

    started = time.monotonic()
    response = Client().get("/r/aaaaaaaaaaaaaaab")
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"redirect took {elapsed:.1f}s — the pattern was actually run"
    # 200 = the branded landing page (default landing_mode), 302 = direct-redirect mode.
    # Either proves the request was SERVED, not hung, and that a spec-valid id still
    # resolves rather than being refused because the config was bad.
    assert response.status_code in (200, 301, 302)
