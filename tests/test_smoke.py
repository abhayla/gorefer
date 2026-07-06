"""Skeleton smoke tests: system check, health endpoint, home page render."""
from django.core.management import call_command
from django.test import Client


def test_django_system_check_clean():
    # Fails the build if the app registry / settings are misconfigured.
    call_command("check")


def test_health_endpoint_ok(db):
    resp = Client().get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "gorefer"


def test_health_endpoint_leaks_no_partner_code(db):
    # Guardrail sanity (full guardrail suite arrives with M2): no ZMPHZC in client responses.
    resp = Client().get("/api/health")
    assert "ZMPHZC" not in resp.content.decode()


def test_home_page_renders_compliance_footer(db):
    resp = Client().get("/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "market risks" in html  # risk warning present
    assert "AP2516003693" in html  # NSE AP reg no injected
