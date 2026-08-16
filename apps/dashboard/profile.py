"""Read-only queries for the User Referral Screen / "Referral Profile" (M9, Part B).

Everything referred by ONE Zerodha client id, assembled from:
  - GoRefer's OWN captured data (Event stream + VisitorPII for IP/city + user-agent),
  - Zoho READ enrichment (top band + Referred-People tab) via the read-only adapter.

Config-over-code: column sets + user-facing strings come from PROFILE_CONFIG (a config
constant, not scattered literals), so per-partner column tuning is a config change
(DF-5 pattern), not code. Reward wording still flows from REFERRAL_INCENTIVE_CLAIM.

PII: the ADMIN view shows full IP + phone. A future customer/referrer view masks them,
gated by PII_MASK_FOR_CUSTOMER_VIEW — built now, dormant until ENABLE_CUSTOMER_LOGIN.
Guardrail #2 preserved: nothing here writes/sets conversion status.
"""
from __future__ import annotations

import logging

from apps.common.phone import normalize_phone
from apps.events.models import Event, VisitorPII
from apps.integrations.models import Conversion
from apps.integrations.ports import (
    ReferredPeople,
    ZohoContact,
    get_crm_read_port,
)
from apps.referrals.models import Lead, Prospect, Referral, ReferralIdentity

# Referrer-name lookup: the ONE shared helper (also used by apps/dashboard/queries),
# so the two can never diverge again (was a documented-only invariant before T-046).
from .queries import _referrer_name

logger = logging.getLogger("gorefer.dashboard.profile")

# ── Config-over-code: labels/columns/strings (a config constant, not inline literals).
# The Clicks/People column sets are here so per-partner tuning is a config change.
PROFILE_CONFIG = {
    "clicks_columns": [
        ("t", "Date"), ("partner", "Partner"), ("channel", "Channel"), ("city", "City"),
        ("region", "Region"), ("country", "Country"), ("ip", "IP"), ("device", "Device"),
        ("ua", "OS/Browser"), ("traffic", "Traffic"), ("outcome", "Outcome"),
    ],
    "people_columns": [
        ("name", "Name"), ("city", "City"), ("profession", "Profession"),
        ("partner", "Partner"), ("status", "Account Status"), ("opened", "Opened"),
        ("reward", "Reward"),
    ],
    "clicks_filters": ["all", "human", "bot", "Mobile", "Desktop", "WhatsApp"],
    "not_on_file": "— not on file —",
    "no_name": "— name not on file —",
    "unique_note": (
        "Visitor count is approximate (bot-filtered). Bot/preview hits are logged but "
        "excluded from click & visitor totals."
    ),
    "link_base": "gorefer.in/r/",
    # §4.4 disclosure host linked from the referrer self-view share text (ADR-031).
    "disclosure_url": "gorefer.in/d/pifs",
}


def _device_and_ua(user_agent: str) -> tuple[str, str]:
    """Best-effort device class + 'OS·Browser' from a user-agent string.

    Deliberately lightweight (no external UA library) — GoRefer already filters bots
    upstream, so this only labels human rows for display.
    """
    ua = user_agent or ""
    low = ua.lower()
    # Device class.
    if any(k in low for k in ("mobile", "android", "iphone", "ipad", "ipod")):
        device = "Mobile"
    elif ua:
        device = "Desktop"
    else:
        device = "—"
    # OS.
    if "android" in low:
        os_name = "Android"
    elif "iphone" in low or "ipad" in low or "ios" in low:
        os_name = "iOS"
    elif "mac os" in low or "macintosh" in low:
        os_name = "macOS"
    elif "windows" in low:
        os_name = "Win"
    elif "linux" in low:
        os_name = "Linux"
    else:
        os_name = ""
    # Browser.
    if "edg" in low:
        browser = "Edge"
    elif "chrome" in low or "crios" in low:
        browser = "Chrome"
    elif "safari" in low and "chrome" not in low:
        browser = "Safari"
    elif "firefox" in low:
        browser = "Firefox"
    else:
        browser = ""
    ua_label = "·".join([p for p in (os_name, browser) if p]) or (ua[:24] if ua else "—")
    return device, ua_label


