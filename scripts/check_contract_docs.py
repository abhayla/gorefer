#!/usr/bin/env python
"""Contract-doc drift gate.

An integration adapter and the doc that describes its contract must move together.
Otherwise the doc rots into confident-sounding fiction — which is worse than no doc,
because the next person trusts it. This gate fails the build when adapter code changes
without a matching change to the contract folder.

    apps/integrations/wati/**  requires a change under  Wati-GoRefer/**
    apps/integrations/zoho/**  requires a change under  Zoho-GoRefer/**

Escape hatch: put ``[skip-contract-doc]`` anywhere in a commit message in the range
(e.g. for a typo fix or a pure refactor that genuinely cannot change the contract).
The gate is a prompt to think, not a bureaucratic wall — but the skip must be a
deliberate, visible act recorded in the commit message, not a silent default.

Usage:
    python scripts/check_contract_docs.py [--base <ref>] [--head <ref>]

Exits 0 when satisfied (or skipped), 1 with an explanatory message when violated.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

# (code prefix, required doc prefix, human label for the message)
PAIRS = [
    ("apps/integrations/wati/", "Wati-GoRefer/", "Wati"),
    ("apps/integrations/zoho/", "Zoho-GoRefer/", "Zoho"),
]

SKIP_TOKEN = "[skip-contract-doc]"

# Code changes that cannot alter an external contract. Tests and __pycache__ are
# excluded so adding a regression test doesn't demand a doc edit on its own.
IGNORED_SUFFIXES = (".pyc",)
IGNORED_PARTS = ("__pycache__",)


def _run(args: list[str]) -> str:
    return subprocess.run(
        args, capture_output=True, text=True, check=False
    ).stdout.strip()


def changed_files(base: str, head: str) -> list[str]:
    """Files changed between base..head (merge-base aware)."""
    merge_base = _run(["git", "merge-base", base, head]) or base
    out = _run(["git", "diff", "--name-only", f"{merge_base}..{head}"])
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def commit_messages(base: str, head: str) -> str:
    merge_base = _run(["git", "merge-base", base, head]) or base
    return _run(["git", "log", "--format=%B", f"{merge_base}..{head}"])


def _relevant(path: str) -> bool:
    if path.endswith(IGNORED_SUFFIXES):
        return False
    return not any(part in path for part in IGNORED_PARTS)


def evaluate(files: list[str], messages: str = "") -> list[str]:
    """Return a list of violation messages (empty == pass).

    Pure function over the file list so it can be unit-tested without a git repo.
    """
    if SKIP_TOKEN in messages:
        return []

    files = [f for f in files if _relevant(f)]
    violations = []
    for code_prefix, doc_prefix, label in PAIRS:
        code_changed = [f for f in files if f.startswith(code_prefix)]
        doc_changed = [f for f in files if f.startswith(doc_prefix)]
        if code_changed and not doc_changed:
            violations.append(
                f"{label} adapter changed but no contract doc was updated.\n"
                f"    changed: {', '.join(sorted(code_changed)[:6])}"
                + (" …" if len(code_changed) > 6 else "")
                + f"\n    required: update the contract doc under '{doc_prefix}'\n"
                f"      -> {doc_prefix}{label}-Integration-Contract.md "
                f"(send/verify shape, gates, status handling)\n"
                f"    If this change genuinely cannot affect the external contract, add "
                f"'{SKIP_TOKEN}' to the commit message."
            )
    return violations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args()

    files = changed_files(args.base, args.head)
    if not files:
        print("contract-doc gate: no changed files in range — nothing to check.")
        return 0

    violations = evaluate(files, commit_messages(args.base, args.head))
    if not violations:
        print("contract-doc gate: OK")
        return 0

    print("\n=== CONTRACT DOC DRIFT ===\n")
    for v in violations:
        print("  " + v + "\n")
    print(
        "Why: an adapter and its contract doc must move together, or the doc becomes\n"
        "confident-sounding fiction that the next person trusts. See CLAUDE.md.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
