#!/usr/bin/env python
"""Public-repo hygiene gate — fail the build when private data enters the tracked tree.

WHY THIS EXISTS
---------------
`github.com/abhayla/gorefer` is a PUBLIC repository. Before T-240 it carried real
customer/owner mobile numbers, the production and backup VPS addresses, and a
checkpoint file holding a filled dev `.env`. Everything operational moved to the
private `gorefer-ops` repo; what stayed was redacted. This script is the rail that
keeps it that way — a leak of the same class now fails CI instead of being noticed
weeks later.

WHAT IT CHECKS (over every git-tracked text file)
-------------------------------------------------
1. MOBILE   — any Indian mobile that is not on
              `scripts/public_hygiene_allowlist.txt`, in ANY notation: `919876543210`,
              `+91 98765 43210`, `+91-98765 43210` or bare `9876543210` all match, because
              separators are stripped before the scan. Adding a number to that file
              is the deliberate, reviewable moment: the reviewer decides whether the
              number is genuinely safe to publish.
2. HOST     — the production / backup VPS IP literals. Their values are NOT written
              here (that would re-leak them); the script hashes every IPv4-shaped
              literal it finds and compares against a stored SHA-256 set.
3. ENVFILE  — any tracked file whose name looks like a real dotenv (`.env`,
              `.env.prod`, `..gorefer-chk-*.env`, …). `.env.example` is the one
              allowed shape. This is the exact leak from commit `bd6a8fd`.

Run locally: `python scripts/check_public_hygiene.py`
Exit code 0 = clean, 1 = leak found (each hit printed as `path:line: reason`).
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
ALLOWLIST = REPO / "scripts" / "public_hygiene_allowlist.txt"
SELF = "scripts/check_public_hygiene.py"

# Indian mobiles are written a dozen ways in these docs: `919876543210`,
# `+91 98765 43210`, `+91-98765 43210`, and bare `9876543210`. Matching only the
# contiguous 91-prefixed form missed real numbers on the first pass of T-240, so the
# scan runs against a SEPARATOR-COLLAPSED copy of each line and reports the canonical
# 91-prefixed digits. `(?<![0-9])`/`(?![0-9])` keep it off longer digit runs like
# Zoho org ids and Meta template ids.
MOBILE_RE = re.compile(r"(?<![0-9])(?:\+?91)?([6-9][0-9]{9})(?![0-9])")
SEPARATORS_RE = re.compile(r"(?<=[0-9])[ \-]+(?=[0-9])")
IPV4_RE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")

# SHA-256 of the private infrastructure addresses. Hashed, not written, so this
# public file does not itself republish them. gorefer-ops/docs/deploy/DEPLOY-TARGET.md
# holds the plaintext values.
FORBIDDEN_HOST_HASHES = {
    "ee101eab2a847b54d0c077cea1b2ef8648b0791b9f68cb6b197ac69cecdcd319": "production VPS address",
    "c3397673a0363ac0de7d0e3a78c5b79f83cd611c7c049034fd1249f0c099e250": "backup VPS address",
}

# Filenames that are allowed to look like dotenvs.
ENV_ALLOWED = {".env.example"}
ENV_SHAPED_RE = re.compile(r"(^|/)\.?\.?[^/]*\.env(\.[^/]+)?$|(^|/)\.env(\.[^/]+)?$")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def load_allowlist() -> set[str]:
    allowed: set[str] = set()
    for raw in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        entry = raw.split("#", 1)[0].strip()
        if entry:
            allowed.add(entry)
    return allowed


def main() -> int:
    allowed_mobiles = load_allowlist()
    failures: list[str] = []

    for path in tracked_files():
        if ENV_SHAPED_RE.search(path) and path not in ENV_ALLOWED:
            failures.append(
                f"{path}:0: ENVFILE — a dotenv-shaped file is tracked. Secrets never "
                f"belong in git; only .env.example may be committed."
            )

        full = REPO / path
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, FileNotFoundError):
            continue  # binary or unreadable — nothing to scan

        if path == SELF:
            continue  # this file documents the patterns it hunts for

        for lineno, line in enumerate(text.splitlines(), start=1):
            collapsed = SEPARATORS_RE.sub("", line)
            for bare in MOBILE_RE.findall(collapsed):
                hit = "91" + bare
                if hit not in allowed_mobiles:
                    failures.append(
                        f"{path}:{lineno}: MOBILE — {hit} is not in "
                        f"scripts/public_hygiene_allowlist.txt. Redact it, or add it "
                        f"there with a reason if it is genuinely safe to publish."
                    )
            for hit in IPV4_RE.findall(line):
                digest = hashlib.sha256(hit.encode()).hexdigest()
                what = FORBIDDEN_HOST_HASHES.get(digest)
                if what:
                    failures.append(
                        f"{path}:{lineno}: HOST — this line contains the {what}. "
                        f"Use <PROD-VPS>/<BACKUP-VPS>, or read it from "
                        f"DEPLOY_SSH_HOSTNAME / scripts/.deploy-target.env."
                    )

    if failures:
        print("Public-repo hygiene gate FAILED — private data found in tracked files:\n")
        for f in sorted(set(failures)):
            print("  " + f)
        print(
            f"\n{len(set(failures))} problem(s). This repository is public; see "
            f"scripts/check_public_hygiene.py for what each check means."
        )
        return 1

    print("Public-repo hygiene gate OK — no un-allowlisted mobiles, no private host "
          "addresses, no tracked dotenv files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
