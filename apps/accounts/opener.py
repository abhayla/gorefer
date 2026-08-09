"""The referrer's PERSONAL share-message opener (T-064) — storage + the write rules.

Owner decision, 2026-08-10: a referrer should be able to say the invitation in their
own words, edited straight on `/hub/{token}` (the token IS the identity, exactly like
a password-reset link), with the platform guaranteeing the parts that must not move.

The guarantee is structural, not a validation rule:

    this module stores ONE piece of text — an OPENING line — and nothing else.

The credit link and the compliance disclosure line are appended AFTER it, server-side,
every time a message is composed (`apps.referrals.share_intent_service.kit_message`).
So there is no string a referrer can type that removes them, reorders them, or turns
them into something else: they are concatenated on, not parsed out of, the opener. The
opener is never passed through `str.format()` either, so a `{link}`-shaped payload is
inert text rather than a placeholder someone else's template will fill in.

What IS validated here is narrow and mechanical: control characters are stripped
(a lone `\\r` or a NUL byte does nothing good in a WhatsApp payload), runs of blank
lines are collapsed, and the text is truncated to the cascade-resolved cap. Truncation
rather than rejection is deliberate — the hub renders the SAVED text straight back, so
a referrer who overshoots sees exactly what will be sent instead of an error page.

One text, no EN/HI twin (owner-decided): the referrer writes in whatever language they
speak, and only the LOCKED tail follows the T-062 language lane.
"""
from __future__ import annotations

import re

from apps.config.cascade import resolve as resolve_config
from apps.config.preferences import (
    REFERRER_SHARE_OPENER_ENABLED,
    REFERRER_SHARE_OPENER_ENABLED_DEFAULT,
    REFERRER_SHARE_OPENER_MAX_CHARS,
    REFERRER_SHARE_OPENER_MAX_CHARS_DEFAULT,
)

from .models import ReferrerShareOpener

#: Everything in the C0/C1 control ranges except newline and tab. `\r` is normalized to
#: `\n` first (below) rather than dropped, so a paste from a Windows editor keeps its
#: line breaks instead of silently welding two lines together.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

#: Three or more newlines collapse to a paragraph break. Without this, a referrer can
#: push the link and the disclosure line far enough down a WhatsApp bubble that they sit
#: behind a "Read more" tap — which is removal of the locked parts in every way that
#: matters to a reader, even though the bytes are still there.
_BLANK_RUNS = re.compile(r"\n{3,}")


def is_enabled(tenant_id: int | None) -> bool:
    """Whether the personalization surface exists for this tenant (rail E-6 gate).

    Default TRUE — the feature ships complete (edit, reset, composition, admin reset),
    so gating it off by default would mean shipping a finished surface nobody can see.
    An owner turning it off flips one tenant row, no deploy (§6d).
    """
    raw = resolve_config(
        REFERRER_SHARE_OPENER_ENABLED,
        tenant_id=tenant_id,
        default=REFERRER_SHARE_OPENER_ENABLED_DEFAULT,
    )
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def max_chars(tenant_id: int | None) -> int:
    """The cascade-resolved write cap. A missing/garbage/non-positive stored value
    falls back to the default: a zero cap would silently erase every opener on save,
    which is a far worse failure than the cap being the shipped 300."""
    raw = resolve_config(
        REFERRER_SHARE_OPENER_MAX_CHARS,
        tenant_id=tenant_id,
        default=REFERRER_SHARE_OPENER_MAX_CHARS_DEFAULT,
    )
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return REFERRER_SHARE_OPENER_MAX_CHARS_DEFAULT
    return limit if limit > 0 else REFERRER_SHARE_OPENER_MAX_CHARS_DEFAULT


def sanitize(raw: str | None, limit: int) -> str:
    """Normalize referrer-typed text to something safe to concatenate and store.

    NOT an HTML/markup filter — escaping is the renderer's job and Django's autoescape
    does it on every surface this text reaches (the hub textarea, `json_script` for the
    share payload). Trying to strip tags here as well would be a second, weaker escape
    layer that only creates disagreement about which one is authoritative.
    """
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _BLANK_RUNS.sub("\n\n", text)
    # Trim each line's trailing spaces, then the whole block — a message that opens or
    # closes on whitespace reads as a formatting bug in the recipient's chat.
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text[: max(0, limit)].strip()


def _row(identity):
    """This identity's opener row, tenant-scoped (rail E-7), or None."""
    return (
        ReferrerShareOpener.objects.for_tenant(identity.tenant_id)
        .filter(identity=identity)
        .first()
    )


def get_opener(identity) -> str:
    """The referrer's saved opener, or "" when unset, blank, or the feature is off.

    Reading through the flag matters: turning the tenant key off must make every
    outgoing message revert to the official copy immediately, without anyone having to
    clear rows first.
    """
    if identity is None or getattr(identity, "pk", None) is None:
        # An unsaved/stub identity cannot have a stored row — answer without a query
        # rather than letting the ORM raise on a pk that is not a number.
        return ""
    if not is_enabled(identity.tenant_id):
        return ""
    row = _row(identity)
    return (row.text if row else "") or ""


def set_opener(identity, raw: str | None) -> str:
    """Save (or clear) this referrer's opener. Returns the text as STORED.

    Empty input clears the row's text rather than deleting the row — "cleared" and
    "never set" must behave identically downstream (both mean: use the official
    message), and keeping the row preserves `updated_at` as an edit trail.
    """
    text = sanitize(raw, max_chars(identity.tenant_id))
    row, created = ReferrerShareOpener.objects.get_or_create(
        identity=identity, defaults={"tenant_id": identity.tenant_id, "text": text}
    )
    if not created and row.text != text:
        row.text = text
        row.save(update_fields=["text", "updated_at"])
    return text


def clear_opener(identity) -> None:
    """Revert this referrer to the tenant's official message (the admin reset, and the
    hub's own "use the standard message" button)."""
    set_opener(identity, "")
