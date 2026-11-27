"""The frozen shared-link register (owner rule 2026-11-27, CLAUDE.md §6h).

Every link GoRefer has ever handed to a customer must keep doing what it did, under
ANY change (code or settings), until the owner explicitly approves a change. The
register `docs/links/frozen-links.json` holds one entry per link FORM (with an example
id standing for every referrer's id) and what it must keep doing:

  redirect -> the exact final address outside GoRefer (partner code + referrer id
              included). GoRefer's own internal hops (the broken-link fallback, the
              pop-up's typed id) are followed; only where the person ENDS matters.
  share    -> opens that share target (wa.me, t.me, x.com) with a message whose every
              gorefer.in link is itself on the register (so the links people forward
              keep working). The message wording may change.
  page     -> GoRefer shows that kind of page (the template, plus the pop-up's mode).
              The page's wording and design may change.
  status   -> that HTTP status (e.g. the 404 that private surfaces keep on purpose).

Adding an entry is free (`python -m pytest tests/test_frozen_links.py` with
FROZEN_LINKS_ADD=...). Changing or removing one needs the owner's
`link-change-approved` label on the PR (scripts/check_frozen_links_approval.py).

This module only OBSERVES — it never writes the register. `observe()` drives the real
URLconf through Django's test client, so it sees exactly what a visitor would.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

REGISTER_PATH = Path(__file__).resolve().parents[2] / "docs" / "links" / "frozen-links.json"

HUMAN_UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"
BOT_UA = "WhatsApp/2.23.20 A"
USER_AGENTS = {"human": HUMAN_UA, "bot": BOT_UA}
MAX_INTERNAL_HOPS = 5

SHARE_TARGETS = {
    "wa.me": "text",
    "api.whatsapp.com": "text",
    "t.me": "text",
    "x.com": "text",
    "twitter.com": "text",
}
_LINK_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def load_register(path: Path = REGISTER_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _page_type(response) -> str:
    names = [t.name for t in (getattr(response, "templates", None) or []) if getattr(t, "name", None)]
    if not names:  # not a template page (e.g. the preview-card PNG): its content type
        return (response.headers.get("Content-Type", "") or "unknown").split(";")[0].strip()
    page = names[0]
    ctx = getattr(response, "context", None)
    mode = None
    try:
        mode = ctx.get("mode") if ctx is not None else None
    except Exception:
        mode = None
    return f"{page}#{mode}" if page == "kite_prompt.html" and mode else page


def _share_outcome(location: str, public_host: str) -> dict:
    parts = urlsplit(location)
    param = SHARE_TARGETS[parts.netloc]
    text = unquote(" ".join(parse_qs(parts.query).get(param, [""])) + " " + " ".join(
        parse_qs(parts.query).get("url", [])))
    links = sorted({
        urlsplit(u).path or "/" for u in _LINK_RE.findall(text)
        if urlsplit(u).netloc == public_host
    })
    return {"kind": "share", "target": parts.netloc, "gorefer_links": links}


def observe(client, path: str, *, ua: str = "human", public_host: str = "gorefer.in") -> dict:
    """What `path` does for a visitor, followed through GoRefer's own redirects."""
    current = path
    for _ in range(MAX_INTERNAL_HOPS + 1):
        resp = client.get(current, HTTP_USER_AGENT=USER_AGENTS[ua], REMOTE_ADDR="203.0.113.50")
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            parts = urlsplit(location)
            if location.startswith("/") or parts.netloc == public_host:
                current = location if location.startswith("/") else (
                    parts.path + (f"?{parts.query}" if parts.query else ""))
                continue
            if parts.netloc in SHARE_TARGETS:
                return _share_outcome(location, public_host)
            return {"kind": "redirect", "location": location}
        if resp.status_code == 200:
            return {"kind": "page", "page": _page_type(resp)}
        return {"kind": "status", "status": resp.status_code}
    return {"kind": "status", "status": "too_many_internal_redirects"}


def register_paths(register: dict) -> set[str]:
    return {e["path"].split("?", 1)[0] for e in register["links"]}
