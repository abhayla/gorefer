"""Rail E-7 (T-049): tenant scoping is STRUCTURAL, not remembered.

ADR-023 multi-tenancy is a single-schema `tenant_id` discriminator. Until this
rail existed it was enforced only by every author remembering to write
`filter(tenant=...)` by hand — one forgotten filter after tenant #2 onboards is a
cross-tenant data leak, and nothing caught a new unscoped query.

This rail makes the convention machine-checked: production source must express
tenant scoping through `TenantQuerySet.for_tenant()` (apps/common/models.py), the
single choke point where hierarchy-aware visibility (doc 16 §3.1) will land. A raw
`filter(tenant=...)` / `filter(tenant_id=...)` anywhere under apps/, api/ or
gorefer/ fails this test unless it is in the ALLOWLIST below with a reason.

Same shape as the E-1…E-6 rails in tests/test_architecture_rails.py and the E-3
gate in scripts/check_architecture.py: an EMPTY-baseline gate, so the count can
only go down.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories of production source this rail governs.
SCANNED_ROOTS = ("apps", "api", "gorefer")

#: Path fragments skipped wholesale.
#: `migrations` — historical models rebuilt by Django carry a plain
#: models.Manager, so `for_tenant()` does not exist there by construction.
SKIPPED_PARTS = ("migrations",)

#: Call sites allowed to keep a raw tenant filter. Key = repo-relative path,
#: value = the one-line justification. Keep this EMPTY-by-default: every entry is
#: a place the rail cannot protect, so each needs a reason a reviewer can check.
ALLOWLIST: dict[str, str] = {
    # The helper's own implementation — this IS the choke point being enforced.
    "apps/common/models.py": "TenantQuerySet.for_tenant() itself; the one raw filter by design.",
}


def _tenant_filter_hits() -> list[tuple[str, int]]:
    """Every `.filter(tenant=...)` / `.filter(tenant_id=...)` in scanned source.

    AST-based, not regex: a call split across lines (the common formatting in this
    repo) must not be able to hide from the rail.
    """
    hits: list[tuple[str, int]] = []
    for root in SCANNED_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            if any(part in SKIPPED_PARTS for part in path.parts):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in ("filter", "exclude"):
                    continue
                if any(kw.arg in ("tenant", "tenant_id") for kw in node.keywords):
                    hits.append((rel, node.lineno))
    return hits


def test_e7_no_raw_tenant_filter_outside_the_helper():
    offenders = [(rel, line) for rel, line in _tenant_filter_hits() if rel not in ALLOWLIST]
    assert not offenders, (
        "raw tenant filter(s) outside the for_tenant() choke point:\n  "
        + "\n  ".join(f"{rel}:{line}" for rel, line in offenders)
        + "\n\nUse `.for_tenant(tenant)` (apps/common/models.py TenantQuerySet) so the "
        "ADR-023 scope has ONE implementation — that is where hierarchy-aware "
        "visibility (doc 16 §3.1) lands. If this site genuinely must filter by hand, "
        "add its path to ALLOWLIST in this file with a one-line justification."
    )


def test_e7_allowlist_entries_are_real_and_still_needed():
    """A stale allowlist is worse than none — it silently un-guards a live file."""
    hit_files = {rel for rel, _ in _tenant_filter_hits()}
    stale = sorted(set(ALLOWLIST) - hit_files)
    assert not stale, (
        f"ALLOWLIST entries with no remaining raw tenant filter: {stale} — "
        "delete them so the rail keeps guarding those files."
    )


def test_e7_scanner_detects_a_violation():
    """The rail must actually fire — a scanner that finds nothing proves nothing."""
    source = "Thing.objects.filter(\n    tenant=tenant,\n    deleted_at__isnull=True,\n)\n"
    tree = ast.parse(source)
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "filter"
        and any(kw.arg == "tenant" for kw in node.keywords)
    ]
    assert found, "scanner failed to detect a multi-line raw tenant filter"
