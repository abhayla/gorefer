"""Runtime-resolved integration flags (Admin Settings checkboxes).

Abhay's ask: flip `ENABLE_WATI_SEND` / `ENABLE_ZOHO_WRITE` / `ENABLE_ZOHO_READ` from
the admin Settings screen — no `.env` edit, no redeploy. This makes the P3 "flip" a UI
action instead of a deploy.

**Resolution order (env is the FLOOR, not the ceiling — read this before changing it):**

    ConfigGlobal override (admin checkbox)  ->  env default (gorefer.flags)

No override row => the env default stands. That is what keeps prod state unchanged
when this ships: a fresh checkbox writes nothing, so all three still resolve OFF
exactly as before.

**Why this module exists rather than putting the lookup in `gorefer/flags.py`:**
`flags.py` is deliberately Django-free and frozen at import time (it is imported *by*
settings), so it cannot query the ORM. And `config.cascade.resolve()` itself reads
`flags.ENABLE_CUSTOMER_LOGIN`, so routing flag reads back through the full cascade
would be circular. This module sits in between: it reads the GLOBAL tier directly and
falls back to the frozen env object — no cycle, no Django import at flags-import time.

**Deliberately NOT cached.** A checkbox must take effect on the next request, which is
the entire point of the feature; caching would reintroduce the "redeploy to flip"
problem in a subtler form. The cost is one indexed lookup per adapter selection, on
paths that are about to make a network call anyway.

**Fail-safe:** any error resolving (no DB, no tenant, missing table mid-migration)
falls back to the env default rather than raising. An admin screen must never be able
to take down the redirect path, and "fall back to the deployed default" is the
conservative direction — it cannot silently turn an integration ON.
"""
from __future__ import annotations

import logging

from gorefer.flags import flags

logger = logging.getLogger("gorefer.config.integration_flags")

# Cascade keys (config-over-code: the NAME lives here once, never as a literal).
# Deliberately the same string as the env var so the screen, the DB row, and the env
# default are obviously the same knob when an operator is debugging.
ENABLE_WATI_SEND = "ENABLE_WATI_SEND"
ENABLE_ZOHO_WRITE = "ENABLE_ZOHO_WRITE"
ENABLE_ZOHO_READ = "ENABLE_ZOHO_READ"

# The three exposed on the Settings screen. Only these — `ENABLE_CUSTOMER_LOGIN` /
# `ENABLE_OTP_LOGIN` stay OUT until their features ship (Constitution §4: no dead UI).
INTEGRATION_FLAG_KEYS = (ENABLE_WATI_SEND, ENABLE_ZOHO_WRITE, ENABLE_ZOHO_READ)

# Turning these ON starts real outbound effects, so the screen confirm-gates them.
# ZOHO_READ is absent deliberately: it is read-only and cannot send or write anything.
RISKY_FLAG_KEYS = (ENABLE_WATI_SEND, ENABLE_ZOHO_WRITE)

# UI copy (config-over-code — the template renders these, no inline strings).
INTEGRATION_FLAG_META = {
    ENABLE_WATI_SEND: {
        "label": "Send WhatsApp messages (Wati)",
        "help": "When off, messages are logged but never sent.",
        "confirm": "This starts sending REAL WhatsApp messages to real people. Confirm?",
    },
    ENABLE_ZOHO_WRITE: {
        "label": "Write leads to Zoho",
        "help": "When off, lead writes are logged but never sent. Writes are an "
                "upsert keyed on mobile — an existing lead is updated, never duplicated.",
        "confirm": "This starts writing REAL leads into Zoho CRM. Confirm?",
    },
    ENABLE_ZOHO_READ: {
        "label": "Read account status from Zoho",
        "help": "Read-only enrichment for the Referral Profile. Never writes to Zoho.",
        "confirm": "",  # read-only — no gate
    },
}

SOURCE_OVERRIDE = "override"
SOURCE_ENV = "env"


def env_default(key: str) -> bool:
    """The deployed env/default value for a flag key (the fallback floor)."""
    return bool(getattr(flags, key, False))


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _override_row(key: str, tenant_id: int | None):
    """The GLOBAL-tier override row for `key`, or None.

    Reads ConfigGlobal directly rather than via cascade.resolve() — resolve() consults
    `flags` itself, so going through it would be circular. The GLOBAL tier is also the
    only tier that applies here: these are operator switches, never per-end-user.
    """
    from apps.config.models import ConfigGlobal

    if tenant_id is None:
        return None
    return ConfigGlobal.objects.filter(tenant_id=tenant_id, key=key).first()


def _current_tenant_id(tenant_id: int | None):
    if tenant_id is not None:
        return tenant_id
    from apps.tenants.resolve import get_current_tenant

    tenant = get_current_tenant()
    return getattr(tenant, "id", None)


def resolve_flag(key: str, *, tenant_id: int | None = None) -> bool:
    """The EFFECTIVE value of an integration flag: admin override else env default.

    Every gate site must call this rather than reading `flags.X` directly, or a
    checkbox would appear to work while the code kept obeying the env — the worst
    outcome here, because an operator would believe sending was off when it was on.
    """
    try:
        row = _override_row(key, _current_tenant_id(tenant_id))
    except Exception:
        # DB unavailable / table missing mid-migration / no tenant yet. Fall back to
        # the deployed default: conservative, and it can never turn an integration ON.
        logger.warning("integration flag %s: override lookup failed — using env default", key,
                       exc_info=True)
        return env_default(key)
    if row is None:
        return env_default(key)
    return _as_bool(row.value)


def flag_source(key: str, *, tenant_id: int | None = None) -> str:
    """Where the effective value came from — `override` (admin) or `env` (default)."""
    try:
        row = _override_row(key, _current_tenant_id(tenant_id))
    except Exception:
        return SOURCE_ENV
    return SOURCE_OVERRIDE if row is not None else SOURCE_ENV


def integration_flags_view(tenant_id: int | None = None) -> list[dict]:
    """Render-ready rows for the Settings screen: value + provenance + copy.

    Showing the SOURCE matters: "off" because nobody touched it and "off" because an
    admin turned it off look identical on a checkbox, but they behave differently on
    the next deploy (an env change moves the first, not the second).
    """
    tid = _current_tenant_id(tenant_id)
    rows = []
    for key in INTEGRATION_FLAG_KEYS:
        meta = INTEGRATION_FLAG_META[key]
        source = flag_source(key, tenant_id=tid)
        rows.append({
            "key": key,
            "name": key.lower(),  # the form field name
            "label": meta["label"],
            "help": meta["help"],
            "value": resolve_flag(key, tenant_id=tid),
            "source": source,
            "source_label": (
                "Set here (admin override)" if source == SOURCE_OVERRIDE
                else f"Default from deployment (env: {'on' if env_default(key) else 'off'})"
            ),
            "env_default": env_default(key),
            "requires_confirm": key in RISKY_FLAG_KEYS,
            "confirm": meta["confirm"],
        })
    return rows
