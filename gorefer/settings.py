"""Django settings for GoRefer (Sprint 1 — Foundation / M1 skeleton).

Stack (LOCKED, ADR-024): Django + Django Ninja + HTMX + Tailwind + PostgreSQL.

Database engine (M10): **PostgreSQL is the ONLY supported engine** across
dev/test/CI/prod. GoRefer relies on Postgres-specific behaviour (JSONB, partial-
unique constraints, case-sensitivity), so there is no SQLite branch or fallback —
a green run on any other engine would be false confidence. The `DATABASES` config
below resolves to Postgres unconditionally and a fail-fast guard raises
`ImproperlyConfigured` if the resolved ENGINE is anything but
`django.db.backends.postgresql`.

Multi-tenancy (see COORDINATION Q-M1-1) is SINGLE-SCHEMA `tenant_id` discriminator
isolation (NOT django-tenants schema-per-tenant): `apps.tenants` keeps a plain
Tenant/Domain registry and isolation is enforced by tenant-scoped model managers +
TenantResolutionMiddleware + composite unique constraints (per 05-Database-Design).
Schema-per-tenant physical isolation is deferred to backlog DF-7.
"""
from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from gorefer.flags import flags

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from repo root if present (no-op if absent / in CI with real env vars).
load_dotenv(BASE_DIR / ".env")

# --- Core security / debug -------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# --- Reverse-proxy / TLS hardening (prod behind nginx + Cloudflare) --------
# All env-driven; defaults preserve dev/CI behaviour (no HTTPS assumptions). In
# production (DEPLOY-TARGET Hostinger: nginx terminates TLS via certbot, sets
# X-Forwarded-Proto), set these so Django knows the request is HTTPS, trusts the
# origin for CSRF (admin login POST), and forces secure cookies.
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]
if os.environ.get("DJANGO_BEHIND_TLS_PROXY", "false").strip().lower() in {"1", "true", "yes", "on"}:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get(
        "DJANGO_SECURE_SSL_REDIRECT", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

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
    "apps.otp",  # pluggable OTP delivery port (Q-M-OTP; behind ENABLE_OTP_LOGIN)
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

# --- Database (PostgreSQL ONLY — M10) --------------------------------------
# Single-schema isolation (Q-M1-1): plain Postgres backend, NO django-tenants
# router. There is NO SQLite/other-engine branch — Postgres is the sole supported
# engine across dev/test/CI/prod (GoRefer relies on JSONB / partial-unique
# constraints / case-sensitivity). The `test` DB name below is what the pytest
# runner creates + tears down (default `gorefer_test`, override via TEST_DB_NAME).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "gorefer"),
        "USER": os.environ.get("DB_USER", "gorefer"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "TEST": {"NAME": os.environ.get("TEST_DB_NAME", "gorefer_test")},
    }
}

# Fail-fast guard (M10): refuse to boot on anything but PostgreSQL, so a non-Postgres
# engine can never silently pass tests or run in prod.
_resolved_engine = DATABASES["default"]["ENGINE"]
if _resolved_engine != "django.db.backends.postgresql":
    raise ImproperlyConfigured(
        "GoRefer supports PostgreSQL only (M10). Resolved DB ENGINE "
        f"'{_resolved_engine}' is not 'django.db.backends.postgresql'. "
        "Set the DB_* env vars to a Postgres database — there is no SQLite fallback."
    )

# --- Auth ------------------------------------------------------------------
LOGIN_URL = "dashboard_login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "dashboard_login"

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
# Human-facing support helpline (config, not a secret) — the "free, fully-assisted
# account opening — call" line on the landing page (Ashok). Display format (with +91).
SUPPORT_HELPLINE_PHONE = os.environ.get("SUPPORT_HELPLINE_PHONE", "+91 73888 82020")

# --- Compliance strings — canonical, byte-exact, single source (ADR-014) ---------
# Rendered verbatim on every customer-facing page via the shared compliance partial.
# NOTE the exact wording: NO "the" before "securities market"; a COMMA (not ";")
# before "read"; the disclosure block is the full SEBI/PIFS/NSE-AP line.
AP_DISCLOSURE_BLOCK = (
    "Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | "
    "Passive Income Financial Solutions Private Limited | "
    f"NSE AP reg. no.: {NSE_AP_NO}"
)
MARKET_RISK_WARNING = (
    "Investments in securities market are subject to market risks, "
    "read all the related documents carefully before investing."
)

