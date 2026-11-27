#!/usr/bin/env python3
"""PreToolUse guard for the frozen shared links (CLAUDE.md §6h, owner rule 2026-11-27).

Claude-side layer of the gate. The hard gate is GitHub (the required `frozen-links`
check + the owner's hand-added `link-change-approved` label); this hook stops a Claude
session from even trying to get around it. It DENIES:
  * shell commands that write, move or delete a gate file (the register, its tests,
    the approval check, its workflow, this hook, .claude/settings.json);
  * `--no-verify` on git commit/push;
  * any GitHub tool call that sets the label `link-change-approved` (only the owner adds
    it, by hand on github.com) or writes a gate file through the API.
It ASKS the human (a permission prompt) before a `git commit` / `git push` whose diff
against origin/main changes or removes a frozen entry or touches a gate file.
Adding entries goes through `FROZEN_LINKS_ADD=... python -m pytest tests/test_frozen_links.py`
(append-only) and is allowed.

Reads the hook JSON on stdin; prints a hookSpecificOutput decision; exit 0. Fails open on
its own internal errors (prints a warning) — the GitHub gate still holds.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABEL = "link-change-approved"
GATE_FILES = (
    "docs/links/frozen-links.json",
    "tests/test_frozen_links.py",
    "tests/urls_frozen_prod.py",
    "apps/referrals/frozen_links.py",
    "scripts/check_frozen_links_approval.py",
    ".github/workflows/frozen-links.yml",
    ".claude/hooks/guard_frozen_links.py",
    ".claude/settings.json",
)
_WRITE_HINTS = re.compile(
    r"(>|\btee\b|\bsed\b[^|;&]*\s-i|\bperl\b[^|;&]*\s-i|\bmv\b|\brm\b|\bcp\b|\btruncate\b|\bdd\b|"
    r"\bgit\s+(rm|mv|checkout|restore|reset|apply|am|cherry-pick|revert)\b|"
    r"\.write_text|\bopen\([^)]*['\"][wa]|\bpatch\b|\bln\b)"
)
_APPEND_ONLY = re.compile(r"\bFROZEN_LINKS_ADD=")


def decide(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def _mentions_gate_file(text: str) -> str | None:
    for f in GATE_FILES:
        if f in text or Path(f).name in text:
            return f
    return None


def _staged_commit() -> str:
    """A throwaway commit object of the index, so `git commit` is checked BEFORE it happens."""
    def git(*a):
        out = subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True)
        return out.stdout.strip()
    return git("commit-tree", git("write-tree"), "-p", "HEAD", "-m", "frozen-links guard probe")


def _protected_diff(cmd: str) -> list[str]:
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_frozen_links_approval as approval  # noqa: PLC0415

        head = _staged_commit() if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd) else "HEAD"
        return approval.protected_changes("origin/main", head)
    except Exception as exc:  # no origin/main, shallow clone, ...: let the GitHub gate decide
        print(f"guard_frozen_links: could not diff against origin/main ({exc})", file=sys.stderr)
        return []


def check_bash(cmd: str) -> None:
    if re.search(r"\bgit\b[^|;&]*\b(commit|push)\b[^|;&]*(--no-verify|\s-n\b)", cmd):
        decide("deny", "§6h: --no-verify is never used in this repo.")
    gate = _mentions_gate_file(cmd)
    if gate and _WRITE_HINTS.search(cmd) and not _APPEND_ONLY.search(cmd):
        decide("deny", f"§6h: {gate} is part of the frozen-link gate. It can only be changed with the "
                       "owner's approval; ask the owner. New links are added with FROZEN_LINKS_ADD=... "
                       "python -m pytest tests/test_frozen_links.py.")
    if re.search(r"\bgit\b[^|;&]*\b(commit|push)\b", cmd):
        reasons = _protected_diff(cmd)
        if reasons:
            decide("ask", "§6h: this changes frozen shared links or the gate itself:\n  - "
                          + "\n  - ".join(reasons[:15])
                          + f"\nOnly the owner may approve. CI will also need the `{LABEL}` label, "
                            "added by the owner by hand on github.com.")


def check_mcp(tool: str, tool_input: dict) -> None:
    blob = json.dumps(tool_input)
    if LABEL in blob:
        decide("deny", f"§6h: only the owner adds the `{LABEL}` label, by hand on github.com.")
    if re.search(r"(create_or_update_file|push_files|delete_file)$", tool):
        gate = _mentions_gate_file(blob)
        if gate:
            decide("deny", f"§6h: {gate} is part of the frozen-link gate; it is not written through the API.")


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return
    tool, tool_input = event.get("tool_name", ""), event.get("tool_input") or {}
    try:
        if tool == "Bash":
            check_bash(str(tool_input.get("command", "")))
        elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
            gate = _mentions_gate_file(path)
            if gate:
                decide("deny", f"§6h: {gate} is part of the frozen-link gate. Ask the owner.")
        elif tool.startswith("mcp__"):
            check_mcp(tool, tool_input)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"guard_frozen_links: internal error, not blocking ({exc})", file=sys.stderr)


if __name__ == "__main__":
    main()
