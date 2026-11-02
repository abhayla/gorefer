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


# --- ReDoS guard on the admin-editable pattern (T-048) ------------------------
#
# `client_id_pattern` is CONFIGURATION an operator edits, and it is then run against
# attacker-supplied input on the public `/r/{client_id}` path. Python's `re` has no
# timeout, so a pattern with a nested quantifier — `(a+)+$`, `(a|a)*$`, `((ab)*)+$` —
# backtracks exponentially and hangs the worker thread for that request. Nobody has to
# be malicious for this to bite: a well-meant "make the pattern stricter" edit is enough.
#
# We screen STATICALLY and refuse to use an unsafe pattern, rather than trying to bound
# it at match time (there is no portable way to interrupt `re`). The refusal reuses the
# EXISTING safe-degrade path — fall back to the loose spec rule and log loudly — so a bad
# config never 400s real referral links.
MAX_PATTERN_LENGTH = 200


def is_safe_pattern(pattern: str) -> bool:
    """False when `pattern` contains a quantified group that itself is quantified.

    Two shapes make backtracking exponential, and both are a quantifier applied to a
    group whose body is itself ambiguous:
      - a nested quantifier — `(a+)+`, `((ab)*)+`
      - a quantified alternation — `(a|a)*`, `(a|ab)+`
    A plain `[A-Z][A-Z0-9]{5}` or `[a-z]+` has neither and matches in linear time. An
    UNQUANTIFIED alternation like `^(RJ|DA)[0-9]{4}$` is fine and stays allowed — it is
    the outer repetition that multiplies the alternatives.

    The scan is a single left-to-right pass tracking each open group's body, honouring
    escapes and character classes so `\\(` and `[+*|]` are not mistaken for structure.
    """
    if len(pattern or "") > MAX_PATTERN_LENGTH:
        return False
    if not pattern:
        return True
    stack: list[bool] = []          # per open group: is its body ambiguous?
    in_class = False
    escaped = False
    for i, ch in enumerate(pattern):
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "(":
            stack.append(False)
        elif ch == ")":
            body_ambiguous = stack.pop() if stack else False
            # Is THIS group quantified? Look at what immediately follows the ')'.
            nxt = pattern[i + 1] if i + 1 < len(pattern) else ""
            group_quantified = nxt in "*+{"
            if group_quantified and body_ambiguous:
                return False
            # A quantified group is itself ambiguous inside its parent.
            if stack and (group_quantified or body_ambiguous):
                stack[-1] = True
        elif ch in "*+{|":
            if stack:
                stack[-1] = True
    return True


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
        # ReDoS screen BEFORE compiling/matching: an unsafe pattern is never run against
        # the (attacker-supplied) candidate. Same safe-degrade as a syntactically broken
        # pattern — fall back to the spec rule and shout, never hang or 400 the link.
        if not is_safe_pattern(pattern):
            logger.error(
                "unsafe client_id_pattern %r (catastrophic-backtracking risk) — "
                "falling back to the spec rule", pattern,
            )
            return normalized
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


# --- Placeholder ids (owner decision 2026-11-02) --------------------------------------
# A link that carries an example instead of a real id (`/r/wa/KITEID`) must never create a
# referrer. `KITEID` has exactly the shape of a real Zerodha id, so the pattern alone can't
# catch it: the obvious placeholder WORDS are a cascade key (rail E-6 / §6d), editable on
# the Preferences screen (key + default live in apps.config.preferences with the other
# screen keys). Only obvious words belong there — when in doubt, let it through (owner:
# "if you're not sure, let the user proceed").


def placeholder_words(tenant_id: int | None) -> set[str]:
    """The configured placeholder words, normalized. Accepts a JSON list or a
    comma-separated string (the Preferences text field), so either storage shape works."""
    from apps.config.cascade import resolve
    from apps.config.preferences import CLIENT_ID_PLACEHOLDER_WORDS, CLIENT_ID_PLACEHOLDER_WORDS_DEFAULT

    try:
        value = resolve(
            CLIENT_ID_PLACEHOLDER_WORDS, tenant_id=tenant_id, default=CLIENT_ID_PLACEHOLDER_WORDS_DEFAULT
        )
    except Exception:
        value = CLIENT_ID_PLACEHOLDER_WORDS_DEFAULT
    if isinstance(value, str):
        value = value.split(",")
    return {"".join(ch for ch in str(word) if ch.isalnum()).upper() for word in (value or [])} - {""}


