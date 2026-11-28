"""The role-based daily report (owner-approved mock-up 2026-11-28, /admin-panel/report).

One page, three formats, each built from that role's OWN queries (never by hiding parts
of a wider view, so a manager's page can't leak another business):

  * owner   — "Platform and growth": month-to-date growth vs last month, businesses,
              where accounts came from (credited referrer or not — Zoho never says which
              link a person tapped), platform facts. Default period: this month.
  * admin   — "Operations": WhatsApp messages by business, businesses vs their usual,
              follow-ups. Default period: yesterday.
  * manager — "<Business> today": people to contact, every Kite ID, the business's
              links, the Kite ID box. Default period: yesterday.

Counting rules are digest_links': IST days, tenant-scoped (rail E-7), bots and synthetic
traffic removed, accounts only from Zoho by their true opening date (ADR-017). Every
threshold is a cascade key (REPORT_SETTINGS_DEFAULTS). Messages come from Zoho's send
queue, one call per day, so they are shown for single-day periods only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.campaigns import digest_links
from apps.campaigns.digest import IST_OFFSET, zoho_queue_summary
from apps.config.cascade import resolve
from apps.config.preferences import REPORT_SETTINGS_DEFAULTS
from apps.events import vocab
from apps.events.bots import exclude_synthetic
from apps.events.models import Event
from apps.tenants.access import ADMIN, MANAGER, OWNER

RANGES = ("today", "yesterday", "7d", "mtd")
RANGE_LABELS = {"today": "Today (live)", "yesterday": "Yesterday", "7d": "7 days", "mtd": "This month"}


def report_setting(key: str, tenant_id=None):
    default = REPORT_SETTINGS_DEFAULTS[key]
    try:
        value = resolve(key, tenant_id=tenant_id, default=default)
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def ist_today() -> date:
    return (timezone.now() + IST_OFFSET).date()


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date  # inclusive

    @property
    def single_day(self) -> bool:
        return self.start == self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def label(self) -> str:
        fmt = lambda d: d.strftime("%a %-d %b %Y")  # noqa: E731
        if self.key == "today":
            return f"Today, {fmt(self.start)}"
        if self.key == "yesterday":
            return f"Yesterday, {fmt(self.start)}"
        if self.single_day:
            return fmt(self.start)
        return f"{self.start.strftime('%-d %b')} – {self.end.strftime('%-d %b %Y')}"


def make_period(key: str, picked: str = "", today: date | None = None) -> Period:
    today = today or ist_today()
    if picked:
        try:
            d = date.fromisoformat(picked)
        except ValueError:
            d = None
        if d is not None and d <= today:
            return Period(
                "today" if d == today else ("yesterday" if d == today - timedelta(1) else "day"), d, d
            )
    if key == "yesterday":
        y = today - timedelta(days=1)
        return Period("yesterday", y, y)
    if key == "7d":
        return Period("7d", today - timedelta(days=7), today - timedelta(days=1))
    if key == "mtd":
        return Period("mtd", today.replace(day=1), today)
    return Period("today", today, today)


def _usual(tenant, period: Period, fn) -> float:
    """Average of `fn(start, end)` over the 7 equal-length periods before this one."""
    vals = []
    for back in range(1, 8):
        shift = timedelta(days=period.days * back)
        vals.append(fn(period.start - shift, period.end - shift))
    return sum(vals) / len(vals)


def _whole(x: float) -> str:
    return str(int(round(x)))


def _pct_change(now: float, before: float) -> str:
    if before <= 0:
        return "new" if now > 0 else "no change"
    pct = round((now - before) / before * 100)
    return f"↑ {pct}%" if pct > 0 else (f"↓ {abs(pct)}%" if pct < 0 else "no change")


# --------------------------------------------------------------------------- per-ID data


def _referral_identity_events(tenant, start, end):
    return exclude_synthetic(
        Event.objects.for_tenant(tenant).filter(
            is_bot=False,
            timestamp__gte=start,
            timestamp__lt=end,
            referral__referral_identity__isnull=False,
        )
    )


def kite_id_rows(tenant, period: Period) -> list[dict]:
    """Every Kite ID with activity or a Zoho credit in the period, for the manager table."""
    from apps.integrations.models import Conversion
    from apps.referrals.models import Referral

    start, end = digest_links._bounds(period.start, period.end)
    field = "referral__referral_identity__client_id"
    ev = _referral_identity_events(tenant, start, end)
    taps = dict(ev.filter(event_type=vocab.CLICK).values_list(field).annotate(n=Count("id")))
    shares = dict(ev.filter(event_type=vocab.SHARE_INTENT).values_list(field).annotate(n=Count("id")))
    typed = {}
    for e in exclude_synthetic(
        Event.objects.for_tenant(tenant).filter(
            is_bot=False,
            timestamp__gte=start,
            timestamp__lt=end,
            event_type=vocab.KITE_PROMPT_ACTION,
            metadata__action=vocab.PROMPT_ACTION_ENTERED,
        )
    ).only("metadata"):
        cid = (e.metadata or {}).get("client_id")
        if cid:
            typed[cid] = typed.get(cid, 0) + 1
    accounts = dict(
        Conversion.objects.for_tenant(tenant)
        .filter(
            is_reversed=False,
            account_opened_at__gte=start,
            account_opened_at__lt=end,
        )
        .exclude(referrer_client_id="")
        .values_list("referrer_client_id")
        .annotate(n=Count("id"))
    )
    new_ids = set(
        Referral.objects.for_tenant(tenant)
        .filter(
            referral_identity__isnull=False,
            first_click_at__gte=start,
            first_click_at__lt=end,
        )
        .values_list("referral_identity__client_id", flat=True)
    )
    ids = set(taps) | set(shares) | set(typed) | set(accounts)
    last = (
        dict(
            exclude_synthetic(
                Event.objects.for_tenant(tenant).filter(
                    is_bot=False, referral__referral_identity__client_id__in=ids
                )
            )
            .values_list(field)
            .annotate(t=Max("timestamp"))
        )
        if ids
        else {}
    )
    top = max(accounts.items(), key=lambda kv: (kv[1], kv[0]))[0] if accounts else None
    rows = []
    for cid in ids:
        note = (
            "Top referrer"
            if cid == top
            else (
                "New referrer"
                if cid in new_ids
                else ("Shared, no taps" if shares.get(cid) and not taps.get(cid) else "")
            )
        )
        rows.append(
            {
                "id": cid,
                "accounts": accounts.get(cid, 0),
                "taps": taps.get(cid, 0),
                "shares": shares.get(cid, 0),
                "typed": typed.get(cid, 0),
                "last": last.get(cid),
                "note": note,
                "is_new": cid in new_ids,
            }
        )
    rows.sort(key=lambda r: (-r["accounts"], -r["taps"], -r["shares"], r["id"]))
    return rows


# --------------------------------------------------------------------------- to-do rules


def manager_todos(tenant, period: Period, counts: dict, rows: list[dict]) -> list[dict]:
    tid = getattr(tenant, "id", None)
    todos = []
    for r in rows:
        if r["accounts"]:
            todos.append(
                {
                    "what": f"Thank {r['id']}",
                    "tag": "Call or WhatsApp",
                    "why": f"Zoho credited {r['accounts']} new account"
                    f"{'s' if r['accounts'] > 1 else ''} to them.",
                }
            )
    for r in rows:
        if r["is_new"]:
            todos.append(
                {
                    "what": f"Welcome {r['id']}",
                    "tag": "Call or WhatsApp",
                    "why": "New referrer: their first link tap. Send them the share hub.",
                }
            )
    hours = report_setting("report_shared_no_taps_hours", tid)
    min_shares = report_setting("report_shared_no_taps_min_shares", tid)
    now = timezone.now()
    ev = _referral_identity_events(tenant, now - timedelta(hours=hours), now)
    field = "referral__referral_identity__client_id"
    shares = dict(ev.filter(event_type=vocab.SHARE_INTENT).values_list(field).annotate(n=Count("id")))
    tapped = set(ev.filter(event_type=vocab.CLICK).values_list(field, flat=True))
    for cid, n in sorted(shares.items()):
        if n >= min_shares and cid not in tapped:
            todos.append(
                {
                    "what": f"Help {cid}",
                    "tag": "Call or WhatsApp",
                    "why": f"Shared {n} times in {hours} hours; no friend has tapped yet.",
                }
            )
    quiet = report_setting("report_quiet_days", tid)
    q_start = now - timedelta(days=quiet)
    before = _referral_identity_events(tenant, q_start - timedelta(days=28), q_start)
    active_before = set(before.values_list(field, flat=True).annotate(n=Count("id")).filter(n__gte=2))
    active_recent = set(_referral_identity_events(tenant, q_start, now).values_list(field, flat=True))
    for cid in sorted(active_before - active_recent)[:3]:
        todos.append(
            {
                "what": f"Re-engage {cid}",
                "tag": "Call or WhatsApp",
                "why": f"No activity for {quiet} days; they were active in the 4 weeks before.",
            }
        )
    wrong = counts["share_prompt"]["wrong"]
    if wrong >= report_setting("report_wrong_ids_min", tid):
        todos.append(
            {
                "what": "Remind referrers what a Kite ID looks like",
                "tag": "Message",
                "why": f"{wrong} wrong IDs were typed in the share box. The ID looks like AB1234.",
            }
        )
    return todos[: report_setting("report_todo_max", tid)]


def admin_todos(msgs_by_business: list[dict], tid=None) -> list[dict]:
    todos = []
    for m in msgs_by_business:
        z = m.get("zoho")
        if not z or not z["referral_total"]:
            continue
        q = z["referral_total"]
        if z["failed"] >= report_setting("report_failed_min", tid) or z["failed"] * 100 > q * report_setting(
            "report_failed_pct", tid
        ):
            todos.append(
                {
                    "what": f"{m['name']}: {z['failed']} messages failed",
                    "tag": "Fix today",
                    "why": "Open the Zoho send queue and check the failed rows.",
                }
            )
        if z["pending"]:
            todos.append(
                {
                    "what": f"{m['name']}: {z['pending']} message{'s' if z['pending'] > 1 else ''} waiting",
                    "tag": "Fix today",
                    "why": "Re-run the send for those rows if they are older than 2 hours.",
                }
            )
        if z["invalid"]:
            todos.append(
                {
                    "what": f"{m['name']}: {z['invalid']} wrong number{'s' if z['invalid'] > 1 else ''}",
                    "tag": "Fix today",
                    "why": "Correct the number in Zoho.",
                }
            )
        if z["capped"] * 100 > q * report_setting("report_meta_limit_pct", tid):
            todos.append(
                {
                    "what": f"Meta limit: {z['capped']} messages",
                    "tag": "Watch",
                    "why": "Tell the owner if this repeats tomorrow.",
                }
            )
    return todos[: report_setting("report_todo_max", tid)]


def owner_todos(
    msgs_by_business: list[dict], no_business_taps: int, businesses: list[dict], tid=None
) -> list[dict]:
    todos = []
    for m in msgs_by_business:
        z = m.get("zoho")
        if (
            z
            and z["referral_total"]
            and z["rate_pct"] is not None
            and z["rate_pct"] < report_setting("report_sent_rate_min_pct", tid)
        ):
            todos.append(
                {
                    "what": f"{m['name']}: only {z['rate_pct']:.0f}% of messages sent",
                    "tag": "Decision",
                    "why": f"{z['capped']} hit Meta's marketing limit. "
                    "Consider moving that template to UTILITY.",
                }
            )
    if no_business_taps >= report_setting("report_no_business_taps_min", tid):
        todos.append(
            {
                "what": f"{no_business_taps} taps on links of no business",
                "tag": "Tidy-up",
                "why": "Assign those links to a business or retire them.",
            }
        )
    for b in businesses:
        if b["accounts_7d"] == 0 and b["accounts_usual_7d"] > 0:
            todos.append(
                {
                    "what": f"{b['name']}: no accounts for 7 days",
                    "tag": "Decision",
                    "why": "Talk to that business's manager.",
                }
            )
    return todos[: report_setting("report_todo_max", tid)]


# --------------------------------------------------------------------------- builders


def _accounts(tenant, start: date, end: date) -> int:
    return digest_links._accounts_opened(tenant, start, end)["total"]


def _messages(tenant, period: Period):
    """Zoho send-queue figures for one day. The queue is the installation's ONE Zoho
    account, which belongs to the bootstrap business (PIFS): any other business gets
    None, never PIFS's numbers (a cross-business leak otherwise)."""
    from apps.tenants.resolve import get_bootstrap_tenant

    if not period.single_day:
        return None
    owner_of_zoho = get_bootstrap_tenant()
    if owner_of_zoho is None or getattr(tenant, "id", None) != owner_of_zoho.id:
        return None
    try:
        return zoho_queue_summary(tenant, period.start)
    except Exception:
        return None


