"""Weekly refresh of the datacenter network table (ADR-019 amendment 2026-11-04).

Downloads the public-domain iptoasn.com dumps, keeps only ranges whose AS description
matches the `datacenter_network_keywords` cascade key, and writes the compact table
ATOMICALLY (temp file in the same directory + os.replace). Any failure - download
error, bad gzip, zero kept rows - leaves the previous table untouched.

Kept out of `netranges.py` on purpose: the click path imports `netranges`, and the
click path must not even import an HTTP client (guardrail #1 spirit).
"""
from __future__ import annotations

import gzip
import io
import logging
import os
import tempfile
import urllib.request
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from . import netranges

logger = logging.getLogger(__name__)

DUMP_URLS = (
    "https://iptoasn.com/data/ip2asn-v4.tsv.gz",
    "https://iptoasn.com/data/ip2asn-v6.tsv.gz",
)
DOWNLOAD_TIMEOUT_SECONDS = 120


class RefreshError(RuntimeError):
    """The table was NOT replaced; the reason is in the message."""


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gorefer-network-table/1"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:  # noqa: S310 (fixed https URLs)
        return resp.read()


def _lines_from_gzip(blob: bytes) -> Iterable[str]:
    return io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(blob)), encoding="utf-8", errors="replace")


def build_lines(dumps: Iterable[Iterable[str]], keywords: list[str]) -> list[str]:
    out: list[str] = []
    for lines in dumps:
        out.extend(netranges.filter_dump(lines, keywords))
    return out


def write_atomic(path: Path, lines: list[str], header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".network-ranges.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(header)
            for line in lines:
                fh.write(line + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refresh_table(*, sources: Iterable[str] | None = None, path: str | os.PathLike | None = None,
                  keywords: list[str] | None = None) -> dict:
    """Rebuild the table. `sources` = local dump files instead of downloading (tests,
    offline runs). Returns a summary dict; raises RefreshError if nothing was written."""
    target = Path(path) if path else netranges.table_path()
    kws = keywords if keywords is not None else netranges.keywords()
    if not kws:
        raise RefreshError("datacenter_network_keywords is empty - table left unchanged")
    dumps: list[Iterable[str]] = []
    try:
        if sources:
            for src in sources:
                with netranges.open_dump(src) as fh:
                    dumps.append(fh.readlines())
        else:
            for url in DUMP_URLS:
                dumps.append(list(_lines_from_gzip(_download(url))))
        lines = build_lines(dumps, kws)
    except (OSError, EOFError, gzip.BadGzipFile, ValueError) as exc:
        raise RefreshError(f"download/parse failed ({exc!r}) - table left unchanged") from exc
    if not lines:
        raise RefreshError("no ranges matched the keywords - table left unchanged")
    header = "# gorefer datacenter network table - built from iptoasn.com (public domain)\n"
    write_atomic(target, lines, header)
    netranges.reset_cache()
    by_kw = Counter(netranges.matching_keyword(line.split("\t", 2)[2], kws) for line in lines)
    summary = {"path": str(target), "ranges": len(lines), "by_keyword": dict(by_kw)}
    logger.info("network table refreshed: %s ranges -> %s", len(lines), target)
    return summary


def scheduled_refresh() -> str:
    """django-q entry point (weekly). Never raises: a failed refresh keeps the old table."""
    try:
        summary = refresh_table()
    except Exception as exc:  # keep the old table; the warning is the signal
        logger.warning("network table refresh failed, old table kept: %s", exc)
        return f"failed: {exc}"
    return f"ok: {summary['ranges']} ranges"
