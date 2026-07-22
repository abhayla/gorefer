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
)
from apps.events.bots import exclude_synthetic
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


def refresh_and_freshness(tenant=None):
    """Recompute any dirty rollups so the dashboard is never stale (OBS-1), and
    return a single 'counts as of' timestamp for the whole page. KPI, funnel, and
    leaderboard all read the SAME rollup snapshot at this freshness."""
    from django.utils import timezone

    from apps.events.rollups import recompute_dirty

    recompute_dirty()
    qs = DailyMetric.objects.all()
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    last = qs.order_by("-recomputed_at").values_list("recomputed_at", flat=True).first()
    return last or timezone.now()


def kpis(tenant=None) -> dict:
    """KPI cards — ALL from the rollup snapshot (same source/freshness as the funnel).
    accounts_opened is Zoho-sourced (true open date); unique visitors approximate."""
    totals = _rollup_totals(tenant)
    clicks = totals["clicks"]
    leads = totals["leads"]
    accounts = totals["accounts"]
    # Fable5 M10: accounts_opened counts by TRUE Zoho open date (ADR-017) and INCLUDES
    # off-platform zero-lead conversions, while `leads` counts captured forms — mixed
    # populations, so accounts/leads can exceed 100% and break the KPI ring (frac>1).
    # Clamp the ratio to [0,100]; the raw counts remain exact on their own cards.
    conv_rate = round(min(100.0, (accounts / leads) * 100), 1) if leads else 0.0
    return {
        "total_clicks": clicks,
        "unique_visitors": approximate_unique_visitors(tenant=tenant),
        "unique_approx": True,
        "leads_captured": leads,
        "accounts_opened": accounts,
        "accounts_from_zoho": True,
        "conversion_rate": conv_rate,
        # Pre-computed ring fractions (0..1) for the Variant C KPI rings, so the
        # template carries no fragile arithmetic. Clicks ring is always full (it is
        # the base of the funnel); leads/conv are ratios of their prior stage.
        "clicks_frac": 1.0,
        "leads_frac": round(leads / clicks, 3) if clicks else 0.0,
        "conversion_frac": round(conv_rate / 100, 3),
    }


# Rollup column for each funnel stage (so the funnel reads the SAME source as KPIs).
_STAGE_ROLLUP_COLUMN = {
    "link_created": "links_created",
    "click": "clicks",
    "landing_viewed": "landing_views",
    "redirect_completed": "redirects",
    "lead_captured": "leads",
    "account_opened": "accounts_opened",
}


def funnel(tenant=None) -> list[dict]:
    """Funnel stages built from the SAME rollup snapshot as the KPIs (OBS-1), so a
    KPI can never sit next to a differently-sourced funnel value."""
    # Read every stage column from the rollups (same snapshot as the KPIs).
    stage_counts = {stage: _rollup_column_sum(tenant, col) for stage, col in _STAGE_ROLLUP_COLUMN.items()}
    stages, prev = [], None
    for stage, label in vocab_funnel_stages():
        count = stage_counts.get(stage, 0)
        pct = (round(count / prev * 100) if prev else 100) if prev is not None else 100
        stages.append({
            "stage": stage, "label": label, "count": count,
            "source_only": stage == "account_opened", "pct_of_prev": pct,
        })
        prev = count if count else prev
    return stages


def _rollup_column_sum(tenant, column: str) -> int:
    qs = DailyMetric.objects.all()
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    return qs.aggregate(n=Sum(column))["n"] or 0


def vocab_funnel_stages():
    from apps.events import vocab

    return vocab.FUNNEL_STAGES


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
        # Accounts = Zoho conversions credited to this referrer (single source of
        # conversion truth), consistent with the KPI/funnel accounts_opened.
        acc_qs = Conversion.objects.filter(referrer_client_id=client_id, is_reversed=False)
        if tenant is not None:
            acc_qs = acc_qs.filter(tenant=tenant)
        accounts = acc_qs.count()
        name = _referrer_name(tenant, client_id)
        rows.append({"client_id": client_id, "name": name, "clicks": clicks,
                     "leads": leads, "accounts": accounts})
    rows.sort(key=lambda r: (r["accounts"], r["clicks"]), reverse=True)
    return rows[:limit]


