"""Follow-up engine domain logic — flag, window, opt-out, and the send gate.

Kept separate from tasks.py (the django-q entry points) so the pure decision logic —
the part the DoD tests exercise — has no scheduling/adapter coupling. The gate returns a
DECISION; tasks.py applies it (sends + records). Mirrors how the codebase keeps
`redirect_service`/`lead_service` decisions apart from the views that call them.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.config.cascade import resolve

from .models import FollowupRule, FollowupWindow, ScheduledFollowup

# Cascade key (lowercase, matching the domain-config convention: landing_mode,
# disclosure_page_enabled, …). Default OFF — nothing enqueues or fires until an admin
# sets it True at the tenant tier (config.cascade.set_tenant).
FOLLOWUPS_ENABLED_KEY = "followups_enabled"

WINDOW = timedelta(hours=24)

# Gate decisions.
DEC_SEND_SESSION = "send_session"
DEC_SEND_TEMPLATE = "send_template"
DEC_CANCEL = "cancel"
DEC_SKIP = "skip"


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


def evaluate_gate(sf: ScheduledFollowup, now=None) -> tuple[str, str]:
    """Decide what to do with a due follow-up at fire time. Pure — no side effects.

    Order (doc 14 §D): flag → rule enabled → opt-out → engaged-exit → window.
    Returns (decision, reason).
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
