"""Fail-closed SERVER-COMPUTED template-variable guard (T-073).

The failure this exists to prevent, stated plainly: a WhatsApp template can be
created, approved and sent while one of its variables is something **only GoRefer
can compute** — today `{{token}}`. Nothing at Meta, at Wati, or in a dashboard
broadcast knows that. A Wati broadcast fills an unknown variable from a contact
attribute that does not exist, the value comes out BLANK, and every recipient gets
a dead link with a green "delivered" tick. The send looks perfect from every angle
except the recipient's.

The PARAM NAME `token` is now a historical label, not a promise of shape: the
records-link family (`refrecord`) fills it with the raw client_id behind
`/rr/{client_id}` (T-129 — Meta silently blanks a URL-button value containing ':',
and a signed `django.core.signing` value always contains one); the invite/hub
family (`referandearn_invite`) still fills it with the signed value behind
`/hub/{token}`. Either way the contract this module enforces is unchanged: the
named param must be present and non-blank before a send is allowed.

So the rule here is the inverse of the usual one: **a template whose computed
variables the sender cannot fill must not be sent at all.** Not sent with a blank.
Not sent with a placeholder. Refused, with a reason a human can read.

Two pieces:

  * a REGISTRY — an explicit, in-code declaration of which templates carry which
    server-computed variables. Registration is by exact `elementName` (the names
    the cascade resolves today) AND by family substring, because a re-cut
    (`…_v2`, `…_hi_…`) is the same template with the same computed variable and
    would otherwise silently fall out of the registry on rename;
  * `assert_computed_vars_filled()` — the ONE check. Every send path runs it; the
    port factory wraps every messaging adapter with it so a caller that forgets
    cannot bypass it.

`missing_reason()` renders the stable machine reason string
(`missing_computed_var:token`) that senders record and tests assert on.

Deliberately NOT here: any knowledge of how a token is minted. This module only
knows a template needs one and whether the sender supplied it. Minting stays in
`apps.accounts.records_link` / `api.records_tokens` — one code path (T-054/T-057).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

#: The one server-computed variable that exists today: the signed records/hub token.
PARAM_TOKEN = "token"

#: Stable machine-readable reason prefix. Senders record `f"{REASON_PREFIX}{param}"`.
REASON_PREFIX = "missing_computed_var:"

#: EXACT `elementName` -> the params GoRefer itself must mint for that template.
#: Seeded with the default names of the cascade keys that carry a token today; a
#: tenant that overrides the name to a same-family re-cut is still covered by
#: `_FAMILY_PATTERNS` below.
_EXACT: dict[str, frozenset[str]] = {
    # Records magic link (T-057) — {{token}} behind the [Referral Records] button.
    "gr_platform_gorefer_refrecord_en_2026_08_07": frozenset({PARAM_TOKEN}),
    # Referral invite (T-073) — {{token}} behind the share-hub URL button.
    "gr_brokers_zerodha_referandearn_invite_en_2026_08_10": frozenset({PARAM_TOKEN}),
}

#: Case-insensitive substrings identifying a template FAMILY. A version bump or a
#: language twin keeps the family marker, so a rename cannot quietly drop the guard.
_FAMILY_PATTERNS: tuple[tuple[str, frozenset[str]], ...] = (
    ("refrecord", frozenset({PARAM_TOKEN})),
    ("referandearn_invite", frozenset({PARAM_TOKEN})),
)


class MissingComputedVar(RuntimeError):
    """A required server-computed variable is missing/blank — the send is REFUSED.

    Carries the offending param name so a caller can record the stable reason
    string instead of re-parsing a message.
    """

    def __init__(self, template: str, param: str):
        self.template = template
        self.param = param
        super().__init__(
            f"refused: template {template!r} needs server-computed variable "
            f"{{{{{param}}}}} and the sender did not supply a usable value"
        )

    @property
    def reason(self) -> str:
        return missing_reason(self.param)


def missing_reason(param: str) -> str:
    """The stable machine reason string for a missing computed variable."""
    return f"{REASON_PREFIX}{param}"


def register_computed_vars(template: str, params: Iterable[str]) -> None:
    """Declare that `template` (exact elementName) carries these computed params.

    Exists so a future template can be registered next to the code that mints its
    value, rather than only in this module's literal map.
    """
    name = (template or "").strip()
    if not name:
        return
    _EXACT[name] = frozenset(_EXACT.get(name, frozenset())) | frozenset(params)


def required_computed_vars(template: str) -> frozenset[str]:
    """The set of params GoRefer must mint for this template. Empty = nothing to guard."""
    name = (template or "").strip()
    if not name:
        return frozenset()
    required: set[str] = set(_EXACT.get(name, frozenset()))
    lowered = name.lower()
    for marker, params in _FAMILY_PATTERNS:
        if marker in lowered:
            required |= set(params)
    return frozenset(required)


def _supplied_values(params) -> dict[str, str]:
    """Flatten a send's `params` into {name: value}, tolerating both shapes.

    Accepts the adapter's `params` dict (`{"template_params": [{"name","value"}]}`)
    or a bare list of `{"name","value"}` — senders build the list, the port wrapper
    sees the dict.
    """
    if isinstance(params, Mapping):
        tvars = params.get("template_params")
    else:
        tvars = params
    if not isinstance(tvars, (list, tuple)):
        return {}
    out: dict[str, str] = {}
    for item in tvars:
        if isinstance(item, Mapping):
            out[str(item.get("name") or "")] = str(item.get("value") or "")
    return out


def missing_computed_vars(template: str, params) -> list[str]:
    """Names of required computed params that are absent OR blank (whitespace counts
    as blank — " " in a URL button is exactly as dead as "")."""
    required = required_computed_vars(template)
    if not required:
        return []
    supplied = _supplied_values(params)
    return sorted(p for p in required if not supplied.get(p, "").strip())


def assert_computed_vars_filled(template: str, params) -> None:
    """THE check. Raises `MissingComputedVar` when a required computed param is
    missing or blank; returns None (silently) for every template that carries none.

    Called from the guarded messaging port (so no send path can skip it) and, ahead
    of the write, by senders that prefer to record a SKIPPED row over an exception.
    """
    missing = missing_computed_vars(template, params)
    if missing:
        raise MissingComputedVar(template, missing[0])
