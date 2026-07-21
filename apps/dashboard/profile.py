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

from apps.events.models import Event, VisitorPII
from apps.integrations.models import Conversion
from apps.integrations.zoho.read import (
    ReferredPeople,
    ZohoContact,
    get_zoho_read_adapter,
)
from apps.referrals.models import Lead, Referral, ReferralIdentity

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
_OUTCOME_ORDER = ["click", "landing_viewed", "redirect_completed", "lead_captured", "account_opened"]
_OUTCOME_LABEL = {
    "click": "Clicked",
    "landing_viewed": "Landing viewed",
    "redirect_completed": "Redirected",
    "lead_captured": "Lead captured",
    "account_opened": "Account opened",
}
_OUTCOME_CLASS = {
    "Clicked": "text-ink-500",
    "Landing viewed": "text-sky-600",
    "Redirected": "text-indigo-600",
    "Lead captured": "text-amber-500",
    "Account opened": "text-positive font-semibold",
    "Bot — excluded": "text-rose-400",
}


def _referral_outcome(referral, has_account: bool) -> str:
    """The furthest stage this referral reached (for the click Outcome column)."""
    stages = set(referral.events.values_list("event_type", flat=True))
    reached = "click"
    for stage in _OUTCOME_ORDER:
        if stage == "account_opened":
            if has_account:
                reached = "account_opened"
        elif stage in stages:
            reached = stage
    return _OUTCOME_LABEL.get(reached, "Clicked")


def _referrer_referrals(tenant, client_id: str):
    """All referral rows whose identity is this client id (referral_link source)."""
    qs = Referral.objects.filter(referral_identity__client_id=client_id)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
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
        ids = ids.filter(tenant=tenant)
    ids = ids.filter(client_id__istartswith=q).values_list("client_id", flat=True).distinct()

    # Names → their client ids (Customer is the name source).
    cust = Customer.objects.filter(first_name__icontains=q)
    if tenant is not None:
        cust = cust.filter(tenant=tenant)
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


def _referrer_name(tenant, client_id: str) -> str:
    from apps.referrals.models import Customer

    cust = Customer.objects.filter(client_id=client_id).exclude(first_name="")
    if tenant is not None:
        cust = cust.filter(tenant=tenant)
    cust = cust.first()
    return f"{cust.first_name} {cust.last_name}".strip() if cust else ""


def profile_exists(tenant, client_id: str) -> bool:
    """True if GoRefer has ANY footprint for this client id (a referral OR a Zoho
    conversion crediting it) — so the screen isn't shown for a total stranger."""
    if _referrer_referrals(tenant, client_id).exists():
        return True
    conv = Conversion.objects.filter(referrer_client_id=client_id)
    if tenant is not None:
        conv = conv.filter(tenant=tenant)
    return conv.exists()


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
        return get_zoho_read_adapter().fetch_contact_by_client_id(client_id=client_id)
    except Exception:
        logger.warning(
            "Zoho enrichment unavailable for ClientId=%s — degrading",
            client_id, exc_info=True,
        )
        return ZohoContact(client_id=client_id, matched=False)


def top_band(tenant, client_id: str) -> dict:
    """Identity + Zoho enrichment chips + the 4 headline aggregates."""
    contact = _safe_zoho_contact(client_id)

    referrals = list(_referrer_referrals(tenant, client_id))
    referral_ids = [r.id for r in referrals]
    clicks = Event.objects.filter(referral_id__in=referral_ids, event_type="click", is_bot=False).count()
    leads = Lead.objects.filter(referral_id__in=referral_ids)
    if tenant is not None:
        leads = leads.filter(tenant=tenant)
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
        qs = qs.filter(tenant=tenant)
    return qs.count()


def _unique_visitors_for(tenant, referral_ids) -> int:
    qs = (
        Event.objects.filter(referral_id__in=referral_ids, is_bot=False)
        .exclude(visitor_id__isnull=True).exclude(visitor_id="")
    )
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
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


def clicks_rows(tenant, client_id: str) -> list[dict]:
    """One row per click event (human + bot) with geo/device/outcome enrichment.

    Geo/device come from GoRefer's OWN captured signals: country/state on the Event,
    city + raw IP on the linked VisitorPII, device/OS from the user-agent. Bot rows
    are included but flagged (the template dims them + excludes from totals).
    """
    referrals = {r.id: r for r in _referrer_referrals(tenant, client_id)}
    has_account = _accounts_for(tenant, client_id) > 0
    events = (
        Event.objects.filter(referral_id__in=list(referrals), event_type="click")
        .order_by("-timestamp")
    )
    # Resolve city/IP from VisitorPII by visitor_id (erasable PII record).
    vids = [e.visitor_id for e in events if e.visitor_id]
    pii = {}
    if vids:
        pq = VisitorPII.objects.filter(visitor_id__in=vids, erased_at__isnull=True)
        if tenant is not None:
            pq = pq.filter(tenant=tenant)
        for row in pq:
            pii.setdefault(row.visitor_id, row)

    rows = []
    for e in events:
        referral = referrals.get(e.referral_id)
        program = referral.program if referral else None
        vpii = pii.get(e.visitor_id)
        device, ua_label = _device_and_ua(e.user_agent)
        channel = (e.metadata or {}).get("channel") or "Direct"
        if e.is_bot:
            outcome = "Bot — excluded"
            device = device if device != "—" else "—"
        else:
            outcome = _referral_outcome(referral, has_account) if referral else "Clicked"
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
            "outcome": outcome,
            "outcome_class": _OUTCOME_CLASS.get(outcome, "text-ink-500"),
        })
    return rows


def referred_people(tenant, client_id: str) -> list[dict]:
    """Referred-People tab — one row per identified person, from Zoho READ."""
    try:
        data = get_zoho_read_adapter().fetch_referred_people(referrer_client_id=client_id)
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
