"""T-047 — CSRF + proper session auth on the staff-scoped Ninja API routes.

The defect this locks down: `/api/followups/*` (staff CRUD for the follow-up cadence)
authenticated the Django session cookie with a plain callable, and every django-ninja
view is `csrf_exempt` at the Django middleware level. So a logged-in staff member
visiting any malicious page could have their browser silently POST/PATCH/DELETE
follow-up rules — classic cross-site request forgery, with the session cookie riding
along automatically.

The fix is narrow ON PURPOSE. CSRF is enforced by the AUTH OBJECT (Ninja's
`APIKeyCookie.__get_key__` runs `check_csrf` before authenticating), not by the
`NinjaAPI`, so switching only the cookie-authed routers to a `SessionAuth` subclass
protects them while leaving every cookie-less caller untouched:

  route                        auth                        CSRF token required?
  ---------------------------  --------------------------  --------------------
  /api/followups/*             session cookie (staff)      YES (unsafe methods)
  /api/analytics/*             session cookie (staff)      n/a — GET only
  /api/leads/, /api/share/     public capture (no auth)    no
  /api/click/*                 public beacon (no auth)     no
  /api/wati/webhook, /inbound  static key + IP allowlist   no (server-to-server)
  /api/zoho/status-webhook     HMAC seal / static key      no (server-to-server)
  /api/health                  public                      no

Both halves are asserted below. A blanket `csrf=True` on the NinjaAPI would 403 the
webhooks and break the live conversion pipe — the tests at the bottom are the tripwire
for anyone who tries it.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.followups.models import FollowupRule
from apps.tenants.resolve import get_bootstrap_tenant

RULES = "/api/followups/rules"


@pytest.fixture
def seeded(db, settings):
    settings.WATI_WEBHOOK_KEY = "testkey"
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")


def _staff_user(username="csrf-tester"):
    U = get_user_model()
    u = U.objects.create(username=username, is_staff=True, is_active=True)
    u.set_password("x")
    u.save()
    return u


def _csrf_client(*, login=True):
    """A client that ENFORCES CSRF (unlike the default test client) plus a real token.

    `enforce_csrf_checks=True` removes the test client's `_dont_enforce_csrf_checks`
    escape hatch, so this exercises the same code path a real browser hits. The token
    comes from a real page render (`{% csrf_token %}` on the admin login screen), which
    also plants the `csrftoken` cookie — token and cookie must agree or Django rejects.
    """
    c = Client(enforce_csrf_checks=True)
    c.get("/admin-panel/login/")  # renders {% csrf_token %} -> sets the cookie
    token = c.cookies["csrftoken"].value
    if login:
        c.force_login(_staff_user())
    return c, token


RULE_PAYLOAD = {
    "step_key": "csrf_probe",
    "offset_minutes": 30,
    "body_en": "hello",
}


# --- the hole this task closes ------------------------------------------------

def test_staff_post_without_csrf_token_is_rejected(seeded):
    """The actual CSRF attack: valid staff session, no token. Must NOT create a rule."""
    c, _token = _csrf_client()
    r = c.post(RULES, data=json.dumps(RULE_PAYLOAD), content_type="application/json")
    assert r.status_code == 403
    assert not FollowupRule.objects.filter(step_key="csrf_probe").exists()


def test_staff_post_with_wrong_csrf_token_is_rejected(seeded):
    c, _token = _csrf_client()
    r = c.post(RULES, data=json.dumps(RULE_PAYLOAD), content_type="application/json",
               HTTP_X_CSRFTOKEN="not-the-real-token")
    assert r.status_code == 403
    assert not FollowupRule.objects.filter(step_key="csrf_probe").exists()


def test_staff_post_with_valid_csrf_token_succeeds(seeded):
    """The legitimate path still works — the fix must not break staff CRUD."""
    c, token = _csrf_client()
    r = c.post(RULES, data=json.dumps(RULE_PAYLOAD), content_type="application/json",
               HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 201, r.content
    assert FollowupRule.objects.filter(step_key="csrf_probe").exists()


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_staff_patch_and_delete_without_csrf_token_are_rejected(seeded, method):
    tenant = get_bootstrap_tenant()
    rule = FollowupRule.objects.create(
        tenant=tenant, step_key="victim", offset_minutes=15, body_en="x",
    )
    c, _token = _csrf_client()
    url = f"{RULES}/{rule.id}"
    if method == "patch":
        r = c.patch(url, data=json.dumps({"offset_minutes": 999}),
                    content_type="application/json")
    else:
        r = c.delete(url)
    assert r.status_code == 403
    rule.refresh_from_db()          # still there, still untouched
    assert rule.offset_minutes == 15


def test_scheduled_action_without_csrf_token_is_rejected(seeded):
    """The /scheduled/{id}/cancel action is a POST too — same protection."""
    c, _token = _csrf_client()
    r = c.post("/api/followups/scheduled/1/cancel")
    assert r.status_code == 403


# --- auth layer: anonymous is refused by the auth class, not an ad-hoc check --

def test_anonymous_get_is_unauthorized(seeded):
    c = Client(enforce_csrf_checks=True)
    assert c.get(RULES).status_code == 401
    assert c.get("/api/analytics/funnel").status_code == 401


def test_non_staff_session_is_unauthorized(seeded):
    U = get_user_model()
    u = U.objects.create(username="plain-user", is_staff=False, is_active=True)
    u.set_password("x")
    u.save()
    c = Client(enforce_csrf_checks=True)
    c.force_login(u)
    assert c.get(RULES).status_code == 401


def test_staff_get_needs_no_csrf_token(seeded):
    """GET is a safe method — CSRF must not gate reads, or the dashboard breaks."""
    c, _token = _csrf_client()
    assert c.get(RULES).status_code == 200
    assert c.get("/api/analytics/funnel").status_code == 200


# --- the regression tripwire: cookie-less callers stay CSRF-exempt -----------

def test_wati_webhook_succeeds_with_key_and_no_csrf_token(seeded):
    """Server-to-server: Wati sends a static key, never a CSRF token or cookie."""
    c = Client(enforce_csrf_checks=True)
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")  # referrer identity exists
    r = c.post(
        "/api/wati/webhook",
        data=json.dumps({"client_id": "RJ4521", "name": "Ravi Kumar", "mobile": "9998887777"}),
        content_type="application/json",
        HTTP_X_WATI_WEBHOOK_KEY="testkey",
    )
    assert r.status_code == 200, r.content
    assert r.json()["lead_id"]


def test_zoho_status_webhook_succeeds_with_key_and_no_csrf_token(seeded):
    """Server-to-server: Zoho authenticates by seal/key — a CSRF 403 here would
    silently stop every account-opened conversion from landing."""
    c = Client(enforce_csrf_checks=True)
    r = c.post(
        "/api/zoho/status-webhook",
        data=json.dumps({
            "event_id": "csrf-probe-1",
            "opener_zerodha_account_id": "ZA900",
            "referrer_client_id": "RJ4521",
            "status": "Account Opened",
            "account_opened_at": "2026-05-10T09:00:00",
        }),
        content_type="application/json",
        HTTP_X_ZOHO_WEBHOOK_KEY="testkey",
    )
    assert r.status_code == 200, r.content


def test_public_lead_capture_succeeds_without_csrf_token(seeded):
    """The landing page posts /api/leads/ from fetch() with no CSRF token today."""
    c = Client(enforce_csrf_checks=True)
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    r = c.post(
        "/api/leads/",
        data=json.dumps({"client_id": "RJ4521", "name": "Rahul Sharma",
                         "mobile": "9876543210", "consent": True}),
        content_type="application/json",
    )
    assert r.status_code == 201, r.content


def test_public_click_confirm_succeeds_without_csrf_token(seeded):
    c = Client(enforce_csrf_checks=True)
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.5")
    r = c.post("/api/click/confirm",
               data=json.dumps({"client_id": "RJ4521", "nonce": "not-a-real-nonce"}),
               content_type="application/json")
    # 401 = the request reached the nonce check, i.e. it was NOT stopped by a CSRF gate.
    assert r.status_code == 401, r.content