# Map the furthest stage a journey reached to a click Outcome label + colour class.
# Per-CLICK outcome labels (owner decision 2026-07-22): each click row reports what
# THAT click led to — never the journey's overall furthest stage, which stamped
# "Lead captured" on every click of a journey where one visit submitted a lead.
# Depth precedence within a click's window (this click → the journey's next click):
_CLICK_WINDOW_PRECEDENCE = [
    ("lead_captured", "Lead captured"),
    ("redirect_completed", "Forwarded to Zerodha signup"),
    ("landing_viewed", "Landing page opened"),
]
_OUTCOME_CLASS = {
    "Clicked": "text-ink-500",
    "Landing page opened": "text-sky-600",
    "Forwarded to Zerodha signup": "text-indigo-600",
    "Lead captured": "text-amber-500",
    # The lead event is immutable history; the Lead row was later hard-deleted
    # (owner decision 2026-07-22: show the deletion, never hide or overstate it).
    "Lead captured (since removed)": "text-amber-400",
    "Bot — excluded": "text-rose-400",
    "Synthetic — excluded": "text-ink-300",
}


def _click_outcome(click_ts, next_click_ts, journey_events, live_lead_prospects=frozenset()) -> str:
    """Deepest stage reached between THIS click and the journey's next click.

    `journey_events` is the journey's non-bot, non-click, non-synthetic
    (event_type, timestamp, person_ref_id) list sorted by timestamp. A bare click
    (nothing followed) is just "Clicked". A lead event whose Lead row no longer
    exists (person_ref_id not in `live_lead_prospects`) reads "(since removed)" —
    the event log is immutable history, the Lead table is current truth.
    """
    window = [
        (et, pid) for et, ts, pid in journey_events
        if ts >= click_ts and (next_click_ts is None or ts < next_click_ts)
    ]
    types_in_window = {et for et, _ in window}
    for event_type, label in _CLICK_WINDOW_PRECEDENCE:
        if event_type in types_in_window:
            if event_type == "lead_captured":
                alive = any(
                    pid in live_lead_prospects
                    for et, pid in window
                    if et == "lead_captured" and pid is not None
                )
                return label if alive else "Lead captured (since removed)"
            return label
    return "Clicked"


def _click_lead_prospect_ids(click_ts, next_click_ts, journey_events) -> set:
    """Prospect ids from `lead_captured` events inside THIS click's window (P-06/DF-11).

    Same window slice `_click_outcome` uses, kept separate so a self-click tag can be
    computed independently of the outcome label. `lead_captured` events carry the
    prospect's pk as `person_ref_id` (apps.referrals.lead_service.capture_lead).
    """
    return {
        pid for et, ts, pid in journey_events
        if et == "lead_captured" and pid is not None
        and ts >= click_ts and (next_click_ts is None or ts < next_click_ts)
    }


def _referrer_own_mobile(client_id: str) -> str | None:
    """The referrer's OWN mobile, resolved from Zoho READ — or None (P-06/DF-11).

    Reuses `_safe_zoho_contact`, so this is gated the same way every other Zoho READ
    call on this page already is: the CRM read port itself resolves live-vs-log-only
    by `ENABLE_ZOHO_READ`, and an unreachable Zoho degrades to an unmatched contact.
    Never guesses — an unmatched contact or a contact with no on-file mobile/phone
    returns None, and the caller must then render every click unmatched (no tag).
    """
    contact = _safe_zoho_contact(client_id)
    if not contact.matched:
        return None
    normalized = normalize_phone(contact.mobile) or normalize_phone(contact.phone)
    return normalized or None


def _referrer_referrals(tenant, client_id: str):
    """All referral rows whose identity is this client id (referral_link source)."""
    qs = Referral.objects.filter(referral_identity__client_id=client_id)
    if tenant is not None:
        qs = qs.for_tenant(tenant)
    return qs.select_related("referral_identity", "program", "program__partner")


