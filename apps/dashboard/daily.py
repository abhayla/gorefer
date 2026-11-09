"""S2-06 — daily referrals report: per-AP, per-IST-day funnel counts + one-day detail.

`tenant` is the SCOPE: a Tenant (an AP admin's binding, or a super-admin's chosen AP) or
None (super-admin, all APs). The view decides it from `apps.tenants.access`; nothing here
reads the request.

Counting rules (spec S2-06 Behaviour):
- clicks: event `click`, non-bot, non-synthetic (same rule as the explorer).
- landing opens: event `landing_viewed`, non-synthetic (same rule as the explorer).
- leads: non-deleted `Lead`, by created date.
- accounts: non-reversed `Conversion`, by the TRUE `account_opened_at` (ADR-017).
- active referrers: distinct referrer client ids with >=1 counted click in the period.
All dates are IST (settings.TIME_ZONE), never UTC `.date()`.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import DateField, Exists, OuterRef, Q
from django.db.models.functions import Trunc
from django.utils import timezone

from apps.events.bots import synthetic_ua_q
from apps.events.models import Event, VisitorPII
from apps.integrations.models import Conversion
from apps.referrals.models import Customer, Lead
from apps.tenants.models import Tenant
from gorefer.flags import SHARE_CHANNEL_LABELS

IST = ZoneInfo(settings.TIME_ZONE)

GROUPS = ("day", "week", "month")
SOURCES = (
    ("referral_link", "Referral link"),
    ("partner_direct", "Partner-direct"),
    ("zoho_import", "Off-platform"),
)
#: Channel filter values: the stored `Event.metadata["channel"]` labels + "none" (no tag).
#: Built from the one channel registry, so a newly configured channel is filterable at once.
CHANNELS = tuple((label, label) for label in SHARE_CHANNEL_LABELS.values()) + (("none", "None / direct"),)
STAGES = (
    ("clicked", "Link clicked"),
    ("landing", "Landing opened"),
    ("lead", "Lead captured"),
    ("account", "Account opened"),
)
_STAGE_RANK = {"clicked": 1, "landing": 2, "lead": 3, "account": 4}
_STAGE_COLUMN = {"clicked": "clicks", "landing": "landing", "lead": "leads", "account": "accounts"}
SORT_KEYS = ("period", "ap", "clicks", "landing", "leads", "accounts", "active_referrers", "lead_rate")

#: Default preset list + default range (rail E-6: each resolves from the cascade).
DEFAULT_PRESETS = ["today", "last7", "last30", "this_month"]
PRESET_LABELS = {"today": "Today", "last7": "Last 7 days", "last30": "Last 30 days",
                 "this_month": "This month"}


def _cfg(tenant, key, default):
    from apps.config.cascade import resolve

    return resolve(key, tenant_id=getattr(tenant, "id", None), default=default)


def page_size(tenant) -> int:
    return int(_cfg(tenant, "daily_report_page_size", 100))


def presets(tenant) -> list[str]:
    return [p for p in _cfg(tenant, "daily_report_presets", DEFAULT_PRESETS) if p in PRESET_LABELS]


def default_preset(tenant) -> str:
    return _cfg(tenant, "daily_report_default_preset", "last7")


def today_ist() -> dt.date:
    return timezone.now().astimezone(IST).date()


def preset_range(preset: str, today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    today = today or today_ist()
    if preset == "today":
        return today, today
    if preset == "last30":
        return today - dt.timedelta(days=29), today
    if preset == "this_month":
        return today.replace(day=1), today
    return today - dt.timedelta(days=6), today  # last7 (and any unknown preset)


def _bounds(start: dt.date, end: dt.date):
    lo = dt.datetime(start.year, start.month, start.day, tzinfo=IST)
    hi = dt.datetime(end.year, end.month, end.day, tzinfo=IST) + dt.timedelta(days=1)
    return lo, hi


def _period(field: str, group: str):
    return Trunc(field, group, output_field=DateField(), tzinfo=IST)


def _period_start(day: dt.date, group: str) -> dt.date:
    if group == "week":
        return day - dt.timedelta(days=day.weekday())  # Postgres week = Monday
    if group == "month":
        return day.replace(day=1)
    return day


def _periods(start: dt.date, end: dt.date, group: str) -> list[dt.date]:
    out, day = [], start
    while day <= end:
        p = _period_start(day, group)
        if not out or out[-1] != p:
            out.append(p)
        day += dt.timedelta(days=1)
    return out


def _scoped(qs, tenant):
    return qs.for_tenant(tenant) if tenant is not None else qs


def _referrer_ids_matching(tenant, text: str) -> list[str]:
    """Client ids whose referrer NAME contains `text` (Customer is the name source)."""
    qs = _scoped(Customer.objects.all(), tenant)
    words = text.split()
    for w in words:
        qs = qs.filter(Q(first_name__icontains=w) | Q(last_name__icontains=w))
    return list(qs.values_list("client_id", flat=True)) if words else []


def _channel_q(channel: str, prefix: str = "") -> Q:
    if channel == "none":
        return ~Q(**{f"{prefix}metadata__has_key": "channel"}) | Q(**{f"{prefix}metadata__channel": ""})
    return Q(**{f"{prefix}metadata__channel": channel})


def _referral_clicked_on(channel: str, lo, hi):
    """Leads/accounts carry no channel: attribute them to a referral link with >=1 counted
    click on that channel INSIDE the selected period (the link, not the person, is tagged)."""
    return Exists(
        Event.objects.filter(
            referral=OuterRef("referral"), event_type="click", is_bot=False,
            timestamp__gte=lo, timestamp__lt=hi,
        ).exclude(synthetic_ua_q()).filter(_channel_q(channel))
    )


def _filtered(kind: str, tenant, *, lo, hi, referrer="", source="", channel=""):
    """The base queryset of one counted population over [lo, hi), all filters applied."""
    if kind in ("click", "landing"):
        qs = Event.objects.filter(
            event_type="click" if kind == "click" else "landing_viewed",
            timestamp__gte=lo, timestamp__lt=hi,
        ).exclude(synthetic_ua_q())
        if kind == "click":
            qs = qs.filter(is_bot=False)
        cid = "referral__referral_identity__client_id"
    elif kind == "lead":
        qs = Lead.objects.filter(deleted_at__isnull=True, created_at__gte=lo, created_at__lt=hi)
        cid = "referral__referral_identity__client_id"
    else:
        qs = Conversion.objects.filter(
            is_reversed=False, account_opened_at__gte=lo, account_opened_at__lt=hi
        )
        cid = "referrer_client_id"
    qs = _scoped(qs, tenant)
    if source:
        q = Q(referral__source=source)
        if kind == "account" and source == "zoho_import":
            q |= Q(referral__isnull=True)  # an off-platform conversion may have no link row
        qs = qs.filter(q)
    if referrer:
        names = _referrer_ids_matching(tenant, referrer)
        qs = qs.filter(Q(**{f"{cid}__icontains": referrer}) | Q(**{f"{cid}__in": names}))
    if channel:
        qs = qs.filter(_channel_q(channel)) if kind in ("click", "landing") else qs.filter(
            _referral_clicked_on(channel, lo, hi)
        )
    return qs, cid


_DATE_FIELD = {"click": "timestamp", "landing": "timestamp", "lead": "created_at",
               "account": "account_opened_at"}
_COLUMN = {"click": "clicks", "landing": "landing", "lead": "leads", "account": "accounts"}


def report(
    tenant=None, *, start: dt.date, end: dt.date, group: str = "day", split_by_ap: bool = False,
    referrer: str = "", source: str = "", channel: str = "", stage: str = "", min_leads: int = 0,
    sort: str = "period", direction: str = "desc",
) -> dict:
    """{"rows": [...], "total": {...}} — every row and the total use the SAME filters."""
    # shortcut: computed from raw rows, fine at today's ~1-2k events; switch to DailyMetric rollups when events pass ~1M  # noqa: E501
    group = group if group in GROUPS else "day"
    lo, hi = _bounds(start, end)
    flt = {"referrer": referrer.strip(), "source": source, "channel": channel}

    def key(p, tid):
        return (p, tid if split_by_ap else None)

    tenants = {t.id: t.name for t in _scoped(Tenant.objects.all(), tenant) if True} if tenant is None \
        else {tenant.id: tenant.name}
    rows: dict = {}
    keys_tenants = list(tenants) if split_by_ap else [None]
    for p in _periods(start, end, group):
        for tid in keys_tenants:
            rows[(p, tid)] = {"period": p, "tenant_id": tid, "ap": tenants.get(tid, ""),
                              "clicks": 0, "landing": 0, "leads": 0, "accounts": 0, "_refs": set()}

    for kind in ("click", "landing", "lead", "account"):
        qs, cid = _filtered(kind, tenant, lo=lo, hi=hi, **flt)
        vals = qs.annotate(p=_period(_DATE_FIELD[kind], group)).values_list("p", "tenant_id", cid)
        for p, tid, client_id in vals:
            row = rows.get(key(p, tid))
            if row is None:  # a tenant outside the scope list can never be added
                continue
            row[_COLUMN[kind]] += 1
            if kind == "click" and client_id:
                row["_refs"].add(client_id)

    out = []
    for row in rows.values():
        if row["leads"] < min_leads:
            continue
        if stage in _STAGE_COLUMN and row[_STAGE_COLUMN[stage]] <= 0:
            continue
        out.append(row)
    all_refs = set().union(*(r["_refs"] for r in out)) if out else set()
    for row in out:
        row["active_referrers"] = len(row.pop("_refs"))
        row["lead_rate"] = _rate(row["leads"], row["clicks"])
    total = {c: sum(r[c] for r in out) for c in ("clicks", "landing", "leads", "accounts")}
    total["active_referrers"] = len(all_refs)  # distinct over the whole range, not a sum
    total["lead_rate"] = _rate(total["leads"], total["clicks"])

    sort = sort if sort in SORT_KEYS else "period"
    # Period then AP as the stable tiebreak; a None lead rate (no clicks) always sorts last.
    out.sort(key=lambda r: (r["period"], r["ap"]), reverse=direction != "asc")
    out.sort(key=lambda r: r[sort] if r[sort] is not None else 0, reverse=direction != "asc")
    out.sort(key=lambda r: r[sort] is None)
    return {"rows": out, "total": total, "group": group}


def _rate(leads: int, clicks: int):
    return round(leads / clicks * 100, 1) if clicks else None


def _names(tenant, client_ids) -> dict[str, str]:
    qs = _scoped(Customer.objects.filter(client_id__in=set(client_ids)), tenant).exclude(first_name="")
    out: dict[str, str] = {}
    for c in qs.order_by("id"):
        out.setdefault(c.client_id, f"{c.first_name} {c.last_name}".strip())
    return out


def day_detail(tenant=None, *, day: dt.date, referrer="", source="", channel="", stage="") -> dict:
    """People who became a lead or had an account opened on `day` (IST), plus that day's
    counted clicks. A person appears on EVERY day they did something."""
    lo, hi = _bounds(day, day)
    flt = {"referrer": referrer.strip(), "source": source, "channel": channel}

    leads_qs, _ = _filtered("lead", tenant, lo=lo, hi=hi, **flt)
    leads = list(leads_qs.select_related("prospect", "referral__referral_identity", "tenant"))
    convs_qs, _ = _filtered("account", tenant, lo=lo, hi=hi, **flt)
    convs = list(convs_qs.select_related("referral", "tenant"))

    # Which leads (of any day) ended in a non-reversed account: matched on the Zoho lead id.
    lead_by_zoho = {}
    zids = [c.zoho_lead_id for c in convs if c.zoho_lead_id]
    if zids:
        for lead in _scoped(Lead.objects.filter(zoho_lead_id__in=zids), tenant).select_related(
            "prospect", "referral__referral_identity"
        ):
            lead_by_zoho[lead.zoho_lead_id] = lead
    converted = set(
        _scoped(Conversion.objects.filter(is_reversed=False), tenant)
        .filter(zoho_lead_id__in=[ld.zoho_lead_id for ld in leads if ld.zoho_lead_id])
        .values_list("zoho_lead_id", flat=True)
    )

    people: dict = {}
    for ld in leads:
        ident = ld.referral.referral_identity if ld.referral_id else None
        people[("lead", ld.pk)] = {
            "t": ld.created_at, "ap": ld.tenant.name if ld.tenant_id else "",
            "client_id": ident.client_id if ident else "",
            "name": ld.prospect.name, "mobile": ld.prospect.mobile, "city": ld.prospect.city,
            "source": ld.referral.source, "happened": ["Lead"],
            # The account stage comes ONLY from a non-reversed Conversion (Zoho), never a Lead field.
            "stage": "account" if ld.zoho_lead_id in converted else "lead",
            "zoho_status": ld.status, "referral_id": ld.referral_id,
        }
    for c in convs:
        ld = lead_by_zoho.get(c.zoho_lead_id) if c.zoho_lead_id else None
        k = ("lead", ld.pk) if ld is not None else ("conv", c.pk)
        if k in people:  # lead and account on the same day: one person, two things
            people[k]["happened"].append("Account opened")
            people[k]["stage"], people[k]["zoho_status"] = "account", c.status
            continue
        people[k] = {
            "t": c.account_opened_at, "ap": c.tenant.name if c.tenant_id else "",
            "client_id": c.referrer_client_id,
            "name": (ld.prospect.name if ld else "") or c.opener_name,
            "mobile": ld.prospect.mobile if ld else "", "city": ld.prospect.city if ld else "",
            "source": c.referral.source if c.referral_id else "zoho_import",
            "happened": ["Account opened"], "stage": "account", "zoho_status": c.status,
            "referral_id": c.referral_id,
        }
    # Stage filter = "reached at least": every offered stage is honoured, none ignored.
    want = _STAGE_RANK.get(stage, 0)
    rows = [r for r in sorted(people.values(), key=lambda r: r["t"]) if _STAGE_RANK[r["stage"]] >= want]
    names = _names(tenant, [r["client_id"] for r in rows])
    for r in rows:
        r["referrer_name"] = names.get(r["client_id"], "")
        r["happened"] = " + ".join(r["happened"])
        r["t"] = r["t"].astimezone(IST)

    clicks_qs, _ = _filtered("click", tenant, lo=lo, hi=hi, **flt)
    clicks = list(clicks_qs.select_related("referral__referral_identity", "tenant").order_by("timestamp"))
    # RDR-6: exact "clicks with no form" only when every browser-form lead that day has its
    # visitor id on a lead event; otherwise (pre-RDR-6 days) all clicks, with a note.
    lead_events = _scoped(Event.objects.filter(event_type="lead_captured"), tenant)
    linked = set(
        lead_events.filter(timestamp__gte=lo, timestamp__lt=hi, visitor_id__isnull=False)
        .exclude(visitor_id="").values_list("referral_id", "person_ref_id")
    )
    day_leads = _scoped(Lead.objects.filter(deleted_at__isnull=True, created_at__gte=lo,
                                            created_at__lt=hi, lead_source="landing"), tenant)
    exact = all((r, p) in linked for r, p in day_leads.values_list("referral_id", "prospect_id"))
    if exact:
        formed = set(lead_events.filter(visitor_id__isnull=False).exclude(visitor_id="")
                     .values_list("visitor_id", flat=True))
        clicks = [e for e in clicks if not e.visitor_id or e.visitor_id not in formed]
    if want > _STAGE_RANK["clicked"]:
        clicks = []  # a click row never reaches a later stage
    vids = {e.visitor_id for e in clicks if e.visitor_id}
    city = {}
    if vids:
        for v in _scoped(VisitorPII.objects.filter(visitor_id__in=vids, erased_at__isnull=True), tenant):
            city.setdefault(v.visitor_id, v.city)
    from .profile import _device_and_ua

    cnames = _names(tenant, [e.referral.referral_identity.client_id for e in clicks
                             if e.referral_id and e.referral.referral_identity_id])
    click_rows = []
    for e in clicks:
        ident = e.referral.referral_identity if e.referral_id else None
        cid = ident.client_id if ident else ""
        click_rows.append({
            "t": e.timestamp.astimezone(IST), "ap": e.tenant.name if e.tenant_id else "",
            "client_id": cid, "referrer_name": cnames.get(cid, ""),
            "channel": (e.metadata or {}).get("channel") or "Direct",
            "city": city.get(e.visitor_id, "") or "", "device": _device_and_ua(e.user_agent)[0],
        })
    return {"people": rows, "clicks": click_rows, "clicks_exact": exact}
