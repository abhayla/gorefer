"""Read-only analytics: journey timeline + funnel aggregation (M4).

Everything here READS the immutable event stream — it never writes conversions or
mutates events. Bots are excluded; unique-visitor counts are approximate (keyed on
gr_vid) and must be labelled as such. account_opened / reward stages stay
source-only (Zoho, M6) — 0 / "pending Zoho" until a Zoho import exists (M6). Nothing
here fabricates a conversion.
"""
from __future__ import annotations

from django.db.models import Count

from . import vocab
from .models import Event

# Human-readable labels for the timeline nodes.
_EVENT_LABELS = {
    vocab.LINK_CREATED: "Link created",
    vocab.CLICK: "Clicked",
    vocab.LANDING_VIEWED: "Landing viewed",
    vocab.HUMAN_CONFIRMED: "Human confirmed",
    vocab.LEAD_CAPTURED: "Lead captured",
    vocab.REDIRECT_COMPLETED: "Redirected",
    vocab.SHARE_CLICKED: "Shared",
    vocab.ACCOUNT_OPENED: "Account opened",
    vocab.REWARD_STATUS_CHANGED: "Reward updated",
}


def build_journey_timeline(referral) -> list[dict]:
    """Ordered event timeline for one referral. Each node: type, label, source, ts.

    Read model for the M7 journey-detail screen. Bots excluded (they never created a
    journey anyway). No PII — labels/source/timestamp only.
    """
    from apps.events.bots import exclude_synthetic

    events = (
        exclude_synthetic(Event.objects.filter(referral=referral, is_bot=False))
        .order_by("timestamp", "id")
        .values("event_type", "source", "timestamp")
    )
    return [
        {
            "event_type": e["event_type"],
            "label": _EVENT_LABELS.get(e["event_type"], e["event_type"]),
            "source": e["source"],
            "timestamp": e["timestamp"],
        }
        for e in events
    ]


def funnel_counts(*, tenant, program=None) -> list[dict]:
    """Funnel stage counts from the immutable event stream (bots excluded).

    Returns one row per FUNNEL_STAGES entry: {stage, label, count, source_only}.
    `account_opened` is source-only — it reads 0 until a Zoho import exists (M6);
    it is NEVER derived from clicks/leads. `click` uses confirmed-human counts is
    reported separately via confirmed_human_clicks().

    `tenant` is REQUIRED (no all-tenants default) — a caller that forgets it is a
    TypeError, not a silent cross-tenant aggregate (T-161 pt 8).
    """
    from apps.events.bots import exclude_synthetic

    qs = exclude_synthetic(Event.objects.filter(is_bot=False)).for_tenant(tenant)
    if program is not None:
        qs = qs.filter(referral__program=program)

    per_type = dict(
        qs.values_list("event_type").annotate(n=Count("id")).values_list("event_type", "n")
    )
    rows = []
    for stage, label in vocab.FUNNEL_STAGES:
        rows.append({
            "stage": stage,
            "label": label,
            "count": per_type.get(stage, 0),
            "source_only": stage in vocab.ZOHO_ONLY_EVENTS,  # pending Zoho (M6)
        })
    return rows


def confirmed_human_clicks(*, tenant) -> int:
    """Count of confirmed-human click events (is_confirmed_human, bots excluded).

    `tenant` is REQUIRED (T-161 pt 8) — see `funnel_counts` docstring.
    """
    from apps.events.bots import exclude_synthetic

    qs = exclude_synthetic(
        Event.objects.filter(event_type=vocab.CLICK, is_bot=False, is_confirmed_human=True)
    ).for_tenant(tenant)
    return qs.count()


def approximate_unique_visitors(*, tenant) -> int:
    """APPROXIMATE unique-visitor count (distinct gr_vid, bots excluded).

    Approximate by construction (cookie-keyed) — callers MUST label it as such
    (ADR-018/019). Never asserted as an exact human count. `tenant` is REQUIRED
    (T-161 pt 8) — see `funnel_counts` docstring.
    """
    from apps.events.bots import exclude_synthetic

    qs = exclude_synthetic(
        Event.objects.filter(is_bot=False).exclude(visitor_id__isnull=True).exclude(visitor_id="")
    ).for_tenant(tenant)
    return qs.values("visitor_id").distinct().count()
