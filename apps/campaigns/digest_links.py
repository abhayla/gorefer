"""Link counts for the daily digest, layout v2 (T-link-tracking, owner 2026-11-27).

The owner asked the daily WhatsApp report to show how the links PIFS shares for account
opening were used yesterday, plus which Kite IDs were behind them:

  * the open link            /zerodha/open (and its tagged posts, e.g. /open/yt/hi)
  * one-tap Step 2           /zerodha/open/wa — friends tapping Step 2 of a forwarded
                             one-tap message (counted apart from PIFS's own /open)
  * the referral link        /zerodha/r/[{channel}/]{ID} — every click carrying an ID
  * the share link           /zerodha/share/wa/{ID} — with an ID / without one
  * the disclosure page      /d/{slug}
  * both Kite ID pop-ups     views (and distinct visitors), ID entered, skip, wrong ID

Counting rules (shared with v1, never weakened):
  * one IST calendar day, UTC-bounded by `_ist_day_bounds_utc`;
  * tenant-scoped through `for_tenant()` (rail E-7);
  * bots excluded (`is_bot=False`: preview user agents write nothing at all, datacenter
    addresses are flagged) and synthetic traffic excluded (`exclude_synthetic`);
  * accounts come ONLY from Zoho-sourced `Conversion` rows, dated by the TRUE opening
    date `account_opened_at` (ADR-017), never inferred from clicks (ADR-013/016).

Every number here is a COUNT of recorded events. Clicks and visitors are approximate
(cookies, in-app browsers) and are labelled so in the template.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from django.db.models import Count, Q

from apps.events import vocab
from apps.events.bots import exclude_synthetic
from apps.events.models import Event

STEP2_CHANNEL_LABEL = "WhatsApp"  # /open/wa -> metadata["channel"] (gorefer.flags labels)


def _bounds(day: date, until: date | None = None):
    """UTC [start, end) of IST `day`, or of `day`..`until` inclusive (a period)."""
    from .digest import _ist_day_bounds_utc

    start, end = _ist_day_bounds_utc(day)
    if until is not None and until > day:
        end = _ist_day_bounds_utc(until)[1]
    return start, end


def _human_events(tenant, day: date, until: date | None = None):
    start, end = _bounds(day, until)
    return exclude_synthetic(
        Event.objects.for_tenant(tenant).filter(is_bot=False, timestamp__gte=start, timestamp__lt=end)
    )


def _id_counts(qs, field: str) -> list[tuple[str, int]]:
    """[(client_id, n), ...] most-used first, ties by id (stable output)."""
    rows = qs.exclude(**{f"{field}__isnull": True}).values(field).annotate(n=Count("id"))
    return sorted(((r[field], r["n"]) for r in rows if r[field]), key=lambda t: (-t[1], t[0]))


def _prompt_counts(base, mode: str) -> dict:
    views = base.filter(event_type=vocab.SHARE_RECOVERY_VIEWED, metadata__prompt=mode)
    actions = base.filter(event_type=vocab.KITE_PROMPT_ACTION, metadata__prompt=mode)
    return {
        "shown": views.count(),
        "visitors": views.exclude(visitor_id__isnull=True).exclude(visitor_id="")
        .values("visitor_id").distinct().count(),
        "entered": actions.filter(metadata__action=vocab.PROMPT_ACTION_ENTERED).count(),
        "skipped": actions.filter(metadata__action=vocab.PROMPT_ACTION_SKIP).count(),
        "wrong": actions.filter(metadata__action=vocab.PROMPT_ACTION_WRONG).count(),
    }


def link_counts(tenant, day: date, until: date | None = None) -> dict:
    """Every v2 link figure for one IST day, or the period `day`..`until` inclusive."""
    base = _human_events(tenant, day, until)
    clicks = base.filter(event_type=vocab.CLICK)
    open_clicks = clicks.filter(metadata__origin=vocab.ORIGIN_OPEN)
    step2 = open_clicks.filter(metadata__channel=STEP2_CHANNEL_LABEL)
    id_clicks = clicks.filter(referral__referral_identity__isnull=False)
    shares = base.filter(event_type=vocab.SHARE_INTENT)
    shares_with_id = shares.filter(referral__referral_identity__isnull=False)
    entered = base.filter(event_type=vocab.KITE_PROMPT_ACTION, metadata__action=vocab.PROMPT_ACTION_ENTERED)

    entered_ids = Counter(e.metadata.get("client_id") for e in entered.only("metadata"))
    entered_ids.pop(None, None)
    entered_ids.pop("", None)

    # NOT .exclude(metadata__channel=...): in SQL a click with NO channel key compares as
    # NULL and would be dropped too — and the plain /open click has no channel key.
    n_open, n_step2 = open_clicks.count(), step2.count()
    return {
        "clicks": clicks.count(),
        "open_link": n_open - n_step2,
        "step2": n_step2,
        "fallback": clicks.filter(metadata__origin=vocab.ORIGIN_FALLBACK).count(),
        "referral_link": id_clicks.count(),
        "referral_ids": _id_counts(id_clicks, "referral__referral_identity__client_id"),
        "share_with_id": shares_with_id.count(),
        "share_without_id": shares.filter(Q(metadata__without_id=True)).count(),
        "share_ids": _id_counts(shares_with_id, "referral__referral_identity__client_id"),
        "disclosure": base.filter(event_type=vocab.DISCLOSURE_VIEWED).count(),
        "share_prompt": _prompt_counts(base, vocab.PROMPT_MODE_SHARE),
        "referral_prompt": _prompt_counts(base, vocab.PROMPT_MODE_REFERRAL),
        "entered_ids": sorted(entered_ids.items(), key=lambda t: (-t[1], t[0])),
        "new_referrers": _new_referrers(tenant, day, until),
        "accounts": _accounts_opened(tenant, day, until),
    }


def _new_referrers(tenant, day: date, until: date | None = None) -> int:
    """Referrers whose FIRST-ever human click fell in the period (Referral.first_click_at)."""
    from apps.referrals.models import Referral

    start, end = _bounds(day, until)
    return (
        Referral.objects.for_tenant(tenant)
        .filter(referral_identity__isnull=False, first_click_at__gte=start, first_click_at__lt=end)
        .values("referral_identity").distinct().count()
    )


def _accounts_opened(tenant, day: date, until: date | None = None) -> dict:
    """Zoho-sourced openings by their TRUE date (ADR-017), with the Zoho-credited top referrer."""
    from apps.integrations.models import Conversion

    start, end = _bounds(day, until)
    qs = Conversion.objects.for_tenant(tenant).filter(
        is_reversed=False, account_opened_at__gte=start, account_opened_at__lt=end,
    )
    credited = _id_counts(qs.exclude(referrer_client_id=""), "referrer_client_id")
    return {"total": qs.count(), "top": credited[0] if credited else None}


HEADLINE_KEYS = ("open_link", "step2", "referral_link", "share_with_id", "disclosure")


def seven_day_average(tenant, day: date, keys=HEADLINE_KEYS) -> dict:
    """Mean of each headline figure over the 7 IST days BEFORE `day` (not including it)."""
    totals = Counter()
    for back in range(1, 8):
        counts = link_counts(tenant, day - timedelta(days=back))
        for k in keys:
            totals[k] += counts[k]
    return {k: totals[k] / 7 for k in keys}


# --------------------------------------------------------------------------- v2 slots

SLOT_COUNT_V2 = 21
LIST_SEPARATOR = " · "  # Meta rejects \n, tabs and 4+ spaces inside a variable (132018)
NONE_TEXT = "none"      # a variable may never be empty


def _avg_text(avg: float) -> str:
    return f"{avg:.1f}".rstrip("0").rstrip(".") if avg < 10 else f"{avg:.0f}"


def with_avg(n: int, avg: float | None) -> str:
    return f"{n} (7d avg {_avg_text(avg)})" if avg is not None else str(n)


def id_list(items: list[tuple[str, int]], cap: int) -> str:
    """'XY9876 ×5 · AB1234 ×3 · +2 more' — the top `cap` ids, then the rest as a count."""
    if not items:
        return NONE_TEXT
    shown = items[:max(cap, 0)]
    parts = [f"{cid} ×{n}" for cid, n in shown]
    rest = len(items) - len(shown)
    if rest:
        parts.append(f"+{rest} more" if shown else f"{rest} IDs")
    return LIST_SEPARATOR.join(parts)


def _with_ids(head: str, items, cap: int) -> str:
    return f"{head} — {id_list(items, cap)}" if items else head


def _prompt_text(p: dict, skip_label: str) -> str:
    return (
        f"shown {p['shown']} ({p['visitors']} people) · ID typed {p['entered']} · "
        f"{skip_label} {p['skipped']} · wrong ID {p['wrong']}"
    )


def build_slots_v2(day: date, zoho: dict, links: dict, avg: dict | None, greeting_name: str,
                   cap: int) -> list[str]:
    """The 21 v2 slot values, in template order (see docs/integrations draft card)."""
    avg = avg or {}
    rate = f"{zoho['rate_pct']:.0f}%" if zoho["rate_pct"] is not None else "n/a"
    failed = f"failed {zoho.get('failed', 0)}"
    if zoho.get("pending"):
        failed += f", pending {zoho['pending']}"
    other = (
        f"{zoho['other_total']} ({', '.join(f'{k}={v}' for k, v in sorted(zoho['other_breakdown'].items()))})"
        if zoho["other_breakdown"] else "0"
    )
    accounts = links["accounts"]
    top = f"{accounts['top'][0]} ({accounts['top'][1]})" if accounts["top"] else NONE_TEXT
    share_head = (
        f"{links['share_with_id']} with ID, {links['share_without_id']} without "
        f"(7d avg {_avg_text(avg['share_with_id'])})" if "share_with_id" in avg
        else f"{links['share_with_id']} with ID, {links['share_without_id']} without"
    )
    return [
        day.isoformat(),                                                          # {{1}}
        greeting_name,                                                            # {{2}}
        str(zoho["referral_total"]),                                              # {{3}}
        str(zoho["delivered"]),                                                   # {{4}}
        str(zoho["not_delivered"]),                                               # {{5}}
        rate,                                                                      # {{6}}
        failed,                                                                    # {{7}}
        f"capped {zoho['capped']}, invalid/blocked {zoho['invalid']}",            # {{8}}
        other,                                                                     # {{9}}
        with_avg(links["open_link"], avg.get("open_link")),                       # {{10}}
        with_avg(links["step2"], avg.get("step2")),                               # {{11}}
        _with_ids(with_avg(links["referral_link"], avg.get("referral_link")),
                  links["referral_ids"], cap),                                    # {{12}}
        _with_ids(share_head, links["share_ids"], cap),                           # {{13}}
        with_avg(links["disclosure"], avg.get("disclosure")),                     # {{14}}
        _prompt_text(links["share_prompt"], "without ID"),                        # {{15}}
        _prompt_text(links["referral_prompt"], "no ID"),                          # {{16}}
        id_list(links["entered_ids"], cap),                                       # {{17}}
        str(links["clicks"]),                                                      # {{18}}
        str(links["new_referrers"]),                                               # {{19}}
        str(accounts["total"]),                                                    # {{20}}
        top,                                                                       # {{21}}
    ]


def fit_slots_v2(day, zoho, links, avg, greeting_name, cap: int, budget: int) -> list[str]:
    """Build the slots, shrinking ONLY the id lists until the values fit `budget` chars.

    Totals are never dropped. At cap 0 a list collapses to "N IDs"; if the values still
    don't fit, the result is returned anyway (a slightly long report beats no report)."""
    for c in range(max(cap, 0), -1, -1):
        slots = build_slots_v2(day, zoho, links, avg, greeting_name, c)
        if sum(len(v) for v in slots) <= budget:
            return slots
    return slots