def build_manager(tenant, period: Period) -> dict:
    c = digest_links.link_counts(tenant, period.start, period.end)
    usual = {
        "accounts": _usual(tenant, period, lambda s, e: _accounts(tenant, s, e)),
        "referral": _usual(
            tenant, period, lambda s, e: digest_links.link_counts(tenant, s, e)["referral_link"]
        ),
    }
    rows = kite_id_rows(tenant, period)
    link_rows = [
        ("/zerodha/r/{ID}", "Referral link (any channel)", c["referral_link"], "PIFS + referrer", True),
        (
            "/zerodha/share/wa/{ID}",
            "Referrer shares on WhatsApp",
            c["share_with_id"] + c["share_without_id"],
            "Sharing step",
            True,
        ),
        ("/zerodha/open", "PIFS open link and tagged posts", c["open_link"], "PIFS only", True),
        ("/zerodha/open/wa", "Friends via shared message", c["step2"], "PIFS only", True),
        ("/d/pifs", "Disclosure page", c["disclosure"], "Information page", True),
        ("broken links", "Mistyped links sent to /zerodha/open", c["fallback"], "PIFS only", False),
    ]
    return {
        "tiles": [
            {
                "label": "Accounts opened (Zoho)",
                "value": c["accounts"]["total"],
                "note": f"Usual {_whole(usual['accounts'])}"
                + (f" · top {c['accounts']['top'][0]}" if c["accounts"]["top"] else ""),
            },
            {
                "label": "Referral link taps",
                "value": c["referral_link"],
                "note": f"Usual {_whole(usual['referral'])}",
            },
            {"label": "Referrers active", "value": len(rows), "note": f"{c['new_referrers']} new"},
            {
                "label": "Shares by referrers",
                "value": c["share_with_id"] + c["share_without_id"],
                "note": f"{c['share_without_id']} without ID",
            },
        ],
        "todos": manager_todos(tenant, period, c, rows),
        "ids": rows,
        "links": [
            {"path": p, "what": w, "taps": n, "credit": cr, "opening": op} for p, w, n, cr, op in link_rows
        ],
        "box": c,
        "messages": _messages(tenant, period),
    }


