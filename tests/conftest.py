"""Pytest bootstrap.

Postgres is the app default (ADR-021), but the test suite defaults to SQLite so CI
is green with no external DB and quick local runs need no Postgres. To run the
authoritative suite on Postgres (matches production), set it explicitly:
    DB_ENGINE=postgres python -m pytest
(`setdefault` below only applies SQLite when DB_ENGINE isn't already in the env.)
"""
import logging
import os

os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gorefer.settings")

# Quiet django-q's per-task cluster chatter during the test run.
logging.getLogger("django-q").setLevel(logging.ERROR)
