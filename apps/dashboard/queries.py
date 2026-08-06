"""Read-only queries for the admin dashboard / explorer / journey detail (M7).

Headline counts read from the M4 ROLLUPS (DailyMetric/MonthlyMetric), not the raw
event firehose. The funnel + timeline reuse the M4 read models. Conversions/accounts
are Zoho-sourced only (mirrored, never fabricated). Unique counts are approximate.
"""
from __future__ import annotations

from django.db.models import (
    CharField,
    Count,
    F,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Concat, Lower, Trim

from apps.events.analytics import (
    approximate_unique_visitors,
    build_journey_timeline,
    confirmed_human_clicks,
)
from apps.events.bots import synthetic_ua_q
from apps.events.models import DailyMetric
from apps.integrations.models import Conversion
from apps.referrals.models import Customer, Lead, Referral


def _rollup_totals(tenant):
    """Sum the daily rollups (dashboards read rollups, never the raw firehose)."""
    qs = DailyMetric.objects.all()
    if tenant is not None:
        qs = qs.for_tenant(tenant)
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
        qs = qs.for_tenant(tenant)
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
        qs = qs.for_tenant(tenant)
    return qs.aggregate(n=Sum(column))["n"] or 0


def vocab_funnel_stages():
    from apps.events import vocab

    return vocab.FUNNEL_STAGES


def _accounts_by_client_id_subquery(tenant):
    """Correlated count of non-reversed Conversions credited to a client id.

    Used where the accounting is keyed by the referrer's Zerodha client id
    (Zoho-sourced credit), not by a single Referral row's own FK.
    """
    sub = Conversion.objects.filter(
        referrer_client_id=OuterRef("referral_identity__client_id"), is_reversed=False
    )
    if tenant is not None:
        sub = sub.for_tenant(tenant)
    sub = sub.order_by().values("referrer_client_id").annotate(cnt=Count("id")).values("cnt")
    return Coalesce(Subquery(sub, output_field=IntegerField()), Value(0))


def _referrer_name_subquery(tenant):
    """Correlated 'first last' name lookup keyed by referral_identity's client id —
    the SINGLE shared implementation `_referrer_name` (scalar, below) also uses."""
    sub = (
        Customer.objects.filter(client_id=OuterRef("referral_identity__client_id"))
        .exclude(first_name="")
    )
    if tenant is not None:
        sub = sub.for_tenant(tenant)
    sub = (
        sub.order_by("id")
        .annotate(full=Trim(Concat("first_name", Value(" "), "last_name", output_field=CharField())))
        .values("full")
    )
    return Coalesce(Subquery(sub[:1], output_field=CharField()), Value(""))


def top_referrers(tenant=None, limit: int = 10) -> list[dict]:
    """Leaderboard by accounts opened, then clicks. Keyed by Zerodha client id +
    name-if-known (from Customer). Reads per-referrer aggregates via annotations —
    zero per-row queries regardless of how many referrals exist."""
    not_synth_events = ~synthetic_ua_q(prefix="events__")
    qs = Referral.objects.filter(
        source__in=["referral_link", "zoho_import"], referral_identity__isnull=False
    )
    if tenant is not None:
        qs = qs.for_tenant(tenant)
    qs = qs.select_related("referral_identity").annotate(
        clicks=Count(
            "events",
            filter=Q(events__event_type="click", events__is_bot=False) & not_synth_events,
            distinct=True,
        ),
        leads_count=Count("events", filter=Q(events__event_type="lead_captured"), distinct=True),
        accounts=_accounts_by_client_id_subquery(tenant),
        name=_referrer_name_subquery(tenant),
    ).order_by("-accounts", "-clicks")[:limit]
    return [
        {
            "client_id": ref.referral_identity.client_id,
            "name": ref.name,
            "clicks": ref.clicks,
            "leads": ref.leads_count,
            "accounts": ref.accounts,
        }
        for ref in qs
    ]


def _referrer_name(tenant, client_id: str) -> str:
    # Guard the tenant filter: filtering `tenant=None` matches only literally-NULL
    # rows (never real Customers), so names would never render on the tenant-agnostic
    # path. Only scope by tenant when one is supplied — the ONE shared helper
    # (imported by apps/dashboard/profile.py so the two paths cannot diverge).
    cust = Customer.objects.filter(client_id=client_id).exclude(first_name="")
    if tenant is not None:
        cust = cust.for_tenant(tenant)
    cust = cust.first()
    return f"{cust.first_name} {cust.last_name}".strip() if cust else ""


def recent_leads(tenant=None, limit: int = 10) -> list[dict]:
    """Recent leads with the referrer name-if-known and MASKED mobile (admin PII)."""
    qs = Lead.objects.select_related("prospect", "referral", "referral__referral_identity")
    if tenant is not None:
        qs = qs.for_tenant(tenant)
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


# Maps an EXPLORER_SORT_KEYS name to the annotated field the DB-level order_by
# actually sorts on (see _annotated_explorer_qs). Kept 1:1 with EXPLORER_SORT_KEYS
# so a whitelisted sort key always has a matching DB column.
_EXPLORER_SORT_FIELD = {
    "client_id": "client_id_lower",
    "referrer_name": "referrer_name_lower",
    "source": "source",
    "clicks": "clicks",
    "landing_views": "landing_views",
    "leads": "leads_count",
    "accounts": "accounts",
    "last_activity": "last_activity",
}

# Stage filters as Q objects over the annotated fields (DB-side HAVING, not a
# per-row Python predicate) — keys match EXPLORER_STAGE_FILTERS above 1:1.
_EXPLORER_STAGE_DB_FILTERS = {
    "clicked": Q(clicks__gt=0),
    "landing": Q(landing_views__gt=0),
    "lead": Q(leads_count__gt=0),
    "account": Q(accounts__gt=0),
}


def explorer_page_size(tenant) -> int:
    """Cascade-resolved explorer page size (rail E-6, doc 16 ADR-044).

    Default 100 preserves pre-pagination behaviour for every seeded/demo dataset
    (well under 100 rows), so this is a zero-behaviour-change default.
    """
    from apps.config.cascade import resolve

    tid = getattr(tenant, "id", None)
    return int(resolve("dashboard_explorer_page_size", tenant_id=tid, default=100))


def _annotated_explorer_qs(tenant, *, source: str = "", search: str = ""):
    """The one query every explorer_rows()/explorer_row_count() call builds on —
    all funnel counts + referrer name come from annotations, never a per-row query."""
    not_synth_events = ~synthetic_ua_q(prefix="events__")
    qs = Referral.objects.select_related("referral_identity")
    if tenant is not None:
        qs = qs.for_tenant(tenant)
    if source:
        qs = qs.filter(source=source)
    if search:
        qs = qs.filter(referral_identity__client_id__icontains=search)
    qs = qs.annotate(
        client_id_val=Coalesce(F("referral_identity__client_id"), Value("")),
        referrer_name=_referrer_name_subquery(tenant),
        clicks=Count(
            "events",
            filter=Q(events__event_type="click", events__is_bot=False) & not_synth_events,
            distinct=True,
        ),
        landing_views=Count(
            "events", filter=Q(events__event_type="landing_viewed") & not_synth_events, distinct=True
        ),
        leads_count=Count("leads", filter=Q(leads__deleted_at__isnull=True), distinct=True),
        accounts=Count("conversions", filter=Q(conversions__is_reversed=False), distinct=True),
        last_activity=Max(
            "events__timestamp", filter=Q(events__is_bot=False) & not_synth_events
        ),
    ).annotate(
        client_id_lower=Lower("client_id_val"),
        referrer_name_lower=Lower("referrer_name"),
    )
    return qs


def explorer_rows(
    tenant=None,
    *,
    source: str = "",
    stage: str = "",
    search: str = "",
    sort: str = "last_activity",
    direction: str = "desc",
    page: int = 1,
):
    """Referral explorer rows — one row per referral link with its full funnel
    counts (clicks / landing opens / leads / accounts), filters (source / stage
    reached / search) and whitelisted column sorting (default: newest activity).

    Counts never overstate: clicks are non-bot, leads are REAL Lead rows (created
    only by a landing-page form submit), accounts are non-reversed Zoho conversions.
    Paginated server-side (`dashboard_explorer_page_size`, default 100) — this
    never materializes more than one page of rows.
    """
    qs = _annotated_explorer_qs(tenant, source=source, search=search)
    stage_filter = _EXPLORER_STAGE_DB_FILTERS.get(stage)
    if stage_filter is not None:
        qs = qs.filter(stage_filter)

    field = _EXPLORER_SORT_FIELD.get(sort, _EXPLORER_SORT_FIELD["last_activity"])
    reverse = direction != "asc"
    order = F(field).desc(nulls_last=True) if reverse else F(field).asc(nulls_last=True)
    qs = qs.order_by(order, "-id")

    page_size = explorer_page_size(tenant)
    offset = max(page, 1) - 1
    offset *= page_size
    rows = []
    for ref in qs[offset : offset + page_size]:
        rows.append({
            "id": ref.id,
            "client_id": ref.client_id_val,
            "referrer_name": ref.referrer_name,  # "" when unknown
            "source": ref.source,
            "clicks": ref.clicks,
            "landing_views": ref.landing_views,
            "leads": ref.leads_count,
            "accounts": ref.accounts,
            "last_activity": ref.last_activity,
            "is_partner_direct": ref.source == "partner_direct",
            "is_off_platform": ref.source == "zoho_import",
        })
    return rows


def explorer_row_count(tenant=None, *, source: str = "", stage: str = "", search: str = "") -> int:
    """Total matching rows for the current filters — drives the pagination controls."""
    qs = _annotated_explorer_qs(tenant, source=source, search=search)
    stage_filter = _EXPLORER_STAGE_DB_FILTERS.get(stage)
    if stage_filter is not None:
        qs = qs.filter(stage_filter)
    return qs.count()


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
