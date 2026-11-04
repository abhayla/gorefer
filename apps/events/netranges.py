"""Datacenter / crawler network lookup (ADR-019 amendment 2026-11-04).

The user-agent filter in `bots.py` misses crawlers and link scanners that send a
normal browser UA. Measured on prod 2026-11-04: 306 of 673 "human" clicks came from
hosting/cloud/crawler networks (Facebook, Hetzner, Apple AS714, OVH, Google Cloud...).

This module answers ONE question offline: "is this IP inside a datacenter/crawler
network?" from a compact prefix table built by `manage.py refresh_network_table`
out of the public-domain iptoasn.com dumps. No network call happens on the click
path: the table is a file, loaded lazily once per process, searched with bisect.

Answer states (each pinned by a test):
- IPv4 / IPv6 inside a kept range   -> (True, "<org>")
- address not in any kept range     -> (False, None)
- IP missing / None / empty         -> (False, None)
- malformed IP                      -> (False, None)
- table file missing / unreadable   -> FAIL OPEN (False, None), one warning per process
- table file empty                  -> (False, None)

Fail-open is deliberate: this flag only changes COUNTING, never the HTTP response,
so the cost of a missing table is the old (UA-only) behaviour, not an outage.

Table file format (UTF-8 TSV, one range per line, '#' lines are comments):
    <start_ip>\t<end_ip>\t<org>
IPv4 and IPv6 rows can be mixed; they are split by address family on load.
"""
from __future__ import annotations

import bisect
import gzip
import ipaddress
import logging
import os
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Event.metadata["bot_reason"] value for a click from a datacenter/crawler network.
DATACENTER_BOT_REASON = "datacenter"

# --- Config keys (cascade, ADR-022; CLAUDE.md §6e / rail E-6) -------------------------
TABLE_PATH_KEY = "network_table_path"
# Relative paths resolve against BASE_DIR; on the box BASE_DIR/var is the SHARED var dir
# (scripts/deploy.sh links every release's var/ to $ROOT/shared/var), so the table
# survives deploys and one weekly refresh serves every release.
TABLE_PATH_DEFAULT = "var/network-ranges.tsv"

KEYWORDS_KEY = "datacenter_network_keywords"
# Case-insensitive SUBSTRINGS matched against the iptoasn AS description
# ("<AS handle> - <org name>"). Each phrase was checked against the 2026-11-04 dump for
# false positives: e.g. bare "google" would also keep GOOGLE-FIBER (a home ISP), bare
# "amazon" Brazilian ISPs, bare "m247" 24/7.ai, "amazon technologies" Amazon's satellite
# ISP, and "level 3 parent" legacy CenturyLink home lines - so the phrases are narrower.
# Deliberately ABSENT: Cloudflare, Akamai, Fastly (iCloud Private Relay real users egress
# there) and every Indian consumer ISP (Jio, Airtel, Vi, BSNL, Hathway, ACT...).
KEYWORDS_DEFAULT = [
    "facebook",                 # Meta preview fetchers (WhatsApp/Facebook link cards)
    "apple-engineering",        # AS714, iMessage link previews
    "hetzner",
    "whg hosting",
    "ovh sas",
    "hostinger",
    "google llc",
    "google cloud",
    "google asia pacific",
    "brandwatch",               # social-listening crawler
    "amazon.com",
    "amazon data services",
    "microsoft corp",
    "microsoft limited",
    "level3 - level 3 parent",  # AS3356 only
    "digitalocean",
    "leaseweb",
    "m247 europe",
    "m247 ltd",
    "the constant company",     # Vultr
    "contabo",
    "scaleway",
    "oracle corporation",
    "alibaba cloud",
]


@dataclass
class _FamilyTable:
    starts: list[int] = field(default_factory=list)
    ends: list[int] = field(default_factory=list)
    orgs: list[str] = field(default_factory=list)


@dataclass
class NetworkTable:
    v4: _FamilyTable = field(default_factory=_FamilyTable)
    v6: _FamilyTable = field(default_factory=_FamilyTable)

    def __len__(self) -> int:
        return len(self.v4.starts) + len(self.v6.starts)

    def lookup(self, ip) -> tuple[bool, str | None]:
        """(is_datacenter, org) for one IP. Never raises."""
        if not ip:
            return False, None
        try:
            addr = ipaddress.ip_address(str(ip).strip())
        except ValueError:
            return False, None
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        fam = self.v4 if addr.version == 4 else self.v6
        n = int(addr)
        i = bisect.bisect_right(fam.starts, n) - 1
        if i >= 0 and n <= fam.ends[i]:
            return True, fam.orgs[i]
        return False, None


