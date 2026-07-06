"""Read-only queries for the admin dashboard / explorer / journey detail (M7).

Headline counts read from the M4 ROLLUPS (DailyMetric/MonthlyMetric), not the raw
event firehose. The funnel + timeline reuse the M4 read models. Conversions/accounts
are Zoho-sourced only (mirrored, never fabricated). Unique counts are approximate.
"""
from __future__ import annotations

from django.db.models import Sum

from apps.events.analytics import (
    approximate_unique_visitors,
    build_journey_timeline,
    confirmed_human_clicks,
    funnel_counts,
)
from apps.events.models import DailyMetric
from apps.integrations.models import Conversion
from apps.referrals.models import Customer, Lead, Referral


def _rollup_totals(tenant):
    """Sum the daily rollups (dashboards read rollups, never the raw firehose)."""
    qs = DailyMetric.objects.all()
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    agg = qs.aggregate(
        clicks=Sum("clicks"), landing_views=Sum("landing_views"),
        redirects=Sum("redirects"), leads=Sum("leads"), accounts=Sum("accounts_opened"),
    )
    return {k: (v or 0) for k, v in agg.items()}


def kpis(tenant=None) -> dict:
    """KPI cards. accounts_opened is Zoho-sourced; unique visitors approximate."""
    totals = _rollup_totals(tenant)
    leads = totals["leads"]
    accounts = totals["accounts"]
    conv_rate = round((accounts / leads) * 100, 1) if leads else 0.0
    return {
        "total_clicks": totals["clicks"],
        "unique_visitors": approximate_unique_visitors(tenant=tenant),
        "unique_approx": True,
        "leads_captured": leads,
        "accounts_opened": accounts,
        "accounts_from_zoho": True,
        "conversion_rate": conv_rate,
    }


def funnel(tenant=None) -> list[dict]:
    """Funnel stages with a conversion% vs the previous stage (for the bars)."""
    stages = funnel_counts(tenant=tenant)
    prev = None
    for s in stages:
        s["pct_of_prev"] = (round(s["count"] / prev * 100) if prev else 100) if prev is not None else 100
        prev = s["count"] if s["count"] else prev
    return stages


def top_referrers(tenant=None, limit: int = 10) -> list[dict]:
    """Leaderboard by accounts opened, then clicks. Keyed by Zerodha client id +
    name-if-known (from Customer). Reads per-referrer aggregates from events."""
    rows = []
    qs = Referral.objects.filter(source__in=["referral_link", "zoho_import"])
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    qs = qs.select_related("referral_identity")
    for ref in qs:
        identity = ref.referral_identity
        if identity is None:
            continue
        client_id = identity.client_id
        clicks = ref.events.filter(event_type="click", is_bot=False).count()
        leads = ref.events.filter(event_type="lead_captured").count()
        accounts = ref.events.filter(event_type="account_opened").count()
        name = _referrer_name(tenant, client_id)
        rows.append({"client_id": client_id, "name": name, "clicks": clicks,
                     "leads": leads, "accounts": accounts})
    rows.sort(key=lambda r: (r["accounts"], r["clicks"]), reverse=True)
    return rows[:limit]


def _referrer_name(tenant, client_id: str) -> str:
    cust = Customer.objects.filter(tenant=tenant, client_id=client_id).exclude(first_name="").first()
    return f"{cust.first_name} {cust.last_name}".strip() if cust else ""


def recent_leads(tenant=None, limit: int = 10) -> list[dict]:
    """Recent leads with the referrer name-if-known and MASKED mobile (admin PII)."""
    qs = Lead.objects.select_related("prospect", "referral", "referral__referral_identity")
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    rows = []
    for lead in qs.order_by("-created_at")[:limit]:
        identity = lead.referral.referral_identity if lead.referral else None
        client_id = identity.client_id if identity else ""
        rows.append({
            "name": lead.prospect.name or "—",
            "mobile_masked": _mask_mobile(lead.prospect.mobile),
            "referrer": _referrer_name(tenant, client_id) or client_id or "— NONE —",
            "status": lead.status,
            "created_at": lead.created_at,
        })
    return rows


def _mask_mobile(mobile: str) -> str:
    """Mask the middle of a mobile for admin display (PII minimization)."""
    if not mobile:
        return "—"
    digits = mobile[-10:] if len(mobile) >= 10 else mobile
    if len(digits) < 6:
        return "•" * len(digits)
    return f"{digits[:3]}•••{digits[-2:]}"


def explorer_rows(tenant=None, *, source: str = "", status: str = "", search: str = ""):
    """Referral explorer rows with filters (source / status / search)."""
    qs = Referral.objects.select_related("referral_identity")
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    if source:
        qs = qs.filter(source=source)
    rows = []
    for ref in qs.order_by("-id"):
        identity = ref.referral_identity
        client_id = identity.client_id if identity else ""
        if search and search.lower() not in (client_id or "").lower():
            continue
        clicks = ref.events.filter(event_type="click", is_bot=False).count()
        landing = ref.events.filter(event_type="landing_viewed").count()
        row_status = ref.conversion_status or ref.status
        if status and status != row_status:
            continue
        last = ref.events.order_by("-timestamp").values_list("timestamp", flat=True).first()
        rows.append({
            "id": ref.id,
            "client_id": client_id,
            "referrer": _referrer_name(tenant, client_id) or (client_id if client_id else ""),
            "source": ref.source,
            "clicks": clicks,
            "landing_views": landing,
            "status": row_status,
            "last_activity": last,
            "is_partner_direct": ref.source == "partner_direct",
            "is_off_platform": ref.source == "zoho_import",
        })
    return rows


def journey_detail(referral) -> dict:
    """Journey timeline + conversion side-panel for one referral."""
    conversion = Conversion.objects.filter(referral=referral).order_by("-synced_at").first()
    conv = None
    if conversion is not None:
        conv = {
            "status": conversion.status,
            "account_opened_at": conversion.account_opened_at,  # TRUE open date
            "synced_at": conversion.synced_at,                  # distinct import date
            "referrer_client_id": conversion.referrer_client_id,
            "opener_account_id": conversion.opener_zerodha_account_id,
            "source_origin": conversion.source_origin,          # 'zoho'
            "is_reversed": conversion.is_reversed,
        }
    return {"timeline": build_journey_timeline(referral), "conversion": conv}


def confirmed_clicks(tenant=None) -> int:
    return confirmed_human_clicks(tenant=tenant)
