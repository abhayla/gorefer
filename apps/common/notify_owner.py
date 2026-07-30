"""Thin, zero-dep client for the shared Notifier gateway (GLOBAL.md §2).

One shared owner-notification service for ALL apps (WhatsApp/Telegram/email) —
`/root/notifier` on the Hostinger VPS, localhost-only `127.0.0.1:3300`. GoRefer
POSTs one HTTP call; Notifier routes it by severity/type to the channels configured
for the `gorefer` project in its own config.yaml (added at deploy time, never here).

This is the ONLY outbound-message path this module knows about — it sends nothing
itself, it just forwards to the gateway. A dead gateway must never break the caller:
every failure is caught and returned as {"ok": False, ...}, never raised.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("gorefer.notify_owner")

DEFAULT_TIMEOUT_SECONDS = 5


def notify(*, project: str, severity: str, title: str, body: str = "",
           type: str | None = None, dedupeKey: str | None = None) -> dict:
    """POST /notify to the Notifier gateway. Never raises — returns a result dict.

    NOTIFIER_URL / NOTIFIER_KEY come from env (GLOBAL.env locally; the VPS .env in
    prod) — never hardcoded, never committed.
    """
    base_url = os.environ.get("NOTIFIER_URL", "").rstrip("/")
    key = os.environ.get("NOTIFIER_KEY", "")
    if not base_url or not key:
        logger.warning(
            "NOTIFIER_URL/NOTIFIER_KEY not set — digest not sent (project=%s title=%s)", project, title,
        )
        return {"ok": False, "error": "NOTIFIER_URL/NOTIFIER_KEY not configured"}

    payload = {"project": project, "severity": severity, "title": title[:500]}
    if body:
        payload["body"] = body[:4000]
    if type:
        payload["type"] = type
    if dedupeKey:
        payload["dedupeKey"] = dedupeKey

    # Header name matches the hub's canonical template (core/.claude/templates/owner_notify.py)
    headers = {"Content-Type": "application/json", "X-Api-Key": key}

    req = urllib.request.Request(
        f"{base_url}/notify",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            code = resp.getcode()
            text = resp.read().decode("utf-8", "replace")
            ok = 200 <= code < 300
            if not ok:
                logger.warning("Notifier POST /notify -> http %s", code)
            return {"ok": ok, "status": code, "response": text}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace") if exc.fp else ""
        logger.warning("Notifier POST /notify HTTPError %s", exc.code)
        return {"ok": False, "status": exc.code, "response": text}
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("Notifier POST /notify transport error: %s", exc.__class__.__name__)
        return {"ok": False, "error": str(exc)}