def is_placeholder_id(tenant_id: int | None, normalized: str) -> bool:
    return (normalized or "").upper() in placeholder_words(tenant_id)


def validate_client_id_for(tenant, raw: str | None) -> str:
    """Validate against the ACTIVE partner's pattern — for identity-CREATING paths.

    Resolving the partner is best-effort: with no program configured we fall back to the
    spec rule rather than refusing every link, because a config gap must never take the
    redirect path down. A well-shaped placeholder (`KITEID`) is refused too, so it can
    never become a referrer.
    """
    tenant_id = getattr(tenant, "id", None)
    partner_code = active_partner_code(tenant)
    normalized = validate_client_id(raw, pattern=resolve_client_id_pattern(tenant_id, partner_code))
    if is_placeholder_id(tenant_id, normalized):
        raise InvalidClientId("client_id is a placeholder, not a real id")
    return normalized


# --- Soft-deleted referrers (owner decision 2026-11-02) ---------------------------------
# An operator soft-deletes a junk referrer (KITEID, ZZ9999, test ids). Before this, a later
# click on that id still resolved the DELETED identity and logged events against its
# deleted Referral, so junk kept collecting clicks. Public LINK paths now treat a deleted
# id like a placeholder: the Kite ID pop-up, nothing recorded. Deliberately NOT inside
# validate_client_id_for, which the records page and the Wati assisted-lead webhook also
# use; their behaviour for a deleted id is unchanged.


class DeletedClientId(InvalidClientId):
    """The id belongs to a soft-deleted referrer identity."""


def is_deleted_referrer(tenant, normalized: str) -> bool:
    from apps.referrals.models import ReferralIdentity

    return (
        ReferralIdentity.objects.for_tenant(tenant)
        .filter(client_id=normalized, id_source="native", deleted_at__isnull=False)
        .exists()
    )


def validate_link_client_id(tenant, raw: str | None) -> str:
    """validate_client_id_for + refuse a soft-deleted referrer — for the public link views."""
    normalized = validate_client_id_for(tenant, raw)
    if is_deleted_referrer(tenant, normalized):
        raise DeletedClientId("client_id belongs to a deleted referrer")
    return normalized


def active_partner_code(tenant) -> str | None:
    """The active program's partner code, or None — best-effort, never raises."""
    try:
        from apps.referrals.redirect_service import get_active_program

        program = get_active_program(tenant)
        return getattr(getattr(program, "partner", None), "code", None)
    except Exception:
        return None


# --- Id length for the Kite ID input box (owner decision 2026-11-02) --------------------
# The pop-up box stops accepting characters at the partner's id length, like an OTP box
# (owner: "it only allows 6 digits of the OTP ... Can we do something similar?"). The
# length is per-partner CONFIGURATION (rail E-6), seeded as `client_id_length__<CODE>`.
# It caps only what the BOX accepts; the server never truncates an id to this length —
# a long id is rejected by the pattern, because cutting `AD1111XXXX` to `AD1111` could
# silently credit the wrong referrer.
LENGTH_KEY = "client_id_length"
ZERODHA_CLIENT_ID_LENGTH = 6


def resolve_client_id_length(tenant_id: int | None, partner_code: str | None = None) -> int:
    """The partner's id length for the input box. Falls back to the spec maximum (16) when
    unset or invalid, and is clamped to the spec bound 4-16, so a bad config value can
    never make the box refuse a valid id or accept more than the spec allows."""
    from apps.config.cascade import resolve

    keys = ([f"{LENGTH_KEY}__{partner_code}"] if partner_code else []) + [LENGTH_KEY]
    for key in keys:
        try:
            value = int(resolve(key, tenant_id=tenant_id, default=0) or 0)
        except Exception:
            value = 0
        if value > 0:
            return max(MIN_CLIENT_ID_LEN, min(MAX_CLIENT_ID_LEN, value))
    return MAX_CLIENT_ID_LEN