def build_admin(tenants, period: Period) -> dict:
    msgs, rows = [], []
    for t in tenants:
        z = _messages(t, period)
        msgs.append({"name": t.name, "zoho": z})
        c = digest_links.link_counts(t, period.start, period.end)
        acc_usual = _usual(t, period, lambda s, e, t=t: _accounts(t, s, e))
        ref_usual = _usual(t, period, lambda s, e, t=t: digest_links.link_counts(t, s, e)["referral_link"])
        below = ref_usual >= report_setting("report_usual_min", t.id) and c[
            "referral_link"
        ] * 100 <= ref_usual * (100 - report_setting("report_below_usual_pct", t.id))
        rows.append(
            {
                "name": t.name,
                "accounts": c["accounts"]["total"],
                "accounts_usual": _whole(acc_usual),
                "taps": c["referral_link"],
                "taps_usual": _whole(ref_usual),
                "status": "Below usual" if below else "Normal",
                "box": c["share_prompt"],
                "friends_box": c["referral_prompt"],
            }
        )
    return {
        "todos": admin_todos(msgs),
        "messages": msgs,
        "businesses": rows,
        "followups": _followups(tenants, period),
    }


def _followups(tenants, period: Period) -> dict:
    from apps.followups.models import ScheduledFollowup

    start, end = digest_links._bounds(period.start, period.end)
    by: dict = {}
    for t in tenants:
        qs = ScheduledFollowup.objects.for_tenant(t).filter(fire_at__gte=start, fire_at__lt=end)
        for status, n in qs.values_list("status").annotate(n=Count("id")):
            by[status] = by.get(status, 0) + n
    return {
        "due": sum(by.values()),
        "sent": by.get("sent", 0),
        "skipped": by.get("skipped", 0) + by.get("cancelled", 0),
        "failed": by.get("failed", 0),
    }