def search_referrers(tenant, query: str, limit: int = 25) -> list[dict]:
    """Search referrers by client_id (prefix, case-insensitive) or known name.

    Names come from the Customer table (Abhay's own customers) — the Zoho-read name
    source; a client id with a GoRefer footprint but no known name still matches by id.
    """
    from apps.referrals.models import Customer

    q = (query or "").strip()
    if not q:
        return []
    # Client ids with a GoRefer footprint (a referral identity).
    ids = ReferralIdentity.objects.all()
    if tenant is not None:
        ids = ids.for_tenant(tenant)
    ids = ids.filter(client_id__istartswith=q).values_list("client_id", flat=True).distinct()

    # Names → their client ids (Customer is the name source).
    cust = Customer.objects.filter(first_name__icontains=q)
    if tenant is not None:
        cust = cust.for_tenant(tenant)
    name_ids = set(cust.values_list("client_id", flat=True))

    seen, rows = set(), []
    for cid in list(ids) + list(name_ids):
        if cid in seen:
            continue
        seen.add(cid)
        if not profile_exists(tenant, cid):
            continue
        name = _referrer_name(tenant, cid)
        rows.append({"client_id": cid, "name": name or PROFILE_CONFIG["no_name"], "name_known": bool(name)})
        if len(rows) >= limit:
            break
    return rows


def profile_exists(tenant, client_id: str) -> bool:
    """True if GoRefer has ANY footprint for this client id (a referral OR a Zoho
    conversion crediting it) — so the screen isn't shown for a total stranger."""
    if _referrer_referrals(tenant, client_id).exists():
        return True
    conv = Conversion.objects.filter(referrer_client_id=client_id)
    if tenant is not None:
        conv = conv.for_tenant(tenant)
    return conv.exists()


def identity_for(tenant, client_id: str):
    """This client id's live `ReferralIdentity` for the tenant, or None (T-064).

    Tenant-scoped through `for_tenant()` (rail E-7). A client id with a footprint but
    no identity row — a Zoho-imported off-platform conversion, ADR-015 — correctly
    returns None: there is nobody who could have written a personal opener.
    """
    from apps.referrals.models import ReferralIdentity

    return (
        ReferralIdentity.objects.for_tenant(tenant)
        .filter(client_id=client_id, deleted_at__isnull=True)
        .first()
    )


def personal_opener(tenant, client_id: str) -> str:
    """This referrer's saved personal share opener, or "" (T-064)."""
    from apps.accounts.opener import get_opener

    identity = identity_for(tenant, client_id)
    return get_opener(identity) if identity is not None else ""


def _safe_zoho_contact(client_id: str) -> ZohoContact:
    """Zoho enrichment, degraded to "unmatched" if Zoho is unreachable.

    Enrichment is DECORATION on this page — the load-bearing content (clicks, leads,
    conversions) is GoRefer's own data and needs no Zoho call. With ENABLE_ZOHO_READ
    on, a Zoho outage or an expired token would otherwise 500 the whole profile and
    take the GoRefer-owned numbers down with it. Degrading to the same unmatched shape
    a genuine no-match returns keeps the page up and renders "— not on file —".

    Deliberately NOT swallowed elsewhere: this never touches conversion status (that
    arrives only via the webhook), so a missed read loses nothing but chips.
    """
    try:
        return get_crm_read_port().fetch_contact_by_client_id(client_id=client_id)
    except Exception:
        logger.warning(
            "Zoho enrichment unavailable for ClientId=%s — degrading",
            client_id, exc_info=True,
        )
        return ZohoContact(client_id=client_id, matched=False)


