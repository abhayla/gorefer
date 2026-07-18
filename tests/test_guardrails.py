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
    """Static assertion (Fable5 M8): the ONLY code that assigns a conversion/account
    status is the Zoho ingest path. Rglob the WHOLE apps/ tree (not just 3 modules)
    excluding zoho/ingest.py, quoting/spacing-tolerant, so a FUTURE writer module in
    any app is caught by CI — not silently allowed."""
    import re
    from pathlib import Path

    apps_dir = Path(__file__).resolve().parent.parent / "apps"
    ingest_path = apps_dir / "integrations" / "zoho" / "ingest.py"

    # Assignment patterns (spacing-tolerant): `<field> =` (not `==`), and any
    # assignment of the literal 'account_opened' to a .status attribute regardless of
    # quote style/spacing. These are the guardrail-#2 truth fields.
    field_assign = re.compile(r"\b(conversion_status|credited_referrer|account_opened_at)\s*=(?!=)")
    status_open = re.compile(r"\.status\s*=\s*['\"]account_opened['\"]")

    offenders = []
    for py in apps_dir.rglob("*.py"):
        if py == ingest_path or "__pycache__" in py.parts or "migrations" in py.parts:
            continue
        # Ignore the read-side query that FILTERS on these (…filter(status=…)); we only
        # flag direct attribute assignment, which is what mutates truth.
        src = py.read_text(encoding="utf-8")
        for m in field_assign.finditer(src):
            line = src[src.rfind("\n", 0, m.start()) + 1: m.end() + 30]
            stripped = line.strip()
            # Skip: (a) ORM field DEFINITIONS (`x = models.…`) — declarations, not
            # mutations; (b) kwargs inside filter/get/exclude/values() calls — reads.
            if "models." in stripped:
                continue
            if any(f"{fn}(" in line for fn in ("filter", "get", "exclude", "values")):
                continue
            offenders.append(f"{py.relative_to(apps_dir)}: {stripped[:70]}")
        if status_open.search(src):
            offenders.append(f"{py.relative_to(apps_dir)}: .status = 'account_opened'")

    assert not offenders, (
        "conversion/account status assigned OUTSIDE zoho/ingest.py (guardrail #2): "
        + "; ".join(offenders)
    )
    # The Zoho ingest module IS the sole writer.
    assert "conversion_status =" in ingest_path.read_text(encoding="utf-8")


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
