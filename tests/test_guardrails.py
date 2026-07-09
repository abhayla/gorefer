"""The three guardrail tests (implementation/10 §6, CLAUDE.md §7 DoD).

Non-negotiable invariants. #1 and #3 are ACTIVE as of M2 (the redirect path
exists). #2 stays scaffolded until the Zoho import path exists (M6).
"""
import inspect
import socket

import pytest
from django.core.management import call_command
from django.test import Client

from apps.referrals import redirect_service, views

# --- Guardrail #1: the redirect service never POSTs/submits to Zerodha -----

def test_redirect_service_never_posts_to_zerodha():
    """Static assertion: no outbound HTTP call lives in the redirect service or
    views. The ONLY compliant path is a 302 of a real browser; Zerodha's reCAPTCHA
    form must never be auto/bot-submitted."""
    for module in (redirect_service, views):
        src = inspect.getsource(module)
        for forbidden in (
            "requests.post",
            "requests.get",
            "urlopen",
            "urllib.request",
            "http.client",
            ".submit(",
        ):
            assert forbidden not in src, f"{module.__name__} must not perform outbound HTTP ({forbidden})"


def test_redirect_service_imports_no_http_client():
    """The service assembles a URL only — it must not even import an HTTP client."""
    src = inspect.getsource(redirect_service)
    assert "import requests" not in src
    assert "urllib" not in src


@pytest.mark.django_db(transaction=True)
def test_redirect_makes_no_network_connection(monkeypatch):
    """Behavioural: exercising the redirect opens NO socket. Any outbound
    connection attempt (i.e. an actual submit to Zerodha) explodes the test."""
    real_connect = socket.socket.connect

    def _guarded_connect(self, address):  # pragma: no cover - only trips on violation
        raise AssertionError(f"redirect path attempted a network connection to {address}")

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    try:
        call_command("seed_program")
        c = Client()
        # Landing render (M3) opens no socket...
        assert c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7").status_code == 200
        # ...and the Continue 302 assembles the URL without ever connecting to Zerodha.
        resp = c.get("/r/RJ4521/continue", HTTP_USER_AGENT="Mozilla/5.0")
        assert resp.status_code == 302
    finally:
        monkeypatch.setattr(socket.socket, "connect", real_connect)


# --- Guardrail #3: no raw Zerodha URL / partner code in client-facing body -

@pytest.mark.django_db
def test_no_partner_code_in_client_facing_response_bodies():
    """The partner code and raw Zerodha URL are server-side only. They may appear
    in the 302 Location header (that IS the redirect), but NEVER in a rendered
    response BODY a user sees."""
    call_command("seed_program")
    # Prime a journey so the landing renders fully.
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    # Include the Track-B client-facing surfaces: the channel-path landing (B1) and
    # the disclosure page (B2) — the code/URL must never appear in any rendered body.
    for path in ("/", "/api/health", "/r/RJ4521", "/r/wa/RJ4521", "/open", "/d/pifs"):
        resp = c.get(path, HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
        body = resp.content.decode()
        assert "ZMPHZC" not in body, f"partner code leaked in body of {path}"
        assert "signup.zerodha.com" not in body, f"raw Zerodha URL leaked in body of {path}"


# --- Guardrail #2 (ACTIVE, M6): account/conversion status ONLY from Zoho -----

def test_conversion_status_only_written_by_zoho_ingest_path():
    """Static assertion: the ONLY code that sets a conversion/account status is the
    Zoho ingest path. No other module writes Conversion.status / .account_opened_at
    / referral.credited_referrer / referral.conversion_status."""
    import inspect

    from apps.integrations.zoho import ingest as zoho_ingest
    from apps.referrals import lead_service, redirect_service, views

    forbidden_writes = (
        "conversion_status =",
        "credited_referrer =",
        "account_opened_at =",
        ".status = \"account_opened\"",
        "status='account_opened'",
    )
    # These non-Zoho modules must NOT set conversion/account status.
    for module in (lead_service, redirect_service, views):
        src = inspect.getsource(module)
        for token in forbidden_writes:
            assert token not in src, f"{module.__name__} must not set conversion status ({token})"
    # The Zoho ingest module IS allowed to (it's the sole writer).
    assert "conversion_status =" in inspect.getsource(zoho_ingest)


@pytest.mark.django_db(transaction=True)
def test_lead_capture_never_sets_account_opened():
    """Behavioural: a full lead capture (no Zoho webhook) produces NO account_opened
    event and leaves conversion status empty — never fabricated internally."""
    from django.test import Client

    from apps.events.models import Event
    from apps.referrals.models import Referral

    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    c.post(
        "/api/leads/",
        data={"client_id": "RJ4521", "name": "Rahul", "mobile": "9876543210", "consent": True},
        content_type="application/json",
    )
    assert Event.objects.filter(event_type="account_opened").count() == 0
    referral = Referral.objects.get(source="referral_link")
    assert referral.conversion_status == ""      # never set outside Zoho
    assert referral.credited_referrer == ""
    assert referral.account_opened_at is None