def top_band(tenant, client_id: str) -> dict:
    """Identity + Zoho enrichment chips + the 4 headline aggregates."""
    contact = _safe_zoho_contact(client_id)

    from apps.events.bots import exclude_synthetic

    referrals = list(_referrer_referrals(tenant, client_id))
    referral_ids = [r.id for r in referrals]
    clicks = exclude_synthetic(
        Event.objects.filter(referral_id__in=referral_ids, event_type="click", is_bot=False)
    ).count()
    leads = Lead.objects.filter(referral_id__in=referral_ids)
    if tenant is not None:
        leads = leads.for_tenant(tenant)
    leads_count = leads.count()
    accounts = _accounts_for(tenant, client_id)
    uniques = _unique_visitors_for(tenant, referral_ids)

    name = contact.full_name or PROFILE_CONFIG["no_name"]
    nf = PROFILE_CONFIG["not_on_file"]
    city_state = ", ".join([p for p in (contact.mailing_city, contact.mailing_state) if p]) or nf
    return {
        "client_id": client_id,
        "name": name,
        "name_known": bool(contact.full_name),
        "initials": _initials(contact.full_name, client_id),
        "is_active_investor": bool(contact.is_active_investor),
        "chips": {
            "city_state": city_state,
            "profession": contact.profession or nf,
            "account_status": contact.account_status or nf,
            "opened_on": contact.account_opened_on or nf,
            "reward": contact.referral_bonus or nf,
        },
        "aggregates": {
            "clicks": clicks,
            "unique_visitors": uniques,
            "leads": leads_count,
            "accounts": accounts,
        },
        "zoho_matched": contact.matched,
    }


def _accounts_for(tenant, client_id: str) -> int:
    qs = Conversion.objects.filter(referrer_client_id=client_id, is_reversed=False)
    if tenant is not None:
        qs = qs.for_tenant(tenant)
    return qs.count()


def _unique_visitors_for(tenant, referral_ids) -> int:
    qs = (
        Event.objects.filter(referral_id__in=referral_ids, is_bot=False)
        .exclude(visitor_id__isnull=True).exclude(visitor_id="")
    )
    if tenant is not None:
        qs = qs.for_tenant(tenant)
    return qs.values("visitor_id").distinct().count()


def per_link_cards(tenant, client_id: str) -> list[dict]:
    """One card per REAL, ENABLED partner link this referrer has (today: Zerodha).

    Config/data-driven so N partners render with no redesign — we group the
    referrer's referrals by their (active) program/partner. The illustrative extra
    partner card in the mockup is NOT shipped (only real enabled programs).
    """
    referrals = _referrer_referrals(tenant, client_id).filter(source="referral_link")
    by_program: dict[int, dict] = {}
    for ref in referrals:
        program = ref.program
        if program is None or program.status != "active":
            continue
        card = by_program.setdefault(
            program.id,
            {
                "partner_name": program.name,
                "partner_code": program.partner.code if program.partner_id else "",
                "link": f"{PROFILE_CONFIG['link_base']}{client_id}",
                "clicks": 0, "leads": 0, "accounts": 0,
            },
        )
        card["clicks"] += ref.events.filter(event_type="click", is_bot=False).count()
        card["leads"] += Lead.objects.filter(referral=ref).count()
    # Accounts are credited by client id (Zoho), attach to the Zerodha card(s).
    accounts = _accounts_for(tenant, client_id)
    if by_program and accounts:
        first = next(iter(by_program.values()))
        first["accounts"] = accounts
    return list(by_program.values())


def clicks_page_size(tenant) -> int:
    """Cascade-resolved clicks-tab page size (T-161 pt 22, rail E-6 — pattern of
    `explorer_page_size`). Default 500 comfortably covers every seeded/demo referrer
    (well under 500 clicks), so this is a zero-behaviour-change default."""
    from apps.config.cascade import resolve

    tid = getattr(tenant, "id", None)
    return int(resolve("dashboard_clicks_page_size", tenant_id=tid, default=500))


def clicks_row_count(tenant, client_id: str) -> int:
    """Total click events for this referrer — drives the Clicks-tab pagination."""
    referral_ids = list(_referrer_referrals(tenant, client_id).values_list("id", flat=True))
    return Event.objects.filter(referral_id__in=referral_ids, event_type="click").count()


