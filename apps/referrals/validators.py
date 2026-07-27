"""client_id format validation (ADR-008 / Gap 3, spec 06-API §4.1).

Format-validate ONLY — reject empty / wrong-length / illegal chars. There is NO
ownership verification: no Zerodha API exists to check a client_id against, so a
well-formed id is accepted and the referrer is created lazily on first click.

TWO RULES, DELIBERATELY (owner decision 2026-07-27)
---------------------------------------------------
The spec bound (06-API §4.1) is 4–16 alphanumerics. That is loose enough that a
malformed chatbot link created REAL referrers called `TALK` and `ZMPHZC` — the latter
being PIFS's own PARTNER CODE, which is not a client id at all. Junk identities are only
ever created by the public LINK paths, so those now validate against a stricter,
per-partner pattern:

  - `validate_client_id(raw)`             — the loose spec rule. LOOKUP paths keep this
    (admin search, login) so staff can still find a legacy or junk id that already
    exists; rejecting there would hide history rather than prevent it.
  - `validate_client_id_for(tenant, raw)` — the strict, PER-PARTNER rule. Used by the
    paths that CREATE an identity (`/r/`, `/share/`, the Wati webhook), so a leaked menu
    label can never become a referrer again.

PATTERN IS CONFIGURATION, PER PARTNER (CLAUDE.md §6d + "configuration over code")
--------------------------------------------------------------------------------
Different partners issue different id shapes, so the pattern comes from the config
cascade, most specific first:

    client_id_pattern__<PARTNER_CODE>   e.g. client_id_pattern__ZMPHZC   (per partner)
    client_id_pattern                   (tenant / central default)
    <the loose spec rule>               (fallback)

Nothing here is named after a partner: the key is composed from the partner's own `code`
field, so onboarding a partner with different id rules is data, not code.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("gorefer.referrals.validators")

# Reconciled to the single spec bound (06-API §4.1): 4–16 alphanumeric chars.
MIN_CLIENT_ID_LEN = 4
MAX_CLIENT_ID_LEN = 16
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9]{4,16}$")

PATTERN_KEY = "client_id_pattern"
#: Zerodha ids are EXACTLY 6 characters, starting with a LETTER; the remaining five may
#: be letters or digits (RJ4521, DA1707, EKU497, and all-letter ids too). Owner-specified
#: 2026-07-27. Seeded as `client_id_pattern__<PARTNER_CODE>`; this constant only documents
#: the shape — the live value is configuration.
#:
#: KNOWN AND ACCEPTED: this admits a 6-letter string, so PIFS's own partner code `ZMPHZC`
#: would pass. That is a deliberate consequence of "all can be letters" — the rule cannot
#: both allow all-letter ids and reject one particular all-letter string. `TALK` (4 chars)
#: is still refused, and the chatbot flow that leaked those labels has been fixed.
ZERODHA_CLIENT_ID_PATTERN = r"^[A-Z][A-Z0-9]{5}$"


class InvalidClientId(ValueError):
    """Raised when a client_id fails format validation."""


def validate_client_id(raw: str | None, *, pattern: str | None = None) -> str:
    """Return the normalized client_id (uppercased) or raise InvalidClientId.

    Base rules (06-API §4.1): 4–16 chars, alphanumeric only. Normalizes to uppercase so
    the identity key is case-stable (r/rj4521 and r/RJ4521 resolve to one referrer).

    `pattern` adds a partner-specific constraint ON TOP — it can only narrow, never
    widen, so a misconfigured pattern cannot admit something the spec rule rejects.
    """
    if raw is None:
        raise InvalidClientId("client_id is required")
    candidate = raw.strip()
    if not candidate:
        raise InvalidClientId("client_id is empty")
    if not (MIN_CLIENT_ID_LEN <= len(candidate) <= MAX_CLIENT_ID_LEN):
        raise InvalidClientId("client_id must be 4–16 characters")
    if not _CLIENT_ID_RE.match(candidate):
        raise InvalidClientId("client_id contains illegal characters")
    normalized = candidate.upper()
    if pattern:
        try:
            compiled = re.compile(pattern)
        except re.error:
            # A broken pattern must NOT block real referrals — degrade to the spec rule
            # and shout, rather than 400-ing every link for that partner.
            logger.error("invalid client_id_pattern %r — falling back to the spec rule", pattern)
            return normalized
        if not compiled.match(normalized):
            raise InvalidClientId("client_id does not match the partner's id format")
    return normalized


def resolve_client_id_pattern(tenant_id: int | None, partner_code: str | None = None) -> str:
    """The partner's id pattern from the cascade, or "" when none is configured."""
    from apps.config.cascade import resolve

    keys = ([f"{PATTERN_KEY}__{partner_code}"] if partner_code else []) + [PATTERN_KEY]
    for key in keys:
        try:
            value = resolve(key, tenant_id=tenant_id, default="")
        except Exception:
            value = ""
        if value:
            return str(value).strip()
    return ""


def validate_client_id_for(tenant, raw: str | None) -> str:
    """Validate against the ACTIVE partner's pattern — for identity-CREATING paths.

    Resolving the partner is best-effort: with no program configured we fall back to the
    spec rule rather than refusing every link, because a config gap must never take the
    redirect path down.
    """
    tenant_id = getattr(tenant, "id", None)
    partner_code = None
    try:
        from apps.referrals.redirect_service import get_active_program

        program = get_active_program(tenant)
        partner_code = getattr(getattr(program, "partner", None), "code", None)
    except Exception:
        partner_code = None
    return validate_client_id(raw, pattern=resolve_client_id_pattern(tenant_id, partner_code))