def build_owner(tenants, period: Period) -> dict:
    from apps.integrations.models import Conversion
    from apps.tenants.models import StaffAccess

    today = ist_today()
    mstart = today.replace(day=1)
    prev_end = mstart - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    same_point = min(prev_start + (today - mstart), prev_end)
    businesses, total_now, total_before = [], 0, 0
    for t in tenants:
        now_n, before_n = _accounts(t, mstart, today), _accounts(t, prev_start, same_point)
        total_now, total_before = total_now + now_n, total_before + before_n
        s30, e30 = digest_links._bounds(today - timedelta(days=29), today)
        active = (
            _referral_identity_events(t, s30, e30).values("referral__referral_identity").distinct().count()
        )
        acc7 = _accounts(t, today - timedelta(days=7), today - timedelta(days=1))
        acc7_usual = _accounts(t, today - timedelta(days=35), today - timedelta(days=8)) / 4
        businesses.append(
            {
                "name": t.name,
                "accounts": now_n,
                "vs": _pct_change(now_n, before_n),
                "active_30d": active,
                "accounts_7d": acc7,
                "accounts_usual_7d": acc7_usual,
                "messages": _messages(t, Period("yesterday", today - timedelta(1), today - timedelta(1))),
            }
        )
    businesses.sort(key=lambda b: -b["accounts"])
    s, e = digest_links._bounds(mstart, today)
    with_ref = without = 0
    for t in tenants:
        conv = Conversion.objects.for_tenant(t).filter(
            is_reversed=False, account_opened_at__gte=s, account_opened_at__lt=e
        )
        n_ref = conv.exclude(referrer_client_id="").count()
        with_ref, without = with_ref + n_ref, without + conv.count() - n_ref
    spark = [
        sum(_accounts(t, today - timedelta(days=i), today - timedelta(days=i)) for t in tenants)
        for i in range(9, -1, -1)
    ]
    p_start, p_end = digest_links._bounds(period.start, period.end)
    no_business = exclude_synthetic(
        Event.objects.for_tenant(None).filter(
            is_bot=False, event_type=vocab.CLICK, timestamp__gte=p_start, timestamp__lt=p_end
        )
    ).count()
    msgs = [{"name": b["name"], "zoho": b["messages"]} for b in businesses]
    return {
        "tiles": [
            {
                "label": "Accounts opened this month (Zoho)",
                "value": total_now,
                "note": f"{_pct_change(total_now, total_before)} vs last month "
                f"at this point ({total_before})",
            },
            {
                "label": "Active referrers (30 days)",
                "value": sum(b["active_30d"] for b in businesses),
                "note": "Kite IDs with any activity",
            },
            {
                "label": "Accounts with a credited referrer",
                "value": with_ref,
                "note": f"{without} with no referrer",
            },
        ],
        "spark": spark,
        "businesses": businesses,
        "origin": {"with_ref": with_ref, "without": without},
        "platform": {
            "people": StaffAccess.objects.filter(revoked_at__isnull=True).count(),
            "no_business_taps": no_business,
        },
        "todos": owner_todos(msgs, no_business, businesses),
    }


def role_choices(grants) -> list[dict]:
    labels = {OWNER: "Owner", ADMIN: "Admin"}
    out = []
    for g in grants:
        out.append({"key": g.role, "label": labels.get(g.role) or f"{g.tenant.name} manager", "grant": g})
    return out


def default_range(role: str, tid=None) -> str:
    key = {
        OWNER: "report_default_range_owner",
        ADMIN: "report_default_range_admin",
        MANAGER: "report_default_range_manager",
    }[role]
    value = report_setting(key, tid)
    return value if value in RANGES else "yesterday"


__all__ = [
    "RANGES",
    "RANGE_LABELS",
    "Period",
    "make_period",
    "build_owner",
    "build_admin",
    "build_manager",
    "role_choices",
    "default_range",
    "report_setting",
    "Q",
]
