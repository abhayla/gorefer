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

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gorefer.settings")

# Quiet django-q's per-task cluster chatter during the test run.
logging.getLogger("django-q").setLevel(logging.ERROR)
