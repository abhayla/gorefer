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


def test_worker_health_endpoint_ok(db, settings):
    # T-149: public, no-auth probe for external monitoring (the Notifier probe, T-151).
    settings.Q_CLUSTER = {**settings.Q_CLUSTER, "sync": True}
    resp = Client().get("/api/health/worker")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "gorefer"
    assert body["state"] in ("healthy", "stale", "unknown")
    assert "last_success_at" in body


def test_worker_health_endpoint_requires_no_auth(db):
    # A monitoring probe that needed a session/API key couldn't be polled externally.
    resp = Client().get("/api/health/worker")
    assert resp.status_code == 200


def test_home_page_renders_compliance_footer(db):
    resp = Client().get("/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "market risks" in html  # risk warning present
    assert "AP2516003693" in html  # NSE AP reg no injected
