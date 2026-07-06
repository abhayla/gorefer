"""Pytest bootstrap: force SQLite (no external DB) so CI is green with no Postgres.

Real deploys use DB_ENGINE=postgres + django-tenants; the M1 test suite runs on
SQLite to stay dependency-free (see COORDINATION Q-M1-1).
"""
import os

os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gorefer.settings")
