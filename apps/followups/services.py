"""Follow-up engine domain logic — flag, window, opt-out, and the send gate.

Kept separate from tasks.py (the django-q entry points) so the pure decision logic —
the part the DoD tests exercise — has no scheduling/adapter coupling. The gate returns a
DECISION; tasks.py applies it (sends + records). Mirrors how the codebase keeps
`redirect_service`/`lead_service` decisions apart from the views that call them.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.db.models import Q
from django.utils import timezone

from apps.config.cascade import resolve

from .models import FollowupRule, FollowupWindow, ScheduledFollowup, WhatsAppOptOut

logger = logging.getLogger("gorefer.followups.services")
# Cascade key (lowercase, matching the domain-config convention: landing_mode,
# disclosure_page_enabled, …). Default OFF — nothing enqueues or fires until an admin
# sets it True at the tenant tier (config.cascade.set_tenant).
FOLLOWUPS_ENABLED_KEY = "followups_enabled"

WINDOW = timedelta(hours=24)

# --- Quiet hours (owner: no sends 23:00–06:00 IST) ---------------------------
# IST is a FIXED offset (UTC+5:30, no DST), so we shift the wall clock by a constant
# rather than depend on the `tzdata` package (absent on Windows/CI by default). The
# bounds are per-tenant cascade keys so an AP can widen/narrow their own quiet window.
IST_OFFSET = timedelta(hours=5, minutes=30)
QUIET_START_KEY = "followup_quiet_start_hour"  # inclusive, IST hour (default 23)
QUIET_END_KEY = "followup_quiet_end_hour"      # exclusive, IST hour (default 6)
QUIET_START_DEFAULT = 23
QUIET_END_DEFAULT = 6

# --- Anti-burst minimum gap between sends to one contact ---------------------
# Two nudges must never reach a contact close together. Without this, quiet-hours
# deferral collapses multiple night steps onto the same 06:00 IST slot and they fire
# together — the "two identical messages at 06:03" defect the owner caught. The gate
# holds a send that would land within MIN_GAP of the contact's last SENT nudge, so
# a burst is impossible regardless of scheduling. Per-AP cascade key.
MIN_GAP_KEY = "followup_min_gap_minutes"
MIN_GAP_DEFAULT = 90

# Gate decisions.
DEC_SEND_SESSION = "send_session"
DEC_SEND_TEMPLATE = "send_template"
DEC_CANCEL = "cancel"
DEC_SKIP = "skip"
DEC_HOLD = "hold"  # would send, but quiet hours OR min-gap → defer fire_at, stay SCHEDULED


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def followups_enabled(tenant_id: int | None) -> bool:
    """The effective `followups_enabled` value for a tenant (cascade, default OFF)."""
    if tenant_id is None:
        return False
    try:
        return _as_bool(resolve(FOLLOWUPS_ENABLED_KEY, tenant_id=tenant_id, default=False))
    except Exception:
        # Config unavailable mid-migration / no tenant — conservative OFF (never send).
        return False


def get_window(tenant, mobile: str) -> FollowupWindow | None:
    return FollowupWindow.objects.for_tenant(tenant).filter(mobile=mobile).first()


def is_opted_out(tenant, mobile: str) -> bool:
    """Per-AP per-contact opt-out (doc-13 G-4; persistent registry added T-149).

    Reads BOTH real, tenant-scoped opt-out records for (tenant, mobile):
      - `FollowupWindow.opted_out` — the window-row flag, kept for back-compat with
        rows/tests that set it directly.
      - `WhatsAppOptOut` — the durable registry (T-149), which survives independently
        of the window row's own lifecycle and is what `record_opt_out` below writes.
    Either being True is enough — an opt-out must never require BOTH rows to exist.
    """
    win = get_window(tenant, mobile)
    if win is not None and win.opted_out:
        return True
    return WhatsAppOptOut.objects.for_tenant(tenant).filter(mobile=mobile).exists()


def record_opt_out(tenant, mobile: str, *, source: str = "keyword") -> None:
    """Persist an opt-out for (tenant, mobile): registry row + window flag + cancel
    every pending ScheduledFollowup for this contact (T-149).

    Idempotent — a repeat opt-out (e.g. "STOP" sent twice) is a no-op past the first
    registry row and leaves no duplicate cancellations (already-terminal rows are
    excluded from the update).
    """
    WhatsAppOptOut.objects.for_tenant(tenant).get_or_create(
        tenant=tenant, mobile=mobile, defaults={"source": source}
    )
    win = get_window(tenant, mobile)
    if win is not None:
        if not win.opted_out:
            win.opted_out = True
            win.save(update_fields=["opted_out", "updated_at"])
    else:
        FollowupWindow.objects.for_tenant(tenant).create(
            tenant=tenant, mobile=mobile, opted_out=True
        )
    (
        ScheduledFollowup.objects.for_tenant(tenant)
        .filter(mobile=mobile, status=ScheduledFollowup.STATUS_SCHEDULED)
        .update(status=ScheduledFollowup.STATUS_CANCELLED, reason="opted out", updated_at=timezone.now())
    )


# --- Opt-out keyword detection (T-149) ----------------------------------------------
# Config-resolved (rail E-6) — see apps.config.preferences.FOLLOWUP_OPTOUT_KEYWORDS_EN/_HI.
# Detection is a WHOLE-TOKEN match (never a bare substring): "STOP" must match "stop" or
# "please stop" but never "nonstop" or "stopwatch". Checked BEFORE stamp_inbound can open
# a window / start a cadence — see apps.integrations.services.record_inbound.


def _optout_keywords(tenant_id: int | None) -> list[str]:
    from apps.config.preferences import (
        FOLLOWUP_OPTOUT_KEYWORDS_EN,
        FOLLOWUP_OPTOUT_KEYWORDS_EN_DEFAULT,
        FOLLOWUP_OPTOUT_KEYWORDS_HI,
        FOLLOWUP_OPTOUT_KEYWORDS_HI_DEFAULT,
    )

    words: list[str] = []
    for key, default in (
        (FOLLOWUP_OPTOUT_KEYWORDS_EN, FOLLOWUP_OPTOUT_KEYWORDS_EN_DEFAULT),
        (FOLLOWUP_OPTOUT_KEYWORDS_HI, FOLLOWUP_OPTOUT_KEYWORDS_HI_DEFAULT),
    ):
        try:
            raw = resolve(key, tenant_id=tenant_id, default=default)
        except Exception:
            raw = default
        if isinstance(raw, list):
            words.extend(str(w) for w in raw)
        elif isinstance(raw, str) and raw.strip():
            words.append(raw)
    return [w.strip().lower() for w in words if str(w).strip()]


def is_optout_text(text: str | None, tenant_id: int | None = None) -> bool:
    """True when `text` (a raw inbound message body) is a WhatsApp opt-out keyword.

    Case-insensitive, whole-token match against the tenant's configured keyword list
    (EN + HI). An empty/None text never matches. Punctuation-trimmed on each token so
    "STOP." or "Stop!" still match.
    """
    if not text or not str(text).strip():
        return False
    keywords = set(_optout_keywords(tenant_id))
    if not keywords:
        return False
    import re

    tokens = [t.strip(".,!?।-").lower() for t in re.split(r"\s+", str(text).strip())]
    tokens = [t for t in tokens if t]
    normalized_whole = " ".join(tokens)
    return any(t in keywords for t in tokens) or normalized_whole in keywords


def stamp_inbound(tenant, mobile: str, at=None) -> tuple[FollowupWindow, bool]:
    """Record an inbound message; return (window, opened_fresh).

    `opened_fresh` is True when this inbound OPENS a new 24h window — i.e. there was no
    prior inbound, or the prior one was ≥24h ago. Only a fresh open should start a new
    cadence; a subsequent inbound inside the window refreshes `last_inbound_at` (and thus
    counts as a reply for engaged-exit) but does NOT re-enqueue.
    """
    at = at or timezone.now()
    win = FollowupWindow.objects.for_tenant(tenant).filter(mobile=mobile).first()
    if win is None:
        win = FollowupWindow.objects.create(tenant=tenant, mobile=mobile, last_inbound_at=at)
        return win, True
    prev = win.last_inbound_at
    # MONOTONIC (T-048): `last_inbound_at` only moves forward. An inbound older than the
    # one already recorded — a replayed webhook carrying its original timestamp, or a
    # poll returning an out-of-order page — must never rewind the window, because
    # rewinding CLOSES a window that is genuinely still open and silently downgrades
    # every in-window session send to the closed-window path.
    if prev is not None and at <= prev:
        return win, False
    opened_fresh = prev is None or (at - prev) >= WINDOW
    win.last_inbound_at = at
    win.save(update_fields=["last_inbound_at", "updated_at"])
    return win, opened_fresh


def window_is_open(window: FollowupWindow | None, now=None) -> bool:
    if window is None or window.last_inbound_at is None:
        return False
    now = now or timezone.now()
    return (now - window.last_inbound_at) < WINDOW


# Owner rule (CLAUDE.md §6d): message behaviour is configuration, not code. Default ON —
# never nudge someone whose account is already open — but switchable without a deploy.
SUPPRESS_WHEN_CONVERTED_KEY = "followup_stop_when_converted"
SUPPRESS_WHEN_CONVERTED_DEFAULT = True


def _suppress_when_converted(tenant_id: int | None) -> bool:
    try:
        return _as_bool(resolve(SUPPRESS_WHEN_CONVERTED_KEY, tenant_id=tenant_id,
                                default=SUPPRESS_WHEN_CONVERTED_DEFAULT))
    except Exception:
        return SUPPRESS_WHEN_CONVERTED_DEFAULT


def has_converted(tenant, mobile: str) -> bool:
    """Best-effort engaged-exit: this mobile's account has been opened, per Zoho.

    account_opened status is only ever SET from Zoho (guardrail #2) — we read it here,
    never write it. Wrapped defensively so a schema surprise can't crash the sweep.

    Reads `Referral.conversion_status` FIRST because that is the field the Zoho ingest
    actually maintains. `Lead.status` is kept as a secondary check only for
    forward-compatibility.

    Why: this gate was silently dead in production (found 2026-07-26). It checked ONLY
    `Lead.status == "account_opened"`, but `apps/integrations/zoho/ingest.py` — the sole
    path allowed to record a conversion — writes `Referral.conversion_status` /
    `Conversion` and never advances `Lead.status`. Every Lead in prod still read `"new"`,
    so `has_converted()` always returned False and a customer who had already opened their
    account kept receiving "your account is still pending" nudges for the whole 21h cadence.
    Two representations of one fact, and the gate read the one nobody wrote.
    """
    try:
        from apps.referrals.models import Lead

        return Lead.objects.for_tenant(tenant).filter(
            prospect__mobile=mobile, deleted_at__isnull=True
        ).filter(
            Q(referral__conversion_status="account_opened")
            | Q(status="account_opened")
        ).exists()
    except Exception:
        return False


def body_for(rule: FollowupRule, pref_lang: str) -> str:
    """Resolve the session-message copy for the contact's language, falling back to EN.

    The fallback is correct behaviour — better an English nudge than a blank one. But it
    was SILENT, and that hid a real gap: `seed_followup_cadence` seeds `body_hi=""` for
    every rule, so as of 2026-07-27 EVERY Hindi-preferring prospect receives the English
    cadence while the templates around it are properly bilingual. The system looks
    bilingual and is only half so.

    So the fallback now says so. Deliberately WARNING, not debug: missing copy for a
    language we advertise support for is an operational gap someone should act on, and a
    debug line nobody reads is how it stayed invisible in the first place.
    """
    if pref_lang == "hi":
        if rule.body_hi.strip():
            return rule.body_hi
        logger.warning(
            "followup copy missing for lang=hi on step=%s — falling back to English "
            "(body_hi is empty; seed_followup_cadence writes it blank)",
            rule.step_key,
        )
    return rule.body_en


def _quiet_bounds(tenant_id: int | None) -> tuple[int, int]:
    """(start, end) IST hours for quiet hours — cascade keys, default 23→6."""
    def _hour(key, default):
        try:
            return int(resolve(key, tenant_id=tenant_id, default=default))
        except Exception:
            return default
    return _hour(QUIET_START_KEY, QUIET_START_DEFAULT), _hour(QUIET_END_KEY, QUIET_END_DEFAULT)


def _ist_wall(now):
    """The IST wall clock for an aware UTC `now` (labelled UTC, but its H:M read IST)."""
    return now.astimezone(dt_timezone.utc) + IST_OFFSET


def in_quiet_hours(now, tenant_id: int | None = None) -> bool:
    """True when `now` falls in the AP's quiet window (default 23:00–06:00 IST)."""
    start, end = _quiet_bounds(tenant_id)
    hour = _ist_wall(now).hour
    if start <= end:            # same-day window
        return start <= hour < end
    return hour >= start or hour < end   # wraps midnight (the 23→6 default)


def next_active_time(now, tenant_id: int | None = None):
    """The next instant quiet hours END (the `end` hour IST), as an aware UTC datetime.

    A send deferred at night lands at 06:00 IST — the message still reaches the contact,
    just not overnight (owner rule). Computed on the fixed IST offset, no tzdata needed.
    """
    _, end = _quiet_bounds(tenant_id)
    ist = _ist_wall(now)
    target = ist.replace(hour=end, minute=0, second=0, microsecond=0)
    if ist.hour >= end:        # already past `end` today → the next `end` is tomorrow
        target = target + timedelta(days=1)
    return target - IST_OFFSET  # shift the IST wall time back to the real UTC instant


def _min_gap(tenant_id: int | None) -> timedelta:
    try:
        return timedelta(minutes=int(resolve(MIN_GAP_KEY, tenant_id=tenant_id, default=MIN_GAP_DEFAULT)))
    except Exception:
        return timedelta(minutes=MIN_GAP_DEFAULT)


def last_sent_at(tenant, mobile: str):
    """The most recent SENT nudge time for this contact (aware UTC), or None."""
    row = (
        ScheduledFollowup.objects.for_tenant(tenant).filter(
            mobile=mobile, status=ScheduledFollowup.STATUS_SENT, sent_at__isnull=False
        )
        .order_by("-sent_at")
        .values_list("sent_at", flat=True)
        .first()
    )
    return row


def within_min_gap(tenant, mobile: str, now, tenant_id: int | None) -> bool:
    """True when sending now would land within MIN_GAP of this contact's last send."""
    last = last_sent_at(tenant, mobile)
    return last is not None and (now - last) < _min_gap(tenant_id)


def compute_defer(now, tenant, mobile, tenant_id: int | None):
    """Earliest instant a held send may fire: outside quiet hours AND ≥ last_send + MIN_GAP.

    Iterates because the two constraints interact (bumping past the gap can land back in
    quiet hours, and vice-versa); converges in a couple of passes, capped so a pathological
    config can never loop forever.
    """
    gap = _min_gap(tenant_id)
    t = now
    for _ in range(4):
        moved = False
        if in_quiet_hours(t, tenant_id):
            t = next_active_time(t, tenant_id)
            moved = True
        last = last_sent_at(tenant, mobile)
        if last is not None and t < last + gap:
            t = last + gap
            moved = True
        if not moved:
            break
    return t


def evaluate_gate(sf: ScheduledFollowup, now=None) -> tuple[str, str]:
    """Decide what to do with a due follow-up at fire time. Pure — no side effects.

    Order (doc 14 §D + quiet hours): flag → rule enabled → opt-out → engaged-exit →
    window decision → quiet-hours hold. Returns (decision, reason).
    """
    now = now or timezone.now()
    rule = sf.rule

    if not followups_enabled(sf.tenant_id):
        return DEC_CANCEL, "followups disabled"
    if not rule.enabled:
        return DEC_CANCEL, "rule disabled"
    if is_opted_out(sf.tenant, sf.mobile):
        return DEC_CANCEL, "opted out"

    window = get_window(sf.tenant, sf.mobile)

    # Converted-exit is UNCONDITIONAL — deliberately NOT nested under `stop_on_reply`.
    #
    # These are two unrelated concerns that used to share one switch. Someone who replied may
    # still want reminders; someone whose account is ALREADY OPEN never does. Telling a
    # customer their account is "still pending" is embarrassing and makes the AP look
    # careless, and it must not become possible again by unticking a reply setting on some
    # future rule created through the CRUD API. Owner decision, 2026-07-26.
    #
    # Checked BEFORE the reply branch so a contact who both replied and converted reports the
    # stronger, more actionable reason.
    if _suppress_when_converted(sf.tenant_id) and has_converted(sf.tenant, sf.mobile):
        return DEC_CANCEL, "engaged: converted"

    if rule.stop_on_reply:
        # A reply = an inbound strictly AFTER the window that scheduled this step.
        if window is not None and window.last_inbound_at is not None \
                and window.last_inbound_at > sf.window_opened_at:
            return DEC_CANCEL, "engaged: replied"

    decision, reason = _window_decision(rule, window, now)

    # A would-be SEND is deferred (never cancelled) for two reasons, both to protect the
    # recipient's experience:
    #  1) Quiet hours — nobody is messaged 23:00–06:00 IST (owner rule).
    #  2) Min-gap — two nudges must never reach a contact close together; without this,
    #     multiple quiet-hours-deferred steps collapse onto one 06:00 slot and fire as an
    #     identical-looking burst (the defect the owner caught). Either → DEC_HOLD; the
    #     sweep re-computes fire_at via compute_defer (satisfies BOTH constraints).
    if decision in (DEC_SEND_SESSION, DEC_SEND_TEMPLATE):
        if in_quiet_hours(now, sf.tenant_id):
            # Report the CONFIGURED end hour, not a hardcoded 06:00 — an AP can widen or
            # narrow its own quiet window, and a reason string that names the wrong hour is a
            # lie in the audit trail (observed 2026-07-26: window shifted to 16-18 IST, the
            # row correctly deferred to 18:00 while the reason still claimed 06:00).
            _, _end = _quiet_bounds(sf.tenant_id)
            return DEC_HOLD, f"quiet hours — deferred to {_end:02d}:00 IST"
        if within_min_gap(sf.tenant, sf.mobile, now, sf.tenant_id):
            return DEC_HOLD, "min-gap — spacing sends to avoid a burst"
    return decision, reason


def _window_decision(rule: FollowupRule, window, now) -> tuple[str, str]:
    """The window-state branch of the gate (pre quiet-hours)."""
    if window_is_open(window, now):
        if rule.channel == FollowupRule.CHANNEL_TEMPLATE and rule.template_name:
            return DEC_SEND_TEMPLATE, "window open, template channel"
        return DEC_SEND_SESSION, "window open"

    # Window closed (>24h since last inbound, or never opened).
    if rule.only_if_window_open:
        return DEC_SKIP, "window closed (session-only)"
    if rule.template_name:
        return DEC_SEND_TEMPLATE, "window closed, template fallback"
    return DEC_SKIP, "window closed, no template"
