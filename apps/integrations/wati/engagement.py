"""Daily WhatsApp engagement report (T-032) — productizes the T-031 one-off study.

Computes, for the trailing 24h and trailing N-day (IST) windows, the same metric set
T-031's report covered by hand: outbound sends per template with delivery outcomes +
Meta error codes, responders + response-mode breakdown, 24h session windows opened,
and GoRefer's own share/click events. Writes a dated markdown report to disk and posts
an owner digest via the shared Notifier gateway (`apps.common.notify_owner`).

Read-only against Wati: this module never sends anything. `get_engagement_reader()`
is gated on WATI credentials being present, NOT on `ENABLE_WATI_SEND` — reading
requires no send flag (decision 7). With no live creds it falls back to a log-only
reader (degraded mode: the report is written but marked "no live data").

Findings only — no template copy changes, no customer-facing sends (CLAUDE.md §6c).
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from apps.config.cascade import resolve

logger = logging.getLogger("gorefer.wati.engagement")

HTTP_TIMEOUT_SECONDS = 20
IST_OFFSET = timedelta(hours=5, minutes=30)

# --- Config keys (cascade, ADR-022) — CLAUDE.md §6e: every behavior literal registers
# a config key. All four default to the pre-existing (inert) behavior: disabled, so
# landing this changes nothing until an operator opts a tenant in. ---------------
REPORT_ENABLED_KEY = "wa_engagement_report_enabled"
REPORT_HOUR_IST_KEY = "wa_engagement_report_hour_ist"
LOOKBACK_DAYS_KEY = "wa_engagement_lookback_days"
REPORT_DIR_KEY = "wa_engagement_report_dir"

REPORT_ENABLED_DEFAULT = False
REPORT_HOUR_IST_DEFAULT = 21
LOOKBACK_DAYS_DEFAULT = 7
REPORT_DIR_DEFAULT = "var/reports/wa-engagement"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def report_enabled(tenant_id: int | None) -> bool:
    """Effective `wa_engagement_report_enabled` for a tenant (cascade, default OFF)."""
    if tenant_id is None:
        return False
    try:
        return _as_bool(resolve(REPORT_ENABLED_KEY, tenant_id=tenant_id, default=REPORT_ENABLED_DEFAULT))
    except Exception:
        return False


def report_hour_ist(tenant_id: int | None) -> int:
    try:
        return int(resolve(REPORT_HOUR_IST_KEY, tenant_id=tenant_id, default=REPORT_HOUR_IST_DEFAULT))
    except Exception:
        return REPORT_HOUR_IST_DEFAULT


def lookback_days(tenant_id: int | None) -> int:
    try:
        return int(resolve(LOOKBACK_DAYS_KEY, tenant_id=tenant_id, default=LOOKBACK_DAYS_DEFAULT))
    except Exception:
        return LOOKBACK_DAYS_DEFAULT


def report_dir(tenant_id: int | None) -> str:
    try:
        return str(resolve(REPORT_DIR_KEY, tenant_id=tenant_id, default=REPORT_DIR_DEFAULT))
    except Exception:
        return REPORT_DIR_DEFAULT


# --- Read client (adapter-boundary clean: all Wati HTTP lives here) -------------

@dataclass
class EngagementPull:
    """Raw data pulled from Wati for one window, or a degraded/empty marker."""

    degraded: bool
    broadcasts: list = field(default_factory=list)          # merged: summary + statistics + template
    templates: list = field(default_factory=list)           # template list (name/category/buttons)
    responder_messages: dict = field(default_factory=dict)  # number -> list of getMessages items
    failure_codes: dict = field(default_factory=dict)       # failed_code -> count (recipient-level)


class LogOnlyEngagementReader:
    """No live Wati creds: makes no network call, returns an empty/degraded pull."""

    kind = "log_only"

    def pull(self, *, window_start, window_end) -> EngagementPull:
        logger.info(
            "[wa-engagement] WATI creds absent — degraded pull (no live data) window=%s..%s",
            window_start, window_end,
        )
        return EngagementPull(degraded=True)


class LiveEngagementReader:
    """Live read-only Wati client — reuses the LiveWatiAdapter auth/HTTP shape.

    Config from env only (WATI_API_ENDPOINT / WATI_API_TOKEN), same as
    apps.integrations.wati.adapter.LiveWatiAdapter. Refuses to construct without both.
    """

    kind = "live"

    def __init__(self, *, transport=None):
        base = os.environ.get("WATI_API_ENDPOINT") or os.environ.get("WATI_BASE_URL") or ""
        self.base_url = base.rstrip("/")
        # /api/v1/* stays tenant-suffixed (self.base_url); /api/ext/v3/* is served off the
        # bare host with NO tenant path — proven by T-031 evidence (pull_broadcasts.py).
        # Derived from the configured v1 endpoint so there is no new env var (rail E-6).
        parsed = urllib.parse.urlsplit(self.base_url)
        self.v3_base_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        raw_token = os.environ.get("WATI_API_TOKEN", "")
        self.token = raw_token[len("Bearer "):] if raw_token.startswith("Bearer ") else raw_token
        if not (self.base_url and self.token):
            raise RuntimeError("WATI_API_ENDPOINT / WATI_API_TOKEN not configured — cannot read live.")
        self._transport = transport or self._http
        self._degraded = False

    def _http(self, method: str, url: str, headers: dict, body: bytes | None):
        headers = {**headers, "User-Agent": "GoRefer/1.0 (+https://gorefer.in)"}
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                return resp.getcode(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("WATI engagement transport error: %s", exc.__class__.__name__)
            return 599, ""

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _get_json(self, path: str, *, base: str | None = None) -> dict:
        base_url = base if base is not None else self.base_url
        code, text = self._transport("GET", f"{base_url}{path}", self._auth(), None)
        if not (200 <= code < 300):
            logger.warning("WATI engagement GET %s -> http %s", path, code)
            self._degraded = True
            return {}
        try:
            return json.loads(text or "{}")
        except ValueError:
            self._degraded = True
            return {}

    def pull(self, *, window_start, window_end) -> EngagementPull:
        """Pull broadcasts (paged, created-desc, until older than window_start),
        the template list, and — for numbers with a replied/failed row — their
        recipient-level detail. Mirrors T-031's Appendix method exactly (#1-#6).

        `/api/v1/*` calls stay on the tenant-suffixed `self.base_url`; `/api/ext/v3/*`
        calls use `self.v3_base_url` (bare host, no tenant path) — see __init__. Any
        non-200 response, or a 200 whose body is missing the expected top-level key
        (unknown shape), marks the pull degraded=True rather than silently reporting
        zero counts as real. A present-but-empty list is a legitimate zero.

        Real payload shapes (verified against T-031 evidence, not guessed):
        - `GET /api/v1/getMessageTemplates` → `{"messageTemplates": [...]}` (NOT "messages").
        - `GET /api/ext/v3/broadcasts` → `{"broadcasts": [...]}` (NOT "items"/"data"); each
          summary row carries `id`, `name`, `status`, `template_id`, `created` — no stats,
          no category.
        - `GET /api/ext/v3/broadcasts/{id}` → `{"statistics": {"total_sent": ..., ...}}` —
          the counts are nested under "statistics", not top-level on the detail response.
        - `GET /api/ext/v3/broadcasts/{id}/recipients` → `{"recipients": [...]}`, each with
          `contact_phone`, `status` ("replied"/"failed"/...), `failed_code`.
        """
        self._degraded = False
        tpl_payload = self._get_json("/api/v1/getMessageTemplates?pageSize=300")
        if "messageTemplates" not in tpl_payload:
            self._degraded = True
        templates = tpl_payload.get("messageTemplates") or []
        template_map = {t.get("id"): t for t in templates if t.get("id")}

        summaries: list = []
        page = 1
        while True:
            payload = self._get_json(
                f"/api/ext/v3/broadcasts?page_size=100&page_number={page}", base=self.v3_base_url,
            )
            if "broadcasts" not in payload:
                self._degraded = True
                break
            items = payload.get("broadcasts") or []
            if not items:
                break
            stop = False
            for b in items:
                created = _parse_dt(b.get("created"))
                if created is not None and created < window_start:
                    stop = True
                    continue
                if created is not None and created > window_end:
                    continue
                if b.get("id") is None:
                    continue
                summaries.append(b)
            if stop or len(items) < 100:
                break
            page += 1
            if page > 50:  # hard safety cap — never loop unbounded on a live API
                break

        broadcasts: list = []
        for b in summaries:
            bid = b["id"]
            detail = self._get_json(f"/api/ext/v3/broadcasts/{bid}", base=self.v3_base_url)
            stats = detail.get("statistics") or {}
            tpl = template_map.get(b.get("template_id")) or {}
            merged = {
                **b,
                **stats,
                "category": (tpl.get("category") or "UNKNOWN").upper(),
                "template_name": tpl.get("elementName") or b.get("name") or "unknown",
            }
            broadcasts.append(merged)

        responder_numbers = set()
        failure_codes: dict = {}
        for b in broadcasts:
            if int(b.get("total_replied") or 0) <= 0 and int(b.get("total_failed") or 0) <= 0:
                continue
            rpayload = self._get_json(
                f"/api/ext/v3/broadcasts/{b['id']}/recipients?page_size=100&page_number=1",
                base=self.v3_base_url,
            )
            recipients = rpayload.get("recipients") or []
            for r in recipients:
                status = str(r.get("status") or "").lower()
                if status == "replied":
                    num = r.get("contact_phone")
                    if num:
                        responder_numbers.add(str(num))
                elif status == "failed":
                    code = r.get("failed_code") or "UNKNOWN"
                    failure_codes[code] = failure_codes.get(code, 0) + 1

        responder_messages: dict = {}
        for number in responder_numbers:
            payload = self._get_json(f"/api/v1/getMessages/{urllib.parse.quote(number)}?pageSize=30")
            items = ((payload.get("messages") or {}).get("items")) or []
            responder_messages[number] = items

        return EngagementPull(degraded=self._degraded, broadcasts=broadcasts, templates=templates,
                               responder_messages=responder_messages, failure_codes=failure_codes)


def get_engagement_reader():
    """Live reader if WATI creds are present, else a log-only degraded reader.

    Deliberately independent of ENABLE_WATI_SEND — this is a READ path (decision 7).
    """
    if os.environ.get("WATI_API_ENDPOINT") or os.environ.get("WATI_BASE_URL"):
        if os.environ.get("WATI_API_TOKEN"):
            try:
                return LiveEngagementReader()
            except RuntimeError:
                pass
    return LogOnlyEngagementReader()


def _parse_dt(raw) -> "datetime | None":
    if not raw:
        return None
    try:
        if isinstance(raw, str) and "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromtimestamp(int(raw), tz=dt_timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


# --- Response-mode classification (T-031 Appendix method, reused verbatim) ------

CLIENT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{5}$")


def _quick_reply_labels(templates: list) -> set[str]:
    labels = set()
    for t in templates or []:
        for btn in (t.get("buttons") or []):
            if btn.get("type") == "quick_reply":
                text = ((btn.get("parameter") or {}).get("text")) or btn.get("text")
                if text:
                    labels.add(str(text).strip().lower())
    return labels


def classify_response_mode(text: str, quick_reply_labels: set[str]) -> str:
    norm = (text or "").strip()
    if norm.lower() in quick_reply_labels:
        return "quick_reply_button"
    if CLIENT_ID_RE.match(norm):
        return "keyword_trigger"
    return "free_text"


# --- Metric computation ---------------------------------------------------------

def _window_bounds(now_utc: datetime, days: float) -> tuple[datetime, datetime]:
    return now_utc - timedelta(days=days), now_utc


def _mask_number(number: str) -> str:
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    if len(digits) <= 4:
        return "****"
    return f"…{digits[-4:]}"


def _sends_by_category(broadcasts: list) -> dict:
    out: dict = {}
    for b in broadcasts:
        cat = (b.get("category") or b.get("template_category") or "UNKNOWN").upper()
        bucket = out.setdefault(
            cat, {"sends": 0, "sent": 0, "delivered": 0, "read": 0, "replied": 0, "failed": 0},
        )
        bucket["sends"] += 1
        bucket["sent"] += int(b.get("total_sent") or 0)
        bucket["delivered"] += int(b.get("total_delivered") or 0)
        bucket["read"] += int(b.get("total_read") or 0)
        bucket["replied"] += int(b.get("total_replied") or 0)
        bucket["failed"] += int(b.get("total_failed") or 0)
    return out


def _sends_by_template(broadcasts: list) -> dict:
    out: dict = {}
    for b in broadcasts:
        name = b.get("template_name") or b.get("name") or "unknown"
        bucket = out.setdefault(name, {
            "category": (b.get("category") or "UNKNOWN").upper(),
            "sends": 0, "sent": 0, "delivered": 0, "read": 0, "replied": 0, "failed": 0,
        })
        bucket["sends"] += 1
        bucket["sent"] += int(b.get("total_sent") or 0)
        bucket["delivered"] += int(b.get("total_delivered") or 0)
        bucket["read"] += int(b.get("total_read") or 0)
        bucket["replied"] += int(b.get("total_replied") or 0)
        bucket["failed"] += int(b.get("total_failed") or 0)
    return out


def _responder_breakdown(pull: EngagementPull) -> dict:
    labels = _quick_reply_labels(pull.templates)
    breakdown = {"quick_reply_button": 0, "keyword_trigger": 0, "free_text": 0}
    responders = set()
    for number, items in (pull.responder_messages or {}).items():
        for it in items:
            if it.get("eventType") != "message" or it.get("owner") is not False:
                continue
            text = it.get("text") or ""
            mode = classify_response_mode(text, labels)
            breakdown[mode] += 1
            responders.add(number)
    return {"responders": len(responders), "modes": breakdown}


def _goref_side_events(tenant, window_start, window_end) -> dict:
    from apps.events import vocab
    from apps.events.models import Event

    counts = {}
    for label, event_type in (
        ("share_intent", vocab.SHARE_INTENT),
        ("click", vocab.CLICK),
        ("share_clicked", vocab.SHARE_CLICKED),
    ):
        counts[label] = Event.objects.for_tenant(tenant).filter(
            event_type=event_type,
            timestamp__gte=window_start, timestamp__lt=window_end,
        ).count()
    return counts


def _session_windows_opened(tenant, window_start, window_end) -> dict:
    from apps.followups.models import ScheduledFollowup

    opens = (
        ScheduledFollowup.objects.for_tenant(tenant).filter(
            window_opened_at__gte=window_start, window_opened_at__lt=window_end,
        ).values_list("mobile", "window_opened_at").distinct()
    )
    return {"distinct_windows_opened": len(set(opens))}


def compute_window_metrics(tenant, pull: EngagementPull, window_start, window_end) -> dict:
    """Compute the section a-d metric set for one window (24h or Nd)."""
    metrics = {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "degraded": pull.degraded,
        "by_category": _sends_by_category(pull.broadcasts),
        "by_template": _sends_by_template(pull.broadcasts),
        "failure_codes": dict(pull.failure_codes),
        "total_sends": len(pull.broadcasts),
    }
    metrics["responders"] = _responder_breakdown(pull)
    metrics["goref_events"] = _goref_side_events(tenant, window_start, window_end)
    metrics["session_windows"] = _session_windows_opened(tenant, window_start, window_end)
    return metrics


def compute_report(tenant, *, now_utc: datetime, lookback: int) -> dict:
    """Compute the full report: trailing-24h + trailing-N-day windows."""
    reader = get_engagement_reader()

    day_start, day_end = _window_bounds(now_utc, 1)
    week_start, week_end = _window_bounds(now_utc, lookback)

    day_pull = reader.pull(window_start=day_start, window_end=day_end)
    week_pull = reader.pull(window_start=week_start, window_end=week_end)

    return {
        "tenant": getattr(tenant, "slug", None),
        "generated_at": now_utc.isoformat(),
        "reader_kind": getattr(reader, "kind", "unknown"),
        "degraded": day_pull.degraded or week_pull.degraded,
        "trailing_24h": compute_window_metrics(tenant, day_pull, day_start, day_end),
        f"trailing_{lookback}d": compute_window_metrics(tenant, week_pull, week_start, week_end),
    }


# --- Markdown rendering ----------------------------------------------------------

def render_markdown(report: dict, *, lookback: int) -> str:
    date_str = report["generated_at"][:10]
    lines = [
        f"# WhatsApp Engagement Report — {date_str}",
        "",
        f"Generated {report['generated_at']} · reader={report['reader_kind']} · tenant={report['tenant']}",
        "",
    ]
    if report.get("degraded"):
        lines.append("> **NO LIVE DATA — WATI credentials absent.** This report reflects an intended "
                      "pull that could not run; all counts below are zero/empty by construction.")
        lines.append("")

    for label, key in (("Trailing 24h", "trailing_24h"), (f"Trailing {lookback}d", f"trailing_{lookback}d")):
        m = report[key]
        lines.append(f"## {label} ({m['window_start']} → {m['window_end']})")
        lines.append("")
        lines.append(f"- Total sends: {m['total_sends']}")
        for cat, b in sorted(m["by_category"].items()):
            lines.append(
                f"  - {cat}: sends={b['sends']} delivered={b['delivered']} read={b['read']} "
                f"replied={b['replied']} failed={b['failed']}"
            )
        r = m["responders"]
        lines.append(f"- Responders: {r['responders']} (quick_reply={r['modes']['quick_reply_button']}, "
                      f"keyword={r['modes']['keyword_trigger']}, free_text={r['modes']['free_text']})")
        lines.append(f"- Session windows opened: {m['session_windows']['distinct_windows_opened']}")
        g = m["goref_events"]
        lines.append(f"- GoRefer events: share_intent={g['share_intent']} click={g['click']} "
                      f"share_clicked={g['share_clicked']}")
        if m["failure_codes"]:
            codes_str = ", ".join(f"{k}={v}" for k, v in sorted(m["failure_codes"].items()))
            lines.append(f"- Failure codes: {codes_str}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Findings only — no template copy changes, no customer-facing sends (T-032).*")
    return "\n".join(lines) + "\n"


# --- Digest (Notifier) ------------------------------------------------------------

def build_digest(
    report: dict, *, lookback: int, report_path: str, prev_day_responders: int | None = None,
) -> dict:
    date_str = report["generated_at"][:10]
    day = report["trailing_24h"]
    week = report[f"trailing_{lookback}d"]
    trend = ""
    if prev_day_responders is not None:
        trend = f" · responders trend {prev_day_responders} → {day['responders']['responders']}"

    title = f"WA engagement — {date_str}"
    if report.get("degraded"):
        title += " (NO LIVE DATA)"

    delivered = sum(b["delivered"] for b in day["by_category"].values())
    total = day["total_sends"] or 0
    pct = f"{(delivered / total * 100):.1f}%" if total else "n/a"

    body_lines = [
        f"Sends (24h): {total}, delivered {pct}",
        f"Responders (24h): {day['responders']['responders']} "
        f"(top mode: {_top_mode(day['responders']['modes'])})",
        f"Windows opened (24h): {day['session_windows']['distinct_windows_opened']}",
        f"7d responders: {week['responders']['responders']}{trend}",
        f"Report: {report_path}",
    ]
    body = "\n".join(body_lines)
    return {
        "project": "gorefer",
        "severity": "info",
        "title": title[:500],
        "body": body[:4000],
        "type": "digest",
        "dedupeKey": f"wa-engagement-{date_str}",
    }


def _top_mode(modes: dict) -> str:
    if not any(modes.values()):
        return "none"
    return max(modes.items(), key=lambda kv: kv[1])[0]


# --- Orchestration (shared by the management command + the scheduled task) ------

def run_report_for_tenant(tenant, *, now_utc: datetime | None = None) -> dict:
    """Compute + write the report + send the owner digest for one tenant.

    Returns {"skipped": True} if disabled; otherwise {"report_path", "report": ..., "digest_result": ...}.
    Never raises on a digest-send failure — logged, job still succeeds (decision on Notifier).
    """
    from django.utils import timezone as dj_timezone

    from apps.common.notify_owner import notify

    if not report_enabled(tenant.id):
        return {"skipped": True, "reason": "wa_engagement_report_enabled is False"}

    now = now_utc or dj_timezone.now()
    lookback = lookback_days(tenant.id)
    report = compute_report(tenant, now_utc=now, lookback=lookback)

    base_dir = report_dir(tenant.id)
    date_str = report["generated_at"][:10]
    path = os.path.join(base_dir, f"{date_str}.md")
    os.makedirs(base_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report, lookback=lookback))

    digest = build_digest(report, lookback=lookback, report_path=path)
    try:
        digest_result = notify(**digest)
    except Exception as exc:  # never fail the report job on a digest-send problem
        logger.warning("wa_engagement digest send failed: %s", exc)
        digest_result = {"ok": False, "error": str(exc)}

    return {"skipped": False, "report_path": path, "report": report, "digest_result": digest_result}


def _current_ist_hour(now_utc: datetime) -> int:
    return ((now_utc + IST_OFFSET).hour)


def run_scheduled_report(*, now_utc: datetime | None = None) -> dict:
    """Entry point for the django-q schedule.

    Fires hourly (setup_schedules registers this at a 60-minute interval) but only
    does real work for a tenant during its configured `wa_engagement_report_hour_ist`
    hour — the interval itself can't express "once a day at hour H", so the hour
    check lives here (same "poll often, gate on config" idiom as the followup sweep
    gating on quiet hours). Other hours are a cheap per-tenant no-op.
    """
    from django.utils import timezone as dj_timezone

    from apps.tenants.models import Tenant

    now = now_utc or dj_timezone.now()
    current_hour = _current_ist_hour(now)

    results = {}
    for tenant in Tenant.objects.filter(is_active=True):
        target_hour = report_hour_ist(tenant.id)
        if current_hour != target_hour:
            reason = f"not the configured hour ({current_hour} != {target_hour})"
            results[tenant.slug] = {"skipped": True, "reason": reason}
            continue
        results[tenant.slug] = run_report_for_tenant(tenant, now_utc=now)
    return results
