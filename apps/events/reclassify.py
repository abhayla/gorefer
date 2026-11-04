"""History repair: re-flag past clicks from datacenter/crawler networks as bots.

ADR-019 amendment 2026-11-04. The live click path now writes is_bot=True for a click
whose IP is in the datacenter network table; clicks recorded BEFORE that change are
still is_bot=False. This sweep repairs them from the erasable VisitorPII record.

Rules:
- Only CLICK events with is_bot=False are candidates (idempotent: a re-run finds the
  repaired rows already is_bot=True and skips them).
- IP source: the click's own VisitorPII row (Event.person_ref_id); if that is absent,
  the visitor's latest VisitorPII row by visitor_id. Erased rows (raw_ip NULL) are
  skipped via `raw_ip__isnull=False` - never `raw_ip=""`, which on a
  GenericIPAddressField silently matches nothing.
- The click's LANDING_VIEWED twin (same visitor + referral, written in the same request
  within LANDING_TWIN_SECONDS) gets the same verdict, matching the live path.
- Writes is_bot=True + metadata {"bot_reason": "datacenter", "network": org}, keeps
  every other metadata key, and marks each affected day dirty for the rollups.
- NEVER touches VisitorPII.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import vocab
from .models import Event, VisitorPII
from .netranges import DATACENTER_BOT_REASON, NetworkTable
from .rollups import mark_dirty

LANDING_TWIN_SECONDS = 5
PARTNER_DIRECT = "partner-direct"
REFERRAL = "referral"


def _kind(referral) -> str:
    if referral is not None and referral.source == "partner_direct":
        return PARTNER_DIRECT
    return REFERRAL


def reclassify_datacenter_clicks(table: NetworkTable, *, tenant=None, apply: bool = False) -> dict:
    clicks = Event.objects.filter(event_type=vocab.CLICK, is_bot=False).select_related("referral")
    if tenant is not None:
        clicks = clicks.for_tenant(tenant)
    clicks = list(clicks.order_by("id"))

    pii = VisitorPII.objects.filter(raw_ip__isnull=False)
    if tenant is not None:
        pii = pii.for_tenant(tenant)
    ref_ids = {e.person_ref_id for e in clicks if e.person_ref_id}
    vids = {e.visitor_id for e in clicks if e.visitor_id}
    ip_by_pk = dict(pii.filter(pk__in=ref_ids).values_list("pk", "raw_ip"))
    ip_by_visitor: dict[tuple[int, str], str] = {}
    for tid, vid, ip in pii.filter(visitor_id__in=vids).order_by("id").values_list(
        "tenant_id", "visitor_id", "raw_ip"
    ):
        ip_by_visitor[(tid, vid)] = ip  # ascending id -> the latest wins

    scanned = len(clicks)
    no_ip = 0
    by_network: Counter = Counter()
    by_kind: Counter = Counter()
    human_by_kind: Counter = Counter()
    flagged: list[tuple[Event, str]] = []
    for ev in clicks:
        ip = ip_by_pk.get(ev.person_ref_id) if ev.person_ref_id else None
        if ip is None and ev.visitor_id:
            ip = ip_by_visitor.get((ev.tenant_id, ev.visitor_id))
        if ip is None:
            no_ip += 1
            human_by_kind[_kind(ev.referral)] += 1
            continue
        is_dc, org = table.lookup(ip)
        if not is_dc:
            human_by_kind[_kind(ev.referral)] += 1
            continue
        flagged.append((ev, org or ""))
        by_network[org or ""] += 1
        by_kind[_kind(ev.referral)] += 1

    twins = 0
    dirty: set[tuple[int, int, object]] = set()
    if apply and flagged:
        with transaction.atomic():
            for ev, org in flagged:
                twin_qs = Event.objects.filter(
                    tenant_id=ev.tenant_id, event_type=vocab.LANDING_VIEWED, is_bot=False,
                    visitor_id=ev.visitor_id, referral_id=ev.referral_id,
                    timestamp__gte=ev.timestamp,
                    timestamp__lte=ev.timestamp + timedelta(seconds=LANDING_TWIN_SECONDS),
                ) if ev.visitor_id else Event.objects.none()
                for target in [ev, *twin_qs.order_by("id")[:1]]:
                    meta = dict(target.metadata or {})
                    meta["bot_reason"] = DATACENTER_BOT_REASON
                    meta["network"] = org
                    n = Event.objects.filter(pk=target.pk, is_bot=False).update(is_bot=True, metadata=meta)
                    if n and target.pk != ev.pk:
                        twins += 1
                    if n and target.referral_id and target.referral.program_id:
                        day = timezone.localtime(target.timestamp).date()
                        dirty.add((target.tenant_id, target.referral.program_id, day))
            for tenant_id, program_id, day in dirty:
                ev0 = next(e for e, _ in flagged if e.tenant_id == tenant_id
                           and e.referral and e.referral.program_id == program_id)
                mark_dirty(tenant=ev0.tenant, program=ev0.referral.program, on_date=day)

    return {
        "applied": apply,
        "scanned_clicks": scanned,
        "clicks_without_ip": no_ip,
        "datacenter_clicks": len(flagged),
        "by_network": dict(by_network.most_common()),
        "by_kind": dict(by_kind),
        "remaining_human_by_kind": dict(human_by_kind),
        "landing_twins_flagged": twins,
        "dirty_days": len(dirty),
    }
