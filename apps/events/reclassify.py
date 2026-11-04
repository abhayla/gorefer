"""History repair: re-flag past datacenter/crawler VISITS as bots.

ADR-019 amendment 2026-11-04. The live click path writes is_bot=True for every event
of a visit whose click IP is in the datacenter network table (the click, its
landing_viewed twin, the beacon's human_confirmed row). Visits recorded BEFORE that
change are still is_bot=False; this sweep repairs them from the erasable VisitorPII
record, so click counts, rollups AND approximate unique visitors all drop.

Rules:
- A visit starts at a CLICK event. Its IP is the click's OWN VisitorPII row
  (Event.person_ref_id). A click with no linked PII row, or whose row was erased
  (raw_ip NULL - filtered by `raw_ip__isnull=False`, never `raw_ip=""`, which on a
  GenericIPAddressField silently matches nothing), is SKIPPED and counted - never
  guessed from another visit's IP.
- A datacenter visit = every is_bot=False event of the same tenant + visitor_id from
  that click's timestamp up to (not including) the visitor's NEXT click. A later visit
  of the same visitor from a home IP starts at its own click and is left alone.
  A datacenter click with no visitor_id flags only itself.
- Writes is_bot=True + metadata {"bot_reason": "datacenter", "network": org}, keeps
  every other metadata key, marks each affected day dirty for the rollups.
- Dry run (default) writes nothing. Idempotent. NEVER touches VisitorPII.
"""
from __future__ import annotations

from collections import Counter

from django.db import transaction
from django.utils import timezone

from . import vocab
from .models import Event, VisitorPII
from .netranges import DATACENTER_BOT_REASON, NetworkTable
from .rollups import mark_dirty

PARTNER_DIRECT = "partner-direct"
REFERRAL = "referral"


def _kind(referral) -> str:
    if referral is not None and referral.source == "partner_direct":
        return PARTNER_DIRECT
    return REFERRAL


def _visit_events(click: Event) -> list[Event]:
    """is_bot=False events of the click's visit (the click itself included)."""
    if not click.visitor_id:
        return [click]
    next_click_ts = (
        Event.objects.filter(
            tenant_id=click.tenant_id, visitor_id=click.visitor_id, event_type=vocab.CLICK,
            timestamp__gt=click.timestamp,
        ).order_by("timestamp").values_list("timestamp", flat=True).first()
    )
    qs = Event.objects.filter(
        tenant_id=click.tenant_id, visitor_id=click.visitor_id, is_bot=False,
        timestamp__gte=click.timestamp,
    ).select_related("referral")
    if next_click_ts is not None:
        qs = qs.filter(timestamp__lt=next_click_ts)
    events = list(qs.order_by("id"))
    if click.pk not in {e.pk for e in events}:
        events.insert(0, click)
    return events


def reclassify_datacenter_clicks(table: NetworkTable, *, tenant=None, apply: bool = False) -> dict:
    clicks = Event.objects.filter(event_type=vocab.CLICK, is_bot=False).select_related("referral")
    if tenant is not None:
        clicks = clicks.for_tenant(tenant)
    clicks = list(clicks.order_by("id"))

    pii = VisitorPII.objects.filter(raw_ip__isnull=False)
    if tenant is not None:
        pii = pii.for_tenant(tenant)
    ip_by_pk = dict(
        pii.filter(pk__in={e.person_ref_id for e in clicks if e.person_ref_id}).values_list("pk", "raw_ip")
    )

    skipped_no_ip = 0
    by_network: Counter = Counter()
    by_kind: Counter = Counter()
    human_by_kind: Counter = Counter()
    flagged_clicks: list[tuple[Event, str]] = []
    for ev in clicks:
        ip = ip_by_pk.get(ev.person_ref_id) if ev.person_ref_id else None
        if ip is None:
            skipped_no_ip += 1
            continue
        is_dc, org = table.lookup(ip)
        if not is_dc:
            human_by_kind[_kind(ev.referral)] += 1
            continue
        flagged_clicks.append((ev, org or ""))
        by_network[org or ""] += 1
        by_kind[_kind(ev.referral)] += 1

    # The whole visit of each datacenter click (read-only; same in dry run and apply).
    targets: dict[int, tuple[Event, str]] = {}
    for click, org in flagged_clicks:
        for ev in _visit_events(click):
            targets.setdefault(ev.pk, (ev, org))
    by_event_type = Counter(ev.event_type for ev, _ in targets.values())
    dc_visitors = {(ev.tenant_id, ev.visitor_id) for ev, _ in targets.values() if ev.visitor_id}

    written = 0
    dirty: dict[tuple[int, int, object], Event] = {}
    if apply and targets:
        with transaction.atomic():
            for ev, org in targets.values():
                meta = dict(ev.metadata or {})
                meta["bot_reason"] = DATACENTER_BOT_REASON
                meta["network"] = org
                n = Event.objects.filter(pk=ev.pk, is_bot=False).update(is_bot=True, metadata=meta)
                written += n
                if n and ev.referral_id and ev.referral.program_id:
                    day = timezone.localtime(ev.timestamp).date()
                    dirty.setdefault((ev.tenant_id, ev.referral.program_id, day), ev)
            for (_tid, _pid, day), ev in dirty.items():
                mark_dirty(tenant=ev.tenant, program=ev.referral.program, on_date=day)

    return {
        "applied": apply,
        "scanned_clicks": len(clicks),
        "skipped_no_linked_ip": skipped_no_ip,
        "datacenter_clicks": len(flagged_clicks),
        "datacenter_visitors": len(dc_visitors),
        "by_network": dict(by_network.most_common()),
        "by_kind": dict(by_kind),
        "by_event_type": dict(sorted(by_event_type.items())),
        "remaining_human_by_kind": dict(human_by_kind),
        "events_written": written,
        "dirty_days": len(dirty),
    }
