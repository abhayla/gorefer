"""Daily funnel digest + threshold alerts (T-127, W4 of the messaging-engine plan).

Two jobs, both config-gated (no literals — CLAUDE.md §6d/§6e), both reading the T-124
`MESSAGING_DIGEST_*` cascade keys (`apps/config/preferences.py`):

  * `run_daily_digest()` — once a day, at `messaging_digest_send_hour_ist`, computes
    the PREVIOUS IST calendar day's counts (Zoho WA_Send_Queue via the T-126
    `CrmReadPort.fetch_send_queue_counts`, grouped referral-vs-other per decision ⑭,
    plus GoRefer's own funnel counts from the immutable event stream) and sends the
    approved template to every `messaging_digest_recipients` number, filling its 15
    positional slots. Follows the same "poll often (hourly), gate on config hour"
    idiom as the WATI engagement report's scheduled-report entry point — the minute-
    granularity scheduler can't express "once daily at hour H" directly.

  * `run_instant_alerts()` — polls more often (every 15 min) and fires ONE short
    session alert per breached rule per IST day when `messaging_digest_alerts_enabled`
    and either the day-so-far Zoho referral failure ratio exceeds
    `messaging_digest_alert_failure_ratio_pct` or today's `share_recovery_viewed`
    hits exceed `messaging_digest_alert_recovery_hits`. Deduped via an Event row
    (kind=funnel_digest_alert, rule, date) checked before sending — a rule can only
    fire once per IST day regardless of how many times the poll re-evaluates it.

Both paths go through the vendor-neutral `get_messaging_port()` / `get_crm_read_port()`
(apps.integrations.ports) — never a `.wati.*` / `.zoho.*` import — and record
accepted -> terminal delivery status the same way `apps.integrations.records_link_send`
does (doc-08 A3: HTTP 200 is never success). Every send/alert also emits a PII-free
Event so the digest itself is observable (Constitution §5). A send failure is caught
and logged; it never raises out of the schedule loop.

Zoho slot mapping (bullets 3-10 of the template — see T-127 contract's verified slot
map): `sent`={{3}} is the total referral-stream queue rows for the day (every status
counted somewhere, decision ⑭); `delivered`={{4}} is the SENT-status subset;
`not delivered`={{5}} is everything else in that total (FAILED/PENDING/SUPPRESSED_*/
OTHER) — a WA_Send_Queue row records dispatch outcome, not a WhatsApp delivery
receipt, so "delivered" here means "successfully handed to the queue's SENT state"
and "not delivered" means "did not reach it (yet or at all)"; `rate`={{6}} is
delivered/sent as a percentage. Bullets {{7}}-{{10}} are free text: capped count,
invalid/blocked-invalid count, an other-stream (non-referral, e.g. legacy
angel_one_*/stay_connected_* broadcasts — CLAUDE.md memory: these are OTHER brokers'
live sends, never retired) summary, and the recovery-saves line.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone as dj_timezone

from apps.common.masking import mask_mobile
from apps.common.phone import normalize_phone
from apps.config.cascade import resolve
from apps.config.preferences import (
    MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT,
    MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT,
    MESSAGING_DIGEST_ALERT_RECOVERY_HITS,
    MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT,
    MESSAGING_DIGEST_ALERTS_ENABLED,
    MESSAGING_DIGEST_ALERTS_ENABLED_DEFAULT,
    MESSAGING_DIGEST_GREETING_NAME,
    MESSAGING_DIGEST_GREETING_NAME_DEFAULT,
    MESSAGING_DIGEST_RECIPIENTS,
    MESSAGING_DIGEST_RECIPIENTS_DEFAULT,
    MESSAGING_DIGEST_SEND_HOUR_IST,
    MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT,
    MESSAGING_DIGEST_TEMPLATE_EN,
    MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT,
)
from apps.events import vocab
from apps.events.bots import exclude_synthetic
from apps.events.models import Event
from apps.integrations import delivery_status as ds
from apps.integrations.models import Notification
from apps.integrations.ports import get_crm_read_port, get_messaging_port

logger = logging.getLogger("gorefer.campaigns.digest")

IST_OFFSET = timedelta(hours=5, minutes=30)

EVENT_KIND_DIGEST = "funnel_digest"
EVENT_KIND_ALERT = "funnel_digest_alert"

# Vendor-neutral send-status literals (architecture boundary, CLAUDE.md §2c): domain
# code outside apps/integrations/ may not import the vendor status module
# directly (E-3). `apps.followups.tasks` uses the same local-literal idiom for
# exactly this reason — these values are the stable SendResult/DeliveryResult
# vocabulary (the vendor status module's STATUS_BLOCKED/STATUS_FAILED).
_STATUS_BLOCKED = "blocked"
_STATUS_FAILED = "failed"

RULE_FAILURE_RATIO = "failure_ratio"
RULE_RECOVERY_HITS = "recovery_hits"

_QUEUE_STATUS_SENT = "SENT"
_QUEUE_STATUS_CAPPED = "SUPPRESSED_CAPPED"
_QUEUE_STATUS_INVALID = "SUPPRESSED_INVALID"
_QUEUE_STATUS_FAILED_ROW = "FAILED"
_QUEUE_STATUS_PENDING_ROW = "PENDING"


# --------------------------------------------------------------------------- config


def _digest_hour_ist(tenant_id: int | None) -> int:
    try:
        return int(
            resolve(MESSAGING_DIGEST_SEND_HOUR_IST, tenant_id=tenant_id,
                    default=MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT)
        )
    except (TypeError, ValueError):
        return MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT


def _digest_recipients(tenant_id: int | None) -> list[str]:
    raw = resolve(
        MESSAGING_DIGEST_RECIPIENTS, tenant_id=tenant_id, default=MESSAGING_DIGEST_RECIPIENTS_DEFAULT
    )
    out = []
    for chunk in str(raw or "").split(","):
        n = normalize_phone(chunk.strip())
        if n and n not in out:
            out.append(n)
    return out


def _alerts_enabled(tenant_id: int | None) -> bool:
    value = resolve(
        MESSAGING_DIGEST_ALERTS_ENABLED, tenant_id=tenant_id, default=MESSAGING_DIGEST_ALERTS_ENABLED_DEFAULT
    )
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _alert_failure_ratio_pct(tenant_id: int | None) -> int:
    try:
        return int(
            resolve(MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT, tenant_id=tenant_id,
                    default=MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT)
        )
    except (TypeError, ValueError):
        return MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT


def _alert_recovery_hits(tenant_id: int | None) -> int:
    try:
        return int(
            resolve(MESSAGING_DIGEST_ALERT_RECOVERY_HITS, tenant_id=tenant_id,
                    default=MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT)
        )
    except (TypeError, ValueError):
        return MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT


def _digest_greeting_name(tenant_id: int | None) -> str:
    value = str(
        resolve(MESSAGING_DIGEST_GREETING_NAME, tenant_id=tenant_id,
                default=MESSAGING_DIGEST_GREETING_NAME_DEFAULT)
    ).strip()
    return value or MESSAGING_DIGEST_GREETING_NAME_DEFAULT


def _digest_template(tenant_id: int | None) -> str:
    value = str(
        resolve(MESSAGING_DIGEST_TEMPLATE_EN, tenant_id=tenant_id,
                default=MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT)
    ).strip()
    return value or MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT


# --------------------------------------------------------------------------- counts


def _ist_day_bounds_utc(day: date):
    """UTC [start, end) instants covering one IST calendar day."""
    start_ist = dj_timezone.datetime(day.year, day.month, day.day, tzinfo=dt_timezone.utc) - IST_OFFSET
    return start_ist, start_ist + timedelta(days=1)


def _top_referrer(tenant, start, end) -> tuple[str, int] | None:
    from django.db.models import Count

    qs = exclude_synthetic(
        Event.objects.for_tenant(tenant).filter(
            event_type=vocab.CLICK, is_bot=False,
            timestamp__gte=start, timestamp__lt=end,
            referral__referral_identity__isnull=False,
        )
    )
    row = (
        qs.values("referral__referral_identity__client_id")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    if not row:
        return None
    return row["referral__referral_identity__client_id"], row["n"]


def goref_counts(tenant, day: date) -> dict:
    """GoRefer-side funnel counts for one IST calendar day (bots excluded)."""
    start, end = _ist_day_bounds_utc(day)
    base = exclude_synthetic(
        Event.objects.for_tenant(tenant).filter(is_bot=False, timestamp__gte=start, timestamp__lt=end)
    )
    top = _top_referrer(tenant, start, end)
    return {
        "human_clicks": base.filter(event_type=vocab.CLICK, is_confirmed_human=True).count(),
        "landing_views": base.filter(event_type=vocab.LANDING_VIEWED).count(),
        "leads": base.filter(event_type=vocab.LEAD_CAPTURED).count(),
        "accounts": base.filter(event_type=vocab.ACCOUNT_OPENED).count(),
        "recovery_saves": base.filter(event_type=vocab.SHARE_RECOVERY_VIEWED).count(),
        "top_referrer": top[0] if top else None,
        "top_referrer_count": top[1] if top else 0,
    }


def zoho_queue_summary(tenant, day: date) -> dict:
    """Zoho WA_Send_Queue counts for one IST day, summarized for the digest slots."""
    crm_read = get_crm_read_port()
    counts = crm_read.fetch_send_queue_counts(date_ist=day)

    referral_total = sum(counts.referral.values())
    delivered = counts.referral.get(_QUEUE_STATUS_SENT, 0)
    not_delivered = referral_total - delivered
    rate = (delivered / referral_total * 100) if referral_total else None
    capped = counts.referral.get(_QUEUE_STATUS_CAPPED, 0)
    invalid = counts.referral.get(_QUEUE_STATUS_INVALID, 0)
    failed = counts.referral.get(_QUEUE_STATUS_FAILED_ROW, 0)
    pending = counts.referral.get(_QUEUE_STATUS_PENDING_ROW, 0)
    other_total = sum(counts.other.values())

    return {
        "referral_total": referral_total,
        "delivered": delivered,
        "not_delivered": not_delivered,
        "rate_pct": rate,
        "capped": capped,
        "invalid": invalid,
        "failed": failed,
        "pending": pending,
        "other_total": other_total,
        "other_breakdown": dict(counts.other),
        "truncated": counts.truncated,
    }


def build_slots(
    day: date, zoho: dict, goref: dict, greeting_name: str = MESSAGING_DIGEST_GREETING_NAME_DEFAULT,
) -> list[str]:
    """The 15 positional slot VALUES, in template order (T-127 verified slot map).

    Bullets {{7}}-{{10}} are the four free-text slots (kept at four, T-132: reallocate
    content, never invent a slot). FAILED leads {{7}} because it is the largest
    not-delivered bucket (T-132: the first live digest left it implicit, hidden inside
    the {{5}} not-delivered total); a PENDING count joins the same line only when the
    queue actually holds pending rows, so a stuck day is visible without adding noise
    to a clean one. {{8}} keeps capped + invalid together (both suppression, not
    failure); {{9}}/{{10}} are unchanged (other-stream summary, recovery saves).
    """
    rate_str = f"{zoho['rate_pct']:.0f}%" if zoho["rate_pct"] is not None else "n/a"
    other_str = (
        f"{zoho['other_total']} ({', '.join(f'{k}={v}' for k, v in sorted(zoho['other_breakdown'].items()))})"
        if zoho["other_breakdown"] else "0"
    )
    top_str = (
        f"{goref['top_referrer']} ({goref['top_referrer_count']})" if goref["top_referrer"] else "none"
    )
    pending = zoho.get("pending", 0)
    failed_str = f"Failed: {zoho.get('failed', 0)}"
    if pending:
        failed_str += f", Pending: {pending}"
    return [
        day.isoformat(),                                    # {{1}} date
        greeting_name,                                       # {{2}} name
        str(zoho["referral_total"]),                        # {{3}} sent
        str(zoho["delivered"]),                              # {{4}} delivered
        str(zoho["not_delivered"]),                          # {{5}} not delivered
        rate_str,                                             # {{6}} rate
        failed_str,                                           # {{7}} failed (+ pending, when present)
        f"Capped: {zoho['capped']}, Invalid/blocked: {zoho['invalid']}",  # {{8}}
        f"Other streams: {other_str}",                       # {{9}}
        f"Recovery saves: {goref['recovery_saves']}",        # {{10}}
        str(goref["human_clicks"]),                          # {{11}} human clicks
        str(goref["landing_views"]),                         # {{12}} landing views
        str(goref["leads"]),                                 # {{13}} leads
        str(goref["accounts"]),                               # {{14}} accounts
        top_str,                                              # {{15}} top referrer
    ]


# --------------------------------------------------------------------------- send + record


def _send_and_record(*, tenant, mobile: str, template: str, slots: list[str], kind: str, meta: dict) -> dict:
    """Send one templated message, record accepted -> terminal status (doc-08 A3).

    Mirrors `apps.integrations.records_link_send._send_and_record` for a non-per-
    client-id, operator-facing send (recipient_role='office').
    """
    masked = mask_mobile(mobile)
    idem = f"{kind}:{template}:{mobile}:{dj_timezone.now().isoformat()}"
    n = Notification.objects.create(
        tenant=tenant,
        recipient_role="office",
        recipient_mobile=mobile,
        template=template,
        category="UTILITY",
        template_params=[{"name": str(i), "value": v} for i, v in enumerate(slots, start=1)],
        idempotency_key=idem,
        status="queued",
    )

    messaging = get_messaging_port()
    result = messaging.send_template(
        to=mobile, template=template,
        params={"template_params": [{"value": v} for v in slots]},
    )
    n.adapter_kind = getattr(messaging, "kind", "")

    if result.raw_status == _STATUS_BLOCKED:
        n.status = "skipped"
        n.skip_reason = "recipient not in WATI allowlist (fail-closed)"
        n.save(update_fields=["status", "skip_reason", "adapter_kind", "updated_at"])
        _emit_event(tenant, kind, "blocked", meta)
        return {"outcome": "skipped", "reason": n.skip_reason, "mobile": masked}

    n.provider_message_id = result.provider_message_id or ""
    n.status = "accepted"
    n.save(update_fields=["provider_message_id", "status", "adapter_kind", "updated_at"])

    if not result.accepted:
        n.status = "failed"
        n.save(update_fields=["status", "updated_at"])
        _emit_event(tenant, kind, "failed", meta)
        return {"outcome": "failed", "reason": "send not accepted", "mobile": masked}

    delivery = messaging.get_message_status(
        provider_message_id=n.provider_message_id, recipient_mobile=mobile, template=template,
    )
    if ds.supersedes(n.status, delivery.status):
        n.status = delivery.status
        if delivery.status == _STATUS_FAILED:
            n.meta_error_code = delivery.meta_error_code
            n.failure_classification = ds.classify_failure(delivery.meta_error_code)
        n.save(update_fields=["status", "meta_error_code", "failure_classification", "updated_at"])

    _emit_event(tenant, kind, n.status, meta)
    outcome = "failed" if n.status == _STATUS_FAILED else "sent"
    return {"outcome": outcome, "reason": n.status, "mobile": masked}


def _emit_event(tenant, kind: str, outcome: str, meta: dict) -> None:
    """PII-free funnel event so the digest/alert itself is observable (Constitution §5)."""
    try:
        Event.objects.create(
            tenant=tenant,
            event_type=vocab.NOTIFICATION,
            source=vocab.SRC_WATI,
            user_type="system",
            metadata={"kind": kind, "outcome": outcome, **meta},
        )
    except Exception:
        logger.warning("digest funnel event emit failed (kind=%s)", kind, exc_info=True)


# --------------------------------------------------------------------------- daily digest


def run_digest_for_tenant(tenant, *, day: date | None = None) -> dict:
    """Compute + send the previous-IST-day digest to every configured recipient."""
    tenant_id = tenant.id
    target_day = day or (dj_timezone.now() + IST_OFFSET).date() - timedelta(days=1)
    recipients = _digest_recipients(tenant_id)
    if not recipients:
        return {"skipped": True, "reason": "no digest recipients configured"}

    template = _digest_template(tenant_id)
    greeting_name = _digest_greeting_name(tenant_id)
    zoho = zoho_queue_summary(tenant, target_day)
    goref = goref_counts(tenant, target_day)
    slots = build_slots(target_day, zoho, goref, greeting_name)

    results = []
    for mobile in recipients:
        try:
            results.append(
                _send_and_record(
                    tenant=tenant, mobile=mobile, template=template, slots=slots,
                    kind=EVENT_KIND_DIGEST, meta={"date": target_day.isoformat()},
                )
            )
        except Exception:
            logger.warning("digest send failed for masked=%s", mask_mobile(mobile), exc_info=True)
            results.append({"outcome": "failed", "reason": "exception", "mobile": mask_mobile(mobile)})

    return {"skipped": False, "date": target_day.isoformat(), "template": template, "results": results}


def _current_ist_hour(now_utc) -> int:
    return (now_utc + IST_OFFSET).hour


def run_daily_digest(*, now_utc=None) -> dict:
    """Schedule entry point. Fires hourly but only sends during the tenant's
    configured `messaging_digest_send_hour_ist` — the interval scheduler can't
    express "once a day at hour H" directly (same idiom as wa_engagement_report)."""
    from apps.tenants.models import Tenant

    now = now_utc or dj_timezone.now()
    current_hour = _current_ist_hour(now)

    results = {}
    for tenant in Tenant.objects.filter(is_active=True):
        target_hour = _digest_hour_ist(tenant.id)
        if current_hour != target_hour:
            results[tenant.slug] = {"skipped": True, "reason": "not the configured hour"}
            continue
        try:
            results[tenant.slug] = run_digest_for_tenant(tenant)
        except Exception:
            logger.warning("daily digest failed for tenant=%s", tenant.slug, exc_info=True)
            results[tenant.slug] = {"skipped": False, "error": "exception"}
    return results


# --------------------------------------------------------------------------- instant alerts


def _alert_already_sent_today(tenant, rule: str, day: date) -> bool:
    return Event.objects.for_tenant(tenant).filter(
        event_type=vocab.NOTIFICATION,
        source=vocab.SRC_WATI,
        metadata__kind=EVENT_KIND_ALERT,
        metadata__rule=rule,
        metadata__date=day.isoformat(),
    ).exists()


def _check_failure_ratio(tenant, day: date, tenant_id: int | None) -> str | None:
    zoho = zoho_queue_summary(tenant, day)
    if zoho["referral_total"] <= 0:
        return None
    failure_pct = zoho["not_delivered"] / zoho["referral_total"] * 100
    threshold = _alert_failure_ratio_pct(tenant_id)
    if failure_pct <= threshold:
        return None
    return (
        f"GoRefer alert: WA referral failure ratio {failure_pct:.0f}% "
        f"(threshold {threshold}%) for {day.isoformat()} so far."
    )


def _check_recovery_hits(tenant, day: date, tenant_id: int | None) -> str | None:
    goref = goref_counts(tenant, day)
    threshold = _alert_recovery_hits(tenant_id)
    if goref["recovery_saves"] <= threshold:
        return None
    return (
        f"GoRefer alert: {goref['recovery_saves']} share-recovery page hits "
        f"(threshold {threshold}) for {day.isoformat()} so far."
    )


_ALERT_RULES = (
    (RULE_FAILURE_RATIO, _check_failure_ratio),
    (RULE_RECOVERY_HITS, _check_recovery_hits),
)


def run_alerts_for_tenant(tenant, *, day: date | None = None) -> dict:
    """Evaluate every alert rule for the IST day-so-far; fire at most once/rule/day."""
    tenant_id = tenant.id
    if not _alerts_enabled(tenant_id):
        return {"skipped": True, "reason": "messaging_digest_alerts_enabled is False"}

    target_day = day or (dj_timezone.now() + IST_OFFSET).date()
    recipients = _digest_recipients(tenant_id)
    if not recipients:
        return {"skipped": True, "reason": "no digest recipients configured"}

    fired = []
    for rule, check in _ALERT_RULES:
        if _alert_already_sent_today(tenant, rule, target_day):
            continue
        message = check(tenant, target_day, tenant_id)
        if not message:
            continue
        messaging = get_messaging_port()
        for mobile in recipients:
            try:
                result = messaging.send_session_text(to=mobile, message=message)
            except Exception:
                logger.warning("instant alert send failed rule=%s masked=%s", rule,
                                mask_mobile(mobile), exc_info=True)
                continue
            outcome = "sent" if result.accepted else "failed"
            _emit_event(tenant, EVENT_KIND_ALERT, outcome, {"rule": rule, "date": target_day.isoformat()})
        fired.append(rule)
    return {"skipped": False, "date": target_day.isoformat(), "fired": fired}


def run_instant_alerts(*, now_utc=None) -> dict:
    """Schedule entry point — polls frequently; per-rule/day dedupe keeps this idempotent."""
    from apps.tenants.models import Tenant

    results = {}
    for tenant in Tenant.objects.filter(is_active=True):
        try:
            results[tenant.slug] = run_alerts_for_tenant(tenant)
        except Exception:
            logger.warning("instant alerts failed for tenant=%s", tenant.slug, exc_info=True)
            results[tenant.slug] = {"skipped": False, "error": "exception"}
    return results
