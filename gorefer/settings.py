"""Django settings for GoRefer (Sprint 1 — Foundation / M1 skeleton).

Stack (LOCKED, ADR-024): Django + Django Ninja + HTMX + Tailwind + PostgreSQL,
with django-tenants for the ADR-023 multi-tenant boundary.

Multi-tenancy note (see COORDINATION QUESTION Q-M1-1): django-tenants is
PostgreSQL-only (schema-per-tenant). To keep the M1 skeleton bootable and CI green
with **no external database**, tenant routing is enabled ONLY when the configured
DB engine is PostgreSQL (`DB_ENGINE=postgres`, the deploy default). On SQLite
(dev/CI convenience) the same apps load WITHOUT the django-tenants schema router,
and the `tenant_id` discriminator columns (per 05-Database-Design §2) still exist.
This lets M1 boot everywhere while the ADR-023 boundary is scaffolded now.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from gorefer.flags import flags

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from repo root if present (no-op if absent / in CI with real env vars).
load_dotenv(BASE_DIR / ".env")

# --- Core security / debug -------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# --- Database engine selection ---------------------------------------------
# DB_ENGINE=postgres  -> real deploy: PostgreSQL + django-tenants schema routing.
# DB_ENGINE=sqlite    -> dev/CI convenience: single SQLite file, no tenant router.
DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").strip().lower()

# --- Applications ----------------------------------------------------------
# Multi-tenancy is SINGLE-SCHEMA tenant_id discriminator (COORDINATION Q-M1-1
# answer): no django-tenants schema routing. `apps.tenants` keeps a plain
# Tenant/Domain registry; isolation is enforced by tenant-scoped model managers +
# TenantResolutionMiddleware + composite unique constraints (per 05-Database-Design).
# Schema-per-tenant physical isolation is deferred to backlog DF-7.
INSTALLED_APPS = [
    "apps.tenants",  # plain Tenant + Domain registry (no schema router)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_q",  # background queue (ORM broker — NO Redis; ADR-024)
    "apps.config",
    "apps.referrals",
    "apps.events",
    "apps.integrations",
]

# --- Background queue (django-q2, Postgres/ORM broker — NO Redis) -----------
# Async WATI sends + retries + terminal-status polling, and the M4 dirty-day
# recompute schedule run here. `sync` runs tasks inline (no worker) — the default
# in dev/CI/demo so the whole flow is testable offline; set Q_ASYNC=true + run
# `python manage.py qcluster` in production for real async.
Q_CLUSTER = {
    "name": "gorefer",
    "orm": "default",  # use the default DB as the broker (no Redis)
    "sync": os.environ.get("Q_ASYNC", "false").strip().lower() not in {"1", "true", "yes", "on"},
    "timeout": 60,
    "retry": 120,
    "max_attempts": 5,
    "catch_up": False,
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Resolves the active tenant (Sprint 1: the single bootstrap tenant PIFS) and
    # stashes it on the request for tenant-scoped writes.
    "apps.tenants.middleware.TenantResolutionMiddleware",
]

ROOT_URLCONF = "gorefer.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "gorefer.context_processors.compliance",
            ],
        },
    },
]

WSGI_APPLICATION = "gorefer.wsgi.application"

# --- Database --------------------------------------------------------------
# Single-schema isolation (Q-M1-1): plain Postgres backend, NO django-tenants
# backend/router. SQLite is the zero-dependency dev/CI path.
if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "gorefer"),
            "USER": os.environ.get("DB_USER", "gorefer"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "gorefer_dev.sqlite3")),
        }
    }

# --- Auth ------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N / TZ -------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static ----------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Feature flags (single source; see gorefer/flags.py) -------------------
# Exposed on settings for convenience, but `from gorefer.flags import flags` is
# the canonical read path.
FEATURE_FLAGS = flags.as_dict()

# --- Env-bootstrap admin (implementation/10 §5) ----------------------------
# Consumed by the `bootstrap_admin` management command. No plaintext default.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

# --- Program bootstrap constants (seeded, not hardcoded in logic) ----------
# Provider-agnostic: these live in config/seed, never in Zerodha-named code.
PARTNER_CODE = os.environ.get("PARTNER_CODE", "ZMPHZC")
NSE_AP_NO = os.environ.get("NSE_AP_NO", "AP2516003693")
# WATI BUSINESS number (config, not a secret) — the wa.me share target. Digits only
# (no +/spaces) so it drops straight into a wa.me link. NOT Ashok's personal number.
WATI_BUSINESS_NUMBER = os.environ.get("WATI_BUSINESS_NUMBER", "917080642020")
# Office/Ashok alert recipient for the "new lead" notification (config, not secret).
OFFICE_ALERT_NUMBER = os.environ.get("OFFICE_ALERT_NUMBER", "917388882020")

# --- Zoho webhook auth (M6, interim R2): static key + IP allowlist ---------
# HMAC wax-seal is deferred (DF-2). The key is a SECRET (from env, never inline).
ZOHO_WEBHOOK_KEY = os.environ.get("ZOHO_WEBHOOK_KEY", "")
ZOHO_WEBHOOK_IP_ALLOWLIST = os.environ.get("ZOHO_WEBHOOK_IP_ALLOWLIST", "")  # csv; empty = any (dev)
