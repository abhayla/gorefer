"""T-162 (owner-approved point 23): a missing DB cache table must NOT 500 the site.

The rate limiter is backed by the `gorefer_cache` table, which is created by
`manage.py createcachetable` — a step the deploy runner did not run and
DEPLOY-TARGET.md's P5 checklist did not list. On a fresh box, or after restoring the
database from a dump (the table is data, not schema — it is NOT created by a
migration), the table is simply absent. Every cache call then raises
ProgrammingError, and the public lead form plus the admin login page answered 500:
the anti-spam counter took the page down with it.

These tests drop the table for real (not a mock) and assert the pages still work,
unthrottled, with one loud log line naming the fix.
"""
import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings

from apps.common import ratelimit


def _drop_cache_table():
    with connection.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS gorefer_cache")


def _restore_cache_table():
    call_command("createcachetable")


@pytest.fixture
def no_cache_table():
    """Run the test with `gorefer_cache` genuinely absent, then put it back."""
    ratelimit._backend_failure_logged = False
    _drop_cache_table()
    try:
        yield
    finally:
        _restore_cache_table()
        ratelimit._backend_failure_logged = False


@pytest.mark.django_db(transaction=True)
@override_settings(RATELIMIT_ENABLED=True)
def test_hit_allows_and_logs_once_when_the_cache_table_is_missing(no_cache_table, caplog):
    caplog.set_level("ERROR", logger="gorefer.ratelimit")

    # A limit of 1 would normally block the second call; with no backend there is no
    # counter, so every call is allowed — degrade OPEN, never 500.
    for _ in range(5):
        allowed, retry_after = ratelimit.hit("leads", "1.2.3.4", limit=1, window=60)
        assert allowed is True
        assert retry_after == 0

    # check_rate must not raise either — RateLimited is a real 429, not a backend error.
    ratelimit.check_rate("leads", "1.2.3.4", limit=1, window=60)

    errors = [r for r in caplog.records if r.name == "gorefer.ratelimit"]
    assert len(errors) == 1, "expected exactly ONE loud line per process, not one per hit"
    assert "RATE LIMITER DISABLED" in errors[0].getMessage()
    assert "createcachetable" in errors[0].getMessage(), "the log line must name the fix"


@pytest.mark.django_db(transaction=True)
@override_settings(RATELIMIT_ENABLED=True)
def test_counter_helpers_degrade_instead_of_raising(no_cache_table):
    key = "login-fail:1.2.3.4"
    ratelimit.bump_counter(key, window=60)      # no-op, must not raise
    assert ratelimit.counter_value(key) == 0    # reads as "not locked"
    ratelimit.clear_counter(key)                # no-op, must not raise


@pytest.mark.django_db(transaction=True)
@override_settings(RATELIMIT_ENABLED=True)
def test_admin_login_page_still_answers_without_the_cache_table(no_cache_table, client):
    """The exact page that used to 500: POST /admin-panel/login/ with bad credentials.

    It reads the lock counter before authenticating and bumps it afterwards — two
    cache calls, both of which raised on a missing table.
    """
    get_response = client.get("/admin-panel/login/")
    assert get_response.status_code == 200

    post_response = client.post(
        "/admin-panel/login/", {"username": "nobody@example.com", "password": "wrong"}
    )
    # 200 = the login form re-rendered with an error (the normal wrong-password path).
    # Before the fix this was a 500 from ProgrammingError inside the lock check.
    assert post_response.status_code == 200
