"""Pytest bootstrap.

PostgreSQL is the ONLY supported engine (M10) — there is no SQLite path. The test
suite runs against the Postgres `gorefer_test` database (settings `DATABASES.default.
TEST.NAME`, override via `TEST_DB_NAME`), which the runner creates + tears down. The
DB_* connection vars come from the environment / `.env` (a Postgres role with CREATEDB
so the runner can create the test DB). No engine override here — settings' fail-fast
guard rejects anything but PostgreSQL.
"""
import logging
import os

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gorefer.settings")

# Quiet django-q's per-task cluster chatter during the test run.
logging.getLogger("django-q").setLevel(logging.ERROR)


@pytest.fixture(autouse=True)
def _clear_ratelimit_cache(request):
    """Reset the DB-cache-backed rate limiter between every test.

    CI runs with DJANGO_DEBUG=false, so RATELIMIT_ENABLED defaults to True
    (prod-like) for the whole suite (see apps/common/ratelimit.py). Without
    a reset, per-IP hit counters for scopes like "leads"/"share" accumulate
    across unrelated test modules that all post through the Django test
    Client's default REMOTE_ADDR (127.0.0.1) — eventually tripping a 429
    on a test that has nothing to do with rate limiting. Clearing the cache
    around each DB-touching test keeps counters test-local without changing
    any rate-limit behavior itself.
    """
    needs_db = (
        request.node.get_closest_marker("django_db") is not None
        or "db" in request.fixturenames
        or "transactional_db" in request.fixturenames
    )
    if not needs_db:
        yield
        return

    # Tests reach db access either via an explicit "db"/"transactional_db"/
    # "seeded(db)" fixture argument (present in request.fixturenames) or via
    # the bare `@pytest.mark.django_db(...)` marker (which grants access
    # internally without adding anything to request.fixturenames). Either
    # way, `django_db_blocker` — pytest-django's public API for touching the
    # database from outside a test's own db fixture — works regardless of
    # which path this test used and isn't sensitive to fixture setup order.
    django_db_blocker = request.getfixturevalue("django_db_blocker")
    from django.core.cache import cache

    with django_db_blocker.unblock():
        cache.clear()
    yield
    with django_db_blocker.unblock():
        cache.clear()
