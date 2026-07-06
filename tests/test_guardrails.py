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
    for path in ("/", "/api/health", "/r/RJ4521", "/open"):
        resp = c.get(path, HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
        body = resp.content.decode()
        assert "ZMPHZC" not in body, f"partner code leaked in body of {path}"
        assert "signup.zerodha.com" not in body, f"raw Zerodha URL leaked in body of {path}"


# --- Guardrail #2: account-status only from Zoho import (M6) ----------------

@pytest.mark.skip(reason="M6: Zoho import path not built yet")
def test_account_status_only_settable_from_zoho_import():
    raise AssertionError("implement in M6")