# --- Open Graph / Twitter-Card preview (M11 / ADR-028) ---------------------
# Per-partner, config-driven card content for a forwarded /r/{client_id} link so
# WhatsApp/FB/LinkedIn/X render a compliant preview. Config-over-code: env overrides;
# a per-tenant override can be added to the ADR-022 cascade later (keys mirror these).
# GUARDRAIL: no partner code, no raw Zerodha URL, must NOT resemble/clone Zerodha.
OG_TITLE = os.environ.get("OG_TITLE", "Open a free Zerodha demat & trading account")
OG_DESCRIPTION = os.environ.get(
    "OG_DESCRIPTION",
    "You've been personally referred. PIFS helps you open your Zerodha account "
    "smoothly with trusted guidance. Investments in securities market are subject to "
    "market risks.",
)
# Card image: a PIFS-branded asset served from our own static (NOT a Zerodha asset).
# Default is a relative static path; env can point at an absolute https URL.
OG_IMAGE = os.environ.get("OG_IMAGE", "img/og-card.png")
OG_SITE_NAME = os.environ.get("OG_SITE_NAME", "GoRefer · PIFS")
# Public base used to build absolute og:url / og:image (Open Graph needs absolute URLs).
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://gorefer.in")

# --- PII masking policy (M9) -----------------------------------------------
# The admin view shows FULL IP + phone. This config drives masking for the FUTURE
# customer/referrer view (IP -> city-only, phone -> partial). Built now, dormant: it
# only takes effect once ENABLE_CUSTOMER_LOGIN turns on (no dead UI in Sprint 1).
PII_MASK_FOR_CUSTOMER_VIEW = os.environ.get(
    "PII_MASK_FOR_CUSTOMER_VIEW", "true"
).strip().lower() in {"1", "true", "yes", "on"}

# --- Zoho webhook auth (M6, interim R2): static key + IP allowlist ---------
# HMAC wax-seal is deferred (DF-2). The key is a SECRET (from env, never inline).
ZOHO_WEBHOOK_KEY = os.environ.get("ZOHO_WEBHOOK_KEY", "")
ZOHO_WEBHOOK_IP_ALLOWLIST = os.environ.get("ZOHO_WEBHOOK_IP_ALLOWLIST", "")  # csv; empty = any (dev)
# DF-2 wax-seal (used only when ENABLE_ZOHO_WEBHOOK_HMAC=true). The shared secret the
# Zoho-side Deluge signer holds. Unset => the seal REJECTS everything (fail-closed).
ZOHO_WEBHOOK_HMAC_SECRET = os.environ.get("ZOHO_WEBHOOK_HMAC_SECRET", "")
# Freshness window for a sealed request, in seconds (absorbs clock skew).
ZOHO_WEBHOOK_MAX_SKEW_SECONDS = int(os.environ.get("ZOHO_WEBHOOK_MAX_SKEW_SECONDS", "300"))

# --- WATI webhook auth (B4, interim R2): static key + IP allowlist ----------
# The Wati assisted-referral flow posts here. Same interim model as Zoho (static
# key + IP allowlist; HMAC wax-seal deferred DF-2). Key is a SECRET (env only).
WATI_WEBHOOK_KEY = os.environ.get("WATI_WEBHOOK_KEY", "")
WATI_WEBHOOK_IP_ALLOWLIST = os.environ.get("WATI_WEBHOOK_IP_ALLOWLIST", "")  # csv; empty = any (dev)

# --- OTP login (Q-M-OTP, behind ENABLE_OTP_LOGIN) --------------------------
# The pluggable OTP delivery port. The per-tenant behavioural knobs (primary
# channel, fallback order, template, TTL, limits) live in the ADR-022 config
# cascade and are edited on the Preferences screen (apps/config/preferences.py) —
# NOT here. This block holds only the process-level SECRET used to hash codes.
# OTP codes are stored HASHED (never plaintext); the pepper strengthens the hash
# so a DB leak alone can't brute-force 6-digit codes. SECRET — env only, never
# inline; falls back to SECRET_KEY in dev so the flow works offline.
OTP_HASH_PEPPER = os.environ.get("OTP_HASH_PEPPER", "") or SECRET_KEY
# Central default for the AUTHENTICATION template name (per-tenant override on the
# Preferences screen wins). Config, not a secret.
OTP_WHATSAPP_TEMPLATE = os.environ.get("OTP_WHATSAPP_TEMPLATE", "gorefer_login_otp")