def _referrer_name(tenant, client_id: str) -> str:
    # Guard the tenant filter: filtering `tenant=None` matches only literally-NULL
    # rows (never real Customers), so names would never render on the tenant-agnostic
    # path. Only scope by tenant when one is supplied — same behaviour as
    # profile._referrer_name (L1/M2: the two helpers must not diverge).
    cust = Customer.objects.filter(client_id=client_id).exclude(first_name="")
    if tenant is not None:
        cust = cust.filter(tenant=tenant)
    cust = cust.first()
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


# Whitelisted sort keys for the explorer table — every visible column is sortable.
# Values are key functions over a built row dict; only last_activity can be None.
EXPLORER_SORT_KEYS = {
    "client_id": lambda r: (r["client_id"] or "").lower(),
    "referrer_name": lambda r: (r["referrer_name"] or "").lower(),
    "source": lambda r: r["source"],
    "clicks": lambda r: r["clicks"],
    "landing_views": lambda r: r["landing_views"],
    "leads": lambda r: r["leads"],
    "accounts": lambda r: r["accounts"],
    "last_activity": lambda r: r["last_activity"],
}

# "Stage reached" filter (owner design A, 2026-07-22): each row is a referral link's
# whole FUNNEL (clicks → landing opens → leads → accounts), so filtering is by the
# stage a link has reached — never by a single collapsed status word.
EXPLORER_STAGE_FILTERS = {
    "clicked": lambda r: r["clicks"] > 0,
    "landing": lambda r: r["landing_views"] > 0,
    "lead": lambda r: r["leads"] > 0,
    "account": lambda r: r["accounts"] > 0,
}


def explorer_rows(
    tenant=None,
    *,
    source: str = "",
    stage: str = "",
    search: str = "",
    sort: str = "last_activity",
    direction: str = "desc",
):
    """Referral explorer rows — one row per referral link with its full funnel
    counts (clicks / landing opens / leads / accounts), filters (source / stage
    reached / search) and whitelisted column sorting (default: newest activity).

    Counts never overstate: clicks are non-bot, leads are REAL Lead rows (created
    only by a landing-page form submit), accounts are non-reversed Zoho conversions.
    """
    qs = Referral.objects.select_related("referral_identity")
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    if source:
        qs = qs.filter(source=source)
    stage_pred = EXPLORER_STAGE_FILTERS.get(stage)
    rows = []
    for ref in qs.order_by("-id"):
        identity = ref.referral_identity
        client_id = identity.client_id if identity else ""
        if search and search.lower() not in (client_id or "").lower():
            continue
        clicks = exclude_synthetic(
            ref.events.filter(event_type="click", is_bot=False)
        ).count()
        landing = exclude_synthetic(
            ref.events.filter(event_type="landing_viewed")
        ).count()
        leads = Lead.objects.filter(referral=ref, deleted_at__isnull=True).count()
        accounts = Conversion.objects.filter(referral=ref, is_reversed=False).count()
        # Human activity only — bot/preview/synthetic pings must not refresh the
        # timestamp (DA decisions 2026-07-22; count columns exclude both already).
        last = (
            exclude_synthetic(ref.events.filter(is_bot=False))
            .order_by("-timestamp")
            .values_list("timestamp", flat=True)
            .first()
        )
        # Referrer column shows the NAME when known (Customer/Zoho); it never
        # duplicates the client id. Unknown -> a clear "name not on file" marker so
        # the "Referral ID" and "Referrer" columns are visibly distinct (DA polish).
        row = {
            "id": ref.id,
            "client_id": client_id,
            "referrer_name": _referrer_name(tenant, client_id),  # "" when unknown
            "source": ref.source,
            "clicks": clicks,
            "landing_views": landing,
            "leads": leads,
            "accounts": accounts,
            "last_activity": last,
            "is_partner_direct": ref.source == "partner_direct",
            "is_off_platform": ref.source == "zoho_import",
        }
        if stage_pred is not None and not stage_pred(row):
            continue
        rows.append(row)
    key_fn = EXPLORER_SORT_KEYS.get(sort, EXPLORER_SORT_KEYS["last_activity"])
    # Rows missing the sort value (no activity yet) always trail, in either direction.
    present = [r for r in rows if key_fn(r) is not None]
    missing = [r for r in rows if key_fn(r) is None]
    present.sort(key=key_fn, reverse=(direction != "asc"))
    return present + missing


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