def clicks_rows(tenant, client_id: str, *, page: int = 1) -> list[dict]:
    """One PAGE of click events (human + bot), newest first, with geo/device/outcome
    enrichment. Geo/device come from GoRefer's OWN captured signals: country/state on
    the Event, city + raw IP on the linked VisitorPII, device/OS from the user-agent.
    Bot rows are included but flagged (the template dims them + excludes from totals).

    Paginated server-side (`dashboard_clicks_page_size`, T-161 pt 22 — pattern of
    `explorer_rows`): the outcome-window scan below is bounded to the page's own time
    span (plus the ONE click immediately newer than the page, needed to close the
    newest row's window correctly) rather than the referrer's entire click history —
    so a 1000-click referrer costs the SAME query shape as a 5-click one.
    """
    referrals = {r.id: r for r in _referrer_referrals(tenant, client_id)}
    referral_ids = list(referrals)
    page_size = clicks_page_size(tenant)
    offset = max(page, 1) - 1
    offset *= page_size

    events = list(
        Event.objects.filter(referral_id__in=referral_ids, event_type="click")
        .order_by("-timestamp")[offset: offset + page_size]
    )
    if not events:
        return []
    newest_ts = events[0].timestamp
    oldest_ts = events[-1].timestamp

    # The closest click strictly NEWER than this page — its timestamp is the upper
    # bound the window scan needs (to correctly close the page's own newest row's
    # outcome window). Page 1's top row has no such click: its own window is
    # open-ended (same as before pagination existed), so the scan stays UNBOUNDED
    # above rather than clipped at the page's own newest click — clipping there would
    # cut off outcome events (e.g. lead_captured) that land after the click but
    # before any next click.
    scan_upper = (
        Event.objects.filter(referral_id__in=referral_ids, event_type="click", timestamp__gt=newest_ts)
        .order_by("timestamp").values_list("timestamp", flat=True).first()
    )

    # Per-journey stage events (non-bot, non-click, non-synthetic) + human click
    # times, for the per-click outcome windows (this click → the next human click) —
    # lower-bounded to oldest_ts and upper-bounded to scan_upper (when a newer click
    # exists), not the referrer's whole lifetime.
    from apps.events.bots import is_synthetic_user_agent
    from apps.referrals.models import Lead

    stage_qs = Event.objects.filter(
        referral_id__in=referral_ids, is_bot=False, timestamp__gte=oldest_ts,
    )
    if scan_upper is not None:
        stage_qs = stage_qs.filter(timestamp__lte=scan_upper)

    stage_events: dict[int, list] = {}
    click_times: dict[int, list] = {}
    lead_prospect_ids: set = set()
    for ev in (
        stage_qs
        .order_by("timestamp")
        .values_list("referral_id", "event_type", "timestamp", "person_ref_id", "user_agent")
    ):
        rid, et, ts, pid, ua = ev
        if et == "click":
            # ALL clicks (synthetic included) bound the windows — otherwise a human
            # click's window would swallow a smoke run's lead and claim it (live
            # misattribution caught on EKU497, 2026-07-22). Synthetic rows still
            # RENDER as "Synthetic — excluded"; they just also close windows.
            click_times.setdefault(rid, []).append(ts)
        elif not is_synthetic_user_agent(ua):
            stage_events.setdefault(rid, []).append((et, ts, pid))
            if et == "lead_captured" and pid is not None:
                lead_prospect_ids.add(pid)
    # Prospects that still have a LIVE Lead row per journey — the current-truth
    # side of the "Lead captured (since removed)" resolution. Membership is checked
    # only against pids already found inside the (time-bounded) stage_events window
    # above, so this query needs no separate time bound — it already scales with the
    # referrer's own lead count, not with click-history size.
    live_lead_prospects: dict[int, set] = {}
    for rid, pid in Lead.objects.filter(
        referral_id__in=referral_ids, deleted_at__isnull=True
    ).values_list("referral_id", "prospect_id"):
        live_lead_prospects.setdefault(rid, set()).add(pid)
    # Self-click tag (P-06/DF-11, DISPLAY-ONLY — no analytics/rollup/count mutation):
    # the referrer's own Zoho-resolved mobile, and each lead prospect's normalized
    # mobile, so a click can be flagged when the PROMOTED lead-side mobile (ADR-018)
    # matches the referrer's own on-file mobile. `referrer_own_mobile` is None when
    # Zoho READ has no match/mobile for this client id — every click then renders
    # exactly as today (no tag, never a guess).
    referrer_own_mobile = _referrer_own_mobile(client_id)
    prospect_mobiles: dict[int, str] = {}
    if referrer_own_mobile and lead_prospect_ids:
        pq = Prospect.objects.filter(pk__in=lead_prospect_ids)
        if tenant is not None:
            pq = pq.for_tenant(tenant)
        prospect_mobiles = {
            row["id"]: normalize_phone(row["mobile"])
            for row in pq.values("id", "mobile")
        }
    # Resolve city/IP from VisitorPII by visitor_id (erasable PII record).
    vids = [e.visitor_id for e in events if e.visitor_id]
    pii = {}
    if vids:
        pq = VisitorPII.objects.filter(visitor_id__in=vids, erased_at__isnull=True)
        if tenant is not None:
            pq = pq.for_tenant(tenant)
        for row in pq:
            pii.setdefault(row.visitor_id, row)

    rows = []
    for e in events:
        referral = referrals.get(e.referral_id)
        program = referral.program if referral else None
        vpii = pii.get(e.visitor_id)
        device, ua_label = _device_and_ua(e.user_agent)
        channel = (e.metadata or {}).get("channel") or "Direct"
        synthetic = is_synthetic_user_agent(e.user_agent)
        self_click = False
        if e.is_bot:
            outcome = "Bot — excluded"
            device = device if device != "—" else "—"
        elif synthetic:
            outcome = "Synthetic — excluded"
        else:
            later = [t for t in click_times.get(e.referral_id, []) if t > e.timestamp]
            next_click_ts = min(later) if later else None
            outcome = _click_outcome(
                e.timestamp, next_click_ts,
                stage_events.get(e.referral_id, []),
                frozenset(live_lead_prospects.get(e.referral_id, set())),
            )
            if referrer_own_mobile:
                window_pids = _click_lead_prospect_ids(
                    e.timestamp, next_click_ts, stage_events.get(e.referral_id, [])
                )
                self_click = any(
                    prospect_mobiles.get(pid) == referrer_own_mobile for pid in window_pids
                )
        rows.append({
            "t": e.timestamp,
            "partner": program.name if program else "—",
            "channel": channel,
            "city": (vpii.city if vpii and vpii.city else "—") if not e.is_bot else "—",
            "region": e.state or "—",
            "country": e.country or ("—" if e.is_bot else "India"),
            "ip": (vpii.raw_ip if vpii and vpii.raw_ip else "—"),
            "device": device,
            "ua": ua_label,
            "bot": e.is_bot,
            "synthetic": synthetic,
            "self_click": self_click,
            "outcome": outcome,
            "outcome_class": _OUTCOME_CLASS.get(outcome, "text-ink-500"),
        })
    return rows


