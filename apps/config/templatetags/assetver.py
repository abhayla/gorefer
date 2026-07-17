"""`static_v` — a cache-busted {% static %}.

Appends a short content-hash query (`?v=<hash8>`) to a static asset's URL so the URL
CHANGES whenever the file's bytes change. This defeats stale BROWSER caches: assets are
served with a long max-age (good for performance), but a long max-age also means a
browser keeps an OLD file until it expires — which is exactly how the fixed toggle CSS
stayed invisible to users who had loaded the broken app.css before the edge was purged.
With a content-hash query, a changed file is a NEW url the browser has never cached, so
the fix is picked up on the next page load with no manual refresh or cache purge.

The hash is computed from the file on disk (STATIC_ROOT first, then finders) and cached
in-process, so it costs one stat+read per asset per worker lifetime, not per request.
Falls back to the plain static url if the file can't be read.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

_HASH_CACHE: dict[str, str] = {}


def _asset_hash(path: str) -> str:
    if path in _HASH_CACHE:
        return _HASH_CACHE[path]
    file_path = None
    # Prefer the collected file under STATIC_ROOT (prod), else the source via finders (dev).
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidate = Path(static_root) / path
        if candidate.is_file():
            file_path = candidate
    if file_path is None:
        found = finders.find(path)
        if found:
            file_path = Path(found)
    digest = ""
    if file_path and file_path.is_file():
        try:
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()[:8]
        except OSError:
            digest = ""
    _HASH_CACHE[path] = digest
    return digest


@register.simple_tag
def static_v(path: str) -> str:
    """Return the static URL for `path` with a `?v=<content-hash>` cache-buster."""
    url = static(path)
    digest = _asset_hash(path)
    return f"{url}?v={digest}" if digest else url
