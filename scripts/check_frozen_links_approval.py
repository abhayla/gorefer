#!/usr/bin/env python3
"""Frozen shared links — the owner-approval gate (CLAUDE.md §6h, owner rule 2026-11-27).

A pull request may ADD entries to docs/links/frozen-links.json freely. It may NOT change
or remove an entry, change the register's settings/flags blocks, or touch any file of the
gate itself, unless the PR carries the label `link-change-approved` and that label was:

  * added by the approver (env FROZEN_LINKS_APPROVER, default `abhayla`),
  * directly by that person on github.com — NOT through an app or bot (Claude's GitHub
    tools act through an app, so a label Claude adds never counts),
  * after the PR's latest commit (a later push needs a fresh approval).

Runs in .github/workflows/frozen-links.yml on every PR event, including label changes.
Stdlib only. Exit 0 = pass, 1 = blocked (the reason is printed).

Local dry run (no label lookup):  python scripts/check_frozen_links_approval.py --base origin/main
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

REGISTER = "docs/links/frozen-links.json"
LABEL = "link-change-approved"
#: Every file whose change could weaken the guarantee. Changing any of them needs approval.
GATE_FILES = (
    REGISTER,
    "tests/test_frozen_links.py",
    "tests/urls_frozen_prod.py",
    "apps/referrals/frozen_links.py",
    "scripts/check_frozen_links_approval.py",
    ".github/workflows/frozen-links.yml",
    ".claude/hooks/guard_frozen_links.py",
    ".claude/settings.json",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _register_at(ref: str) -> dict | None:
    try:
        return json.loads(_git("show", f"{ref}:{REGISTER}"))
    except subprocess.CalledProcessError:
        return None


def _key(entry: dict) -> str:
    return f'{entry["path"]} [{entry.get("ua", "human")}]'


def protected_changes(base: str, head: str = "HEAD") -> list[str]:
    """Human-readable reasons this diff needs the owner's approval ([] = additions only)."""
    merge_base = _git("merge-base", base, head).strip()
    changed = set(_git("diff", "--name-only", merge_base, head).split())
    reasons = [f"gate file changed: {f}" for f in GATE_FILES if f in changed and f != REGISTER]

    before, after = _register_at(merge_base), _register_at(head)
    if before is None and after is None:
        return reasons
    if after is None:
        reasons.append(f"{REGISTER} was deleted")
        return reasons
    if before is None:
        reasons.append(f"{REGISTER} is new: the owner approves the first version once")
        return reasons
    for block in ("public_host", "prod_flags", "prod_settings"):
        if before.get(block) != after.get(block):
            reasons.append(f"register block '{block}' changed")
    now = {_key(e): e for e in after.get("links", [])}
    for entry in before.get("links", []):
        key = _key(entry)
        if key not in now:
            reasons.append(f"frozen link removed: {key}")
        elif now[key] != entry:
            reasons.append(f"frozen link changed: {key}  {entry['expect']} -> {now[key]['expect']}")
    return reasons


def _api(path: str) -> list | dict:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed api.github.com host
        return json.load(resp)


def _paged(path: str) -> list:
    out, page = [], 1
    while True:
        chunk = _api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        out += chunk
        if len(chunk) < 100:
            return out
        page += 1


def approval_status(repo: str, pr: int, approver: str) -> tuple[bool, str]:
    """(approved?, explanation). Every labeled event is logged so its provenance is auditable."""
    pull = _api(f"/repos/{repo}/pulls/{pr}")
    labels = {lab["name"] for lab in pull.get("labels", [])}
    if LABEL not in labels:
        return False, f"the PR does not carry the label `{LABEL}`"
    commits = _paged(f"/repos/{repo}/pulls/{pr}/commits")
    last_commit = max(c["commit"]["committer"]["date"] for c in commits) if commits else ""
    events = [e for e in _paged(f"/repos/{repo}/issues/{pr}/events")
              if e.get("event") == "labeled" and e.get("label", {}).get("name") == LABEL]
    for e in events:
        print(f"label event: actor={e.get('actor', {}).get('login')} "
              f"app={(e.get('performed_via_github_app') or {}).get('slug')} at={e.get('created_at')}")
    if not events:
        return False, "no labeled event found for the label"
    latest = max(events, key=lambda e: e["created_at"])
    actor = (latest.get("actor") or {}).get("login", "")
    app = latest.get("performed_via_github_app")
    if actor != approver:
        return False, f"the label was added by {actor!r}, not by the approver {approver!r}"
    if app:
        return False, f"the label was added through the app {app.get('slug')!r}, not by hand on github.com"
    if last_commit and latest["created_at"] < last_commit:
        return False, "the label predates the latest commit: re-add it after reviewing the new changes"
    return True, f"approved by {actor} at {latest['created_at']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default=os.environ.get("BASE_REF", "origin/main"))
    parser.add_argument("--head", default=os.environ.get("HEAD_REF", "HEAD"))
    args = parser.parse_args()

    reasons = protected_changes(args.base, args.head)
    if not reasons:
        print("frozen links: additions only (or nothing frozen touched) - no approval needed")
        return 0
    print("This PR changes frozen shared links or the gate itself (CLAUDE.md §6h):")
    for r in reasons:
        print(f"  - {r}")

    repo, pr = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("PR_NUMBER")
    if not (repo and pr and os.environ.get("GITHUB_TOKEN")):
        print("BLOCKED: approval can only be checked on a pull request in CI.")
        return 1
    ok, why = approval_status(repo, int(pr), os.environ.get("FROZEN_LINKS_APPROVER", "abhayla"))
    if ok:
        print(f"APPROVED: {why}")
        return 0
    print(f"BLOCKED: {why}.\nThe owner approves by adding the label `{LABEL}` by hand on github.com.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
