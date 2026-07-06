"""Read-only analytics API (M4). Feeds the M7 dashboard/journey screens.

Everything here reads the immutable event stream / rollups. No conversion is ever
written or derived — account_opened stays source-only (Zoho, M6).
"""
from __future__ import annotations

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.events.analytics import (
    approximate_unique_visitors,
    build_journey_timeline,
    confirmed_human_clicks,
    funnel_counts,
)
from apps.events.models import SyncHealth
from apps.referrals.models import Referral
from apps.tenants.resolve import get_current_tenant

router = Router()


class FunnelStage(Schema):
    stage: str
    label: str
    count: int
    source_only: bool


class FunnelOut(Schema):
    stages: list[FunnelStage]
    confirmed_human_clicks: int
    unique_visitors_approx: int
    unique_visitors_note: str


@router.get("/funnel", response=FunnelOut)
def funnel(request):
    tenant = get_current_tenant(request)
    return {
        "stages": funnel_counts(tenant=tenant),
        "confirmed_human_clicks": confirmed_human_clicks(tenant=tenant),
        "unique_visitors_approx": approximate_unique_visitors(tenant=tenant),
        "unique_visitors_note": "Approximate — cookie-keyed, bot-filtered (ADR-018/019).",
    }


class TimelineNode(Schema):
    event_type: str
    label: str
    source: str
    timestamp: str


@router.get("/journey/{referral_id}", response=list[TimelineNode])
def journey(request, referral_id: int):
    tenant = get_current_tenant(request)
    referral = Referral.objects.filter(id=referral_id, tenant=tenant).first()
    if referral is None:
        raise HttpError(404, "referral not found")
    nodes = build_journey_timeline(referral)
    return [{**n, "timestamp": n["timestamp"].isoformat()} for n in nodes]


class SyncHealthOut(Schema):
    zoho_state: str
    zoho_last_sync: str | None
    wati_state: str
    note: str


@router.get("/sync-health", response=SyncHealthOut)
def sync_health(request):
    tenant = get_current_tenant(request)
    row = SyncHealth.objects.filter(tenant=tenant).order_by("-updated_at").first()
    if row is None:
        return {"zoho_state": "no_sync", "zoho_last_sync": None, "wati_state": "no_sync",
                "note": "No sync yet — Zoho/WATI integrate in M5/M6."}
    last_sync = row.last_successful_zoho_sync_at
    return {
        "zoho_state": row.zoho_state,
        "zoho_last_sync": last_sync.isoformat() if last_sync else None,
        "wati_state": row.wati_state,
        "note": "Populated by M5/M6.",
    }