def parse_table(lines: Iterable[str]) -> NetworkTable:
    """Build a NetworkTable from table-file lines. Bad lines are skipped."""
    rows: dict[int, list[tuple[int, int, str]]] = {4: [], 6: []}
    for line in lines:
        line = line.rstrip("\r\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            start = ipaddress.ip_address(parts[0])
            end = ipaddress.ip_address(parts[1])
        except ValueError:
            continue
        if start.version != end.version or int(end) < int(start):
            continue
        rows[start.version].append((int(start), int(end), parts[2]))
    table = NetworkTable()
    for version, fam in ((4, table.v4), (6, table.v6)):
        for start, end, org in sorted(rows[version]):
            # iptoasn ranges never overlap; if a hand-edited table does, keep the first.
            if fam.ends and start <= fam.ends[-1]:
                continue
            fam.starts.append(start)
            fam.ends.append(end)
            fam.orgs.append(org)
    return table


def load_table(path: str | os.PathLike) -> NetworkTable | None:
    """Read a table file. None when the file is missing or unreadable (caller fails open)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_table(fh)
    except OSError:
        return None


# --- Building the table from the iptoasn dumps (used by refresh_network_table) --------

def iter_dump_rows(lines: Iterable[str]) -> Iterator[tuple[str, str, str, str]]:
    """Yield (start, end, asn, description) from iptoasn ip2asn-v4/v6 TSV lines.

    iptoasn columns: range_start, range_end, AS_number, country_code, AS_description.
    """
    for line in lines:
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) < 5:
            continue
        yield parts[0], parts[1], parts[2], parts[4]


def matching_keyword(description: str, keywords: Iterable[str]) -> str | None:
    desc = (description or "").lower()
    for kw in keywords:
        kw_norm = (kw or "").strip().lower()
        if kw_norm and kw_norm in desc:
            return kw_norm
    return None


def filter_dump(lines: Iterable[str], keywords: Iterable[str]) -> list[str]:
    """Table-file lines for every dump range whose AS description matches a keyword."""
    keywords = [k for k in (keywords or []) if (k or "").strip()]
    out: list[str] = []
    for start, end, asn, desc in iter_dump_rows(lines):
        if asn == "0" or not matching_keyword(desc, keywords):
            continue
        org = f"AS{asn} {desc}".replace("\t", " ").strip()
        out.append(f"{start}\t{end}\t{org}")
    return out


def open_dump(path: str | os.PathLike):
    """Open an iptoasn dump, gzip or plain, as text."""
    p = str(path)
    if p.endswith(".gz"):
        return gzip.open(p, "rt", encoding="utf-8", errors="replace")
    return open(p, encoding="utf-8", errors="replace")


# --- Process-wide lazy table ----------------------------------------------------------
# Loaded on first use, then re-checked (one os.stat) at most every RECHECK_SECONDS so a
# weekly refresh reaches long-lived gunicorn/qcluster workers without a restart.

RECHECK_SECONDS = 300
_lock = threading.Lock()
_table: NetworkTable | None = None
_loaded = False
_mtime: float | None = None
_checked_at = 0.0
_warned_missing = False


def table_path() -> Path:
    from django.conf import settings

    raw = TABLE_PATH_DEFAULT
    try:
        from apps.config.cascade import resolve

        raw = resolve(TABLE_PATH_KEY, default=TABLE_PATH_DEFAULT) or TABLE_PATH_DEFAULT
    except Exception:  # DB not ready etc. -> the default path
        raw = TABLE_PATH_DEFAULT
    p = Path(str(raw))
    return p if p.is_absolute() else Path(settings.BASE_DIR) / p


def keywords() -> list[str]:
    """Effective `datacenter_network_keywords` (central cascade; list or comma string)."""
    try:
        from apps.config.cascade import resolve

        value = resolve(KEYWORDS_KEY, default=KEYWORDS_DEFAULT)
    except Exception:
        value = KEYWORDS_DEFAULT
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def _mtime_of(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _get_table() -> NetworkTable | None:
    global _table, _loaded, _mtime, _checked_at, _warned_missing
    now = time.monotonic()
    if _loaded and now - _checked_at < RECHECK_SECONDS:
        return _table
    with _lock:
        if _loaded and now - _checked_at < RECHECK_SECONDS:
            return _table
        path = table_path()
        mtime = _mtime_of(path)
        if not _loaded or mtime != _mtime:
            table = load_table(path) if mtime is not None else None
            if table is None:
                if not _warned_missing:
                    logger.warning(
                        "datacenter network table missing at %s - datacenter bot filter "
                        "is OFF (fail open); run `manage.py refresh_network_table`",
                        path,
                    )
                    _warned_missing = True
            else:
                _warned_missing = False
            _table, _mtime, _loaded = table, mtime, True
        _checked_at = now
    return _table


def reset_cache() -> None:
    """Forget the loaded table (next lookup reloads). For tests and post-refresh."""
    global _table, _loaded, _mtime, _checked_at, _warned_missing
    with _lock:
        _table, _loaded, _mtime, _checked_at, _warned_missing = None, False, None, 0.0, False


def classify_ip(ip) -> tuple[bool, str | None]:
    """(is_datacenter, org) for the request IP. FAIL OPEN on any problem."""
    if not ip:
        return False, None
    try:
        table = _get_table()
        if table is None:
            return False, None
        return table.lookup(ip)
    except Exception:  # never let counting break a click
        logger.exception("datacenter lookup failed for a click; treating as not datacenter")
        return False, None
