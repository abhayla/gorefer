"""The three guardrail tests (implementation/10 §6, CLAUDE.md §7 DoD).

These are the non-negotiable invariants every mission from M2 on must keep green.
In M1 the code paths they assert against (redirect service, Zoho import, client
responses) do not exist yet, so the tests are scaffolded and SKIPPED — visible in
the suite so they cannot be forgotten, and lit up in the mission that adds the
corresponding path.
"""
import pytest


@pytest.mark.skip(reason="M2: redirect service not built yet")
def test_redirect_service_never_posts_to_zerodha():
    """Guardrail 1: the redirect service must NEVER POST/submit to Zerodha.

    The only compliant path is a 302 redirect of a real human browser; Zerodha's
    form is reCAPTCHA-gated and must never be auto/bot-submitted (M2).
    """
    raise AssertionError("implement in M2")


@pytest.mark.skip(reason="M6: Zoho import path not built yet")
def test_account_status_only_settable_from_zoho_import():
    """Guardrail 2: account/conversion status can be set ONLY from a Zoho-sourced
    import path, never fabricated by an internal write (M6)."""
    raise AssertionError("implement in M6")


@pytest.mark.skip(reason="M2/M3: client-facing referral responses not built yet")
def test_no_raw_zerodha_url_or_partner_code_in_client_response():
    """Guardrail 3: no raw Zerodha URL or partner code appears in any client-facing
    response (M2/M3). The M1 smoke suite already asserts this for /api/health."""
    raise AssertionError("implement in M2/M3")
