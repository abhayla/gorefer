"""Fable5 H3 — rate limiting on public API endpoints + login lockout, and the
ClickNonce purge sweep.

RATELIMIT_ENABLED is off in dev/CI by default, so each test flips it on explicitly.
"""
from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client


@pytest.fixture(autouse=True)
def _clear_cache(request):
    # The DB cache needs DB access; only clear it for tests that enable the DB.
    has_db = "db" in request.fixturenames or "transactional_db" in request.fixturenames
    if has_db:
        cache.clear()
    yield
    if has_db:
        cache.clear()


@pytest.fixture
def seeded(db):
    call_command("seed_program")


# --- ratelimit primitive ---------------------------------------------------

@pytest.mark.django_db
def test_ratelimit_disabled_is_noop(settings):
    from apps.common.ratelimit import hit

    settings.RATELIMIT_ENABLED = False
    for _ in range(100):
        allowed, _ra = hit("x", "1.2.3.4", limit=3, window=60)
        assert allowed


@pytest.mark.django_db
def test_ratelimit_blocks_past_limit(settings):
    from apps.common.ratelimit import RateLimited, check_rate

    settings.RATELIMIT_ENABLED = True
    for _ in range(3):
        check_rate("x", "1.2.3.4", limit=3, window=60)  # 3 allowed
    with pytest.raises(RateLimited):
        check_rate("x", "1.2.3.4", limit=3, window=60)  # 4th blocked
    # A different ident is independent.
    check_rate("x", "9.9.9.9", limit=3, window=60)


# --- /api/leads throttle ---------------------------------------------------

@pytest.mark.django_db
def test_leads_endpoint_429_past_limit(settings, seeded):
    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_LEADS_MAX = 2
    settings.RATELIMIT_API_WINDOW = 60
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")  # create the journey
    body = {"client_id": "RJ4521", "name": "Rahul Kumar", "mobile": "9876543210", "consent": True}
    codes = []
    for _ in range(4):
        r = c.post("/api/leads/", data=json.dumps(body), content_type="application/json",
                   HTTP_X_FORWARDED_FOR="203.0.113.9")
        codes.append(r.status_code)
    assert 429 in codes, f"expected a 429 after the limit, got {codes}"


# --- /api/share throttle ---------------------------------------------------

@pytest.mark.django_db
def test_share_endpoint_429_past_limit(settings, seeded):
    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_SHARE_MAX = 2
    settings.RATELIMIT_API_WINDOW = 60
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    codes = [
        c.post("/api/share/", data=json.dumps({"client_id": "RJ4521", "channel": "whatsapp"}),
               content_type="application/json", HTTP_X_FORWARDED_FOR="203.0.113.10").status_code
        for _ in range(4)
    ]
    assert 429 in codes, codes


# --- login lockout ---------------------------------------------------------

@pytest.mark.django_db
def test_login_locks_out_after_max_failures(settings, seeded):
    from django.contrib.auth import get_user_model

    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_LOGIN_MAX = 3
    settings.RATELIMIT_LOGIN_WINDOW = 900
    get_user_model().objects.create_user(username="admin@pifs.in", password="rightpw123!", is_staff=True)
    c = Client()
    # 3 wrong attempts fill the counter; the 4th is locked (429).
    for _ in range(3):
        r = c.post("/admin-panel/login/", {"username": "admin@pifs.in", "password": "wrong"})
        assert r.status_code == 200  # re-rendered login with error, not locked yet
    locked = c.post("/admin-panel/login/", {"username": "admin@pifs.in", "password": "wrong"})
    assert locked.status_code == 429
    # Even the CORRECT password is refused while locked.
    still = c.post("/admin-panel/login/", {"username": "admin@pifs.in", "password": "rightpw123!"})
    assert still.status_code == 429


@pytest.mark.django_db
def test_login_counter_resets_on_success(settings, seeded):
    from django.contrib.auth import get_user_model

    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_LOGIN_MAX = 5
    get_user_model().objects.create_user(username="admin@pifs.in", password="rightpw123!", is_staff=True)
    c = Client()
    c.post("/admin-panel/login/", {"username": "admin@pifs.in", "password": "wrong"})
    ok = c.post("/admin-panel/login/", {"username": "admin@pifs.in", "password": "rightpw123!"})
    assert ok.status_code in (302, 200)  # logged in (redirect) — counter cleared
    # The per-IP failed-login counter for the test client IP is cleared on success.
    assert cache.get("login-fail:127.0.0.1") in (None, 0)


# --- ClickNonce purge ------------------------------------------------------

@pytest.mark.django_db
def test_click_nonce_purge_removes_expired_only():
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import ClickNonce
    from apps.events.nonces import purge_expired_nonces
    from apps.tenants.resolve import get_bootstrap_tenant

    call_command("seed_program")
    t = get_bootstrap_tenant()
    fresh = ClickNonce.objects.create(tenant=t, nonce="fresh", visitor_id="v1",
                                      expires_at=timezone.now() + timedelta(minutes=30))
    old = ClickNonce.objects.create(tenant=t, nonce="old", visitor_id="v2",
                                    expires_at=timezone.now() - timedelta(hours=3))
    n = purge_expired_nonces()
    assert n == 1
    assert ClickNonce.objects.filter(pk=fresh.pk).exists()
    assert not ClickNonce.objects.filter(pk=old.pk).exists()
