#!/usr/bin/env python
"""Architecture boundary gate — rail E-3 (doc 16 §5, ADR-044).

Vendor packages (`apps.integrations.wati`, `apps.integrations.zoho`) may be
referenced only from inside `apps/integrations/` and from tests. Every existing
production leak is recorded in `scripts/architecture_import_baseline.txt` — the
Phase-2 work-list. This gate runs in OBSERVE mode: it FAILS only when a file NOT
in the baseline references a vendor package (a NEW leak), so the leak count can
shrink but never grow. When Phase 2 clears the baseline, the gate becomes a hard
boundary automatically (empty baseline = any reference outside the boundary fails).

Usage:
    python scripts/check_architecture.py                  # gate (CI calls this)
    python scripts/check_architecture.py --write-baseline # regenerate the baseline
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "scripts" / "architecture_import_baseline.txt"
PATTERN = re.compile(r"apps\.integrations\.(wati|zoho)")

# Directories whose references are legitimate (the boundary itself) or out of scope.
ALLOWED_PREFIXES = ("apps/integrations/", "tests/", "scripts/", "docs/", "review/")
SKIP_DIRS = {".git", ".venv", "node_modules", "staticfiles", "__pycache__", "migrations"}


def scan() -> set[str]:
    hits: set[str] = set()
    for path in REPO.rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel.startswith(ALLOWED_PREFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if PATTERN.search(text):
            hits.add(rel)
    return hits


def main() -> int:
    hits = scan()

    if "--write-baseline" in sys.argv:
        BASELINE.write_text("\n".join(sorted(hits)) + "\n", encoding="utf-8")
        print(f"architecture gate: baseline written ({len(hits)} files)")
        return 0

    baseline = set()
    if BASELINE.exists():
        baseline = {
            line.strip()
            for line in BASELINE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    new_leaks = sorted(hits - baseline)
    cleared = sorted(baseline - hits)

    print(f"architecture gate (E-3): {len(hits)} vendor references outside the boundary "
          f"(baseline {len(baseline)})")
    if cleared:
        print("  cleared since baseline (run --write-baseline to shrink it):")
        for f in cleared:
            print(f"    - {f}")
    if new_leaks:
        print("  NEW leaks — vendor packages referenced outside apps/integrations/:")
        for f in new_leaks:
            print(f"    - {f}")
        print("  Fix: consume the adapter surface via its get_*_adapter() factory from")
        print("  inside the boundary, or (Phase 2+) the role port. Do NOT add to the")
        print("  baseline — it only shrinks. (doc 16 §5 rail E-3 / ADR-044)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