def referred_people(tenant, client_id: str) -> list[dict]:
    """Referred-People tab — one row per identified person, from Zoho READ."""
    try:
        data = get_crm_read_port().fetch_referred_people(referrer_client_id=client_id)
    except Exception:
        # Same rationale as _safe_zoho_contact: an unreachable Zoho must not 500 the
        # profile. An empty tab renders the honest "no people" empty state.
        logger.warning(
            "Zoho referred-people unavailable for ClientId=%s — degrading",
            client_id, exc_info=True,
        )
        data = ReferredPeople(referrer_client_id=client_id, people=[])
    nf = PROFILE_CONFIG["not_on_file"]
    no_name = PROFILE_CONFIG["no_name"]
    rows = []
    for p in data.people:
        rows.append({
            "name": p.name or no_name,
            "name_known": bool(p.name),
            "city": p.city or nf,
            "profession": p.profession or nf,
            "partner": p.partner or nf,
            "status": p.account_status or nf,
            "opened": p.opened_on or "—",
            "reward": p.reward or "—",
        })
    return rows


def _initials(full_name: str | None, client_id: str) -> str:
    if full_name:
        parts = [p for p in full_name.split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            return parts[0][:2].upper()
    return client_id[:2].upper()


def ring_fractions(aggregates: dict) -> dict:
    """Pre-computed 0..1 fractions for the top-band KPI rings (Clicks/Leads/Accounts),
    so the template carries no arithmetic. Denominator is clicks (the base)."""
    clicks = aggregates["clicks"] or 0
    return {
        "clicks": 1.0 if clicks else 0.0,
        "leads": round(aggregates["leads"] / clicks, 3) if clicks else 0.0,
        "accounts": round(aggregates["accounts"] / clicks, 3) if clicks else 0.0,
    }
