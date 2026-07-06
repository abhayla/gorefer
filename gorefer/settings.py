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
USE_TENANTS = DB_ENGINE == "postgres"

# --- Applications ----------------------------------------------------------
# App split kept "tenant vs shared" aware from day one (ADR-024 line 269), so the
# django-tenants boundary can light up without re-homing apps later.

# Shared/global apps: identity of tenants themselves, Django admin, config baseline.
SHARED_APPS = [
    "django_tenants",  # must be first when tenants are active
    "apps.tenants",    # holds the Tenant + Domain models (TENANT_MODEL)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.config",     # config cascade central layer is shared
]

# Tenant-scoped apps: the referral domain data partitions per tenant.
TENANT_APPS = [
    "django.contrib.contenttypes",
    "apps.referrals",
    "apps.events",
    "apps.integrations",
]

# TENANT_MODEL / TENANT_DOMAIN_MODEL are defined unconditionally: django-tenants'
# DomainMixin references settings.TENANT_MODEL at import time. They are inert
# without the schema router (which is only wired when USE_TENANTS).
TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"

if USE_TENANTS:
    INSTALLED_APPS = SHARED_APPS + [a for a in TENANT_APPS if a not in SHARED_APPS]
else:
    # SQLite/dev boot: same apps, no django-tenants app or router.
    INSTALLED_APPS = [a for a in SHARED_APPS if a != "django_tenants"] + [
        a for a in TENANT_APPS if a not in SHARED_APPS
    ]

MIDDLEWARE = (
    (["django_tenants.middleware.main.TenantMainMiddleware"] if USE_TENANTS else [])
    + [
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
)

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
if USE_TENANTS:
    DATABASES = {
        "default": {
            "ENGINE": "django_tenants.postgresql_backend",
            "NAME": os.environ.get("DB_NAME", "gorefer"),
            "USER": os.environ.get("DB_USER", "gorefer"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
    DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)
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
