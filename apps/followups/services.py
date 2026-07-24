"""Follow-up engine domain logic — flag, window, opt-out, and the send gate.

Kept separate from tasks.py (the django-q entry points) so the pure decision logic —
the part the DoD tests exercise — has no scheduling/adapter coupling. The gate returns a
DECISION; tasks.py applies it (sends + records). Mirrors how the codebase keeps
`redirect_service`/`lead_service` decisions apart from the views that call them.
"""
from __future__ import annotations

from datetime import timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from apps.config.cascade import resolve

from .models import FollowupRule, FollowupWindow, ScheduledFollowup

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

# Gate decisions.
DEC_SEND_SESSION = "send_session"
DEC_SEND_TEMPLATE = "send_template"
DEC_CANCEL = "cancel"
DEC_SKIP = "skip"
DEC_HOLD = "hold"  # would send, but it's quiet hours → defer fire_at, stay SCHEDULED


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
    return FollowupWindow.objects.filter(tenant=tenant, mobile=mobile).first()


def is_opted_out(tenant, mobile: str) -> bool:
    """Per-AP per-contact opt-out (doc-13 G-4).

    Primary store is the window row's `opted_out` flag (keyed by tenant+mobile, exactly
    the AP-per-contact scope). Also honours a future `whatsapp_opt_out` on a matching
    Prospect (the hook wati/notify already reads), so a later field suppresses cleanly.
    """
    win = get_window(tenant, mobile)
    if win is not None and win.opted_out:
        return True
    from apps.referrals.models import Prospect

    return Prospect.objects.filter(
        tenant=tenant, mobile=mobile, deleted_at__isnull=True, whatsapp_opt_out=True
    ).exists() if _prospect_has_optout_field() else False


def _prospect_has_optout_field() -> bool:
    from apps.referrals.models import Prospect

    return any(f.name == "whatsapp_opt_out" for f in Prospect._meta.get_fields())


def stamp_inbound(tenant, mobile: str, at=None) -> tuple[FollowupWindow, bool]:
    """Record an inbound message; return (window, opened_fresh).

    `opened_fresh` is True when this inbound OPENS a new 24h window — i.e. there was no
    prior inbound, or the prior one was ≥24h ago. Only a fresh open should start a new
    cadence; a subsequent inbound inside the window refreshes `last_inbound_at` (and thus
    counts as a reply for engaged-exit) but does NOT re-enqueue.
    """
    at = at or timezone.now()
    win = FollowupWindow.objects.filter(tenant=tenant, mobile=mobile).first()
    if win is None:
        win = FollowupWindow.objects.create(tenant=tenant, mobile=mobile, last_inbound_at=at)
        return win, True
    prev = win.last_inbound_at
    opened_fresh = prev is None or (at - prev) >= WINDOW
    win.last_inbound_at = at
    win.save(update_fields=["last_inbound_at", "updated_at"])
    return win, opened_fresh


def window_is_open(window: FollowupWindow | None, now=None) -> bool:
    if window is None or window.last_inbound_at is None:
        return False
    now = now or timezone.now()
    return (now - window.last_inbound_at) < WINDOW


def has_converted(tenant, mobile: str) -> bool:
    """Best-effort engaged-exit: a lead for this mobile has reached account_opened.

    account_opened status is only ever set from Zoho (guardrail #2) — we read it here,
    never write it. Wrapped defensively so a schema surprise can't crash the sweep.
    """
    try:
        from apps.referrals.models import Lead

        return Lead.objects.filter(
            tenant=tenant, prospect__mobile=mobile, status="account_opened", deleted_at__isnull=True
        ).exists()
    except Exception:
        return False


def body_for(rule: FollowupRule, pref_lang: str) -> str:
    """Resolve the session-message copy for the contact's language, falling back to EN."""
    if pref_lang == "hi" and rule.body_hi.strip():
        return rule.body_hi
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
    if rule.stop_on_reply:
        # A reply = an inbound strictly AFTER the window that scheduled this step.
        if window is not None and window.last_inbound_at is not None \
                and window.last_inbound_at > sf.window_opened_at:
            return DEC_CANCEL, "engaged: replied"
        if has_converted(sf.tenant, sf.mobile):
            return DEC_CANCEL, "engaged: converted"

    decision, reason = _window_decision(rule, window, now)

    # Quiet hours suppress SENDS only (never a cancel/skip): defer a would-be send to
    # 06:00 IST so nobody is messaged 23:00–06:00 IST (owner rule).
    if decision in (DEC_SEND_SESSION, DEC_SEND_TEMPLATE) and in_quiet_hours(now, sf.tenant_id):
        return DEC_HOLD, "quiet hours — deferred to 06:00 IST"
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
