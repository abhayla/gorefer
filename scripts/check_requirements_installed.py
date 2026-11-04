#!/usr/bin/env python3
"""Verify that every requirement in a requirements file is installed AND satisfied.

    python scripts/check_requirements_installed.py [requirements.txt]
    python scripts/check_requirements_installed.py --upgrade-preview REPORT.json [--allow-upgrade]

Exit 0 when every applicable requirement is met. Exit 1 with one line per problem:

    MISSING Pillow>=10.0
    VERSION Django 5.0 does not satisfy >=5.1,<5.2
    UNPARSEABLE requirements.txt:7: git+https://example/x.git

WHY (2026-11-04): Pillow>=10.0 was added to requirements.txt on 2026-08-17 but never
installed on production, because scripts/deploy.sh copied code and never ran pip. The
first page that imported it (the v2 link-preview card) returned HTTP 500 on every
request. scripts/deploy.sh runs this check with the release's venv python BEFORE it
flips `current`, so a release whose dependencies are not all present never goes live.

Rules:
- Comments, blank lines and inline ` # ...` comments are ignored; `\\` continuations join.
- `-r` / `--requirement` includes are followed (relative to the including file).
- Other option lines (`-c`, `--index-url`, `-e`, `--hash` ...) are not requirements and are
  skipped, EXCEPT `-e`/`--editable`, which is reported UNPARSEABLE (cannot be verified).
- Environment markers are honoured: `foo; python_version < "3.0"` is skipped on 3.x.
- Extras are honoured: `pkg[extra]` also checks the direct dependencies that extra adds.
- Pre-release installed versions count as satisfying (prereleases=True).
- Fail CLOSED: a line it cannot parse is a problem, never a silent pass.

Uses only the stdlib plus `packaging` (taken from the environment, or from pip's vendored
copy, which every venv that can run `pip install` has). Run it with the interpreter whose
site-packages you want to check.
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

try:  # pragma: no cover - which branch runs depends on the venv
    from packaging.markers import default_environment
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover
    from pip._vendor.packaging.markers import default_environment  # type: ignore[no-redef]
    from pip._vendor.packaging.requirements import (  # type: ignore[no-redef]
        InvalidRequirement,
        Requirement,
    )
    from pip._vendor.packaging.version import InvalidVersion, Version  # type: ignore[no-redef]


def _logical_lines(path: Path):
    """Yield (lineno, text) with comments stripped and `\\` continuations joined."""
    buf, start = "", None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw
        # A '#' starts a comment at line start or after whitespace (pip's rule); a '#'
        # inside a URL fragment ('...#egg=x') has no whitespace before it.
        if line.lstrip().startswith("#"):
            line = ""
        else:
            for i, ch in enumerate(line):
                if ch == "#" and i > 0 and line[i - 1] in " \t":
                    line = line[:i]
                    break
        if start is None:
            start = lineno
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        buf += line
        text = buf.strip()
        if text:
            yield start, text
        buf, start = "", None
    if buf.strip():
        yield start, buf.strip()


def parse_requirements(path: Path, _seen: set[Path] | None = None):
    """Return (requirements, problems). requirements = [(origin, Requirement)]."""
    seen = _seen if _seen is not None else set()
    path = path.resolve()
    reqs, problems = [], []
    if path in seen:
        return reqs, problems
    seen.add(path)
    if not path.is_file():
        return reqs, [f"UNREADABLE {path}: file not found"]
    for lineno, text in _logical_lines(path):
        origin = f"{path.name}:{lineno}"
        if text.startswith("-"):
            opt, _, rest = text.partition(" ")
            if "=" in opt and not rest:
                opt, _, rest = opt.partition("=")
            rest = rest.strip()
            if opt in ("-r", "--requirement"):
                sub_reqs, sub_problems = parse_requirements(path.parent / rest, seen)
                reqs += sub_reqs
                problems += sub_problems
            elif opt in ("-e", "--editable"):
                problems.append(f"UNPARSEABLE {origin}: editable install cannot be verified: {text}")
            # every other option (-c, --index-url, --hash, ...) is not a requirement
            continue
        # Per-requirement options such as `--hash=...` trail the requirement itself.
        spec = text.split(" --", 1)[0].strip()
        try:
            reqs.append((origin, Requirement(spec)))
        except InvalidRequirement as exc:
            problems.append(f"UNPARSEABLE {origin}: {spec} ({exc})")
    return reqs, problems


def _installed_version(name: str):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _extra_requirements(name: str, extra: str, env: dict):
    """Direct requirements a distribution adds for `extra` (from its own metadata)."""
    out = []
    for line in metadata.requires(name) or []:
        try:
            req = Requirement(line)
        except InvalidRequirement:
            continue
        if req.marker is None or "extra" not in str(req.marker):
            continue
        if req.marker.evaluate({**env, "extra": extra}):
            out.append(req)
    return out


def check_requirement(req, env: dict, label: str | None = None) -> list[str]:
    label = label or str(req)
    if req.marker is not None and not req.marker.evaluate({**env, "extra": ""}):
        return []  # not for this interpreter/platform
    installed = _installed_version(req.name)
    if installed is None:
        return [f"MISSING {label}"]
    problems = []
    if req.specifier:
        try:
            ok = req.specifier.contains(Version(installed), prereleases=True)
        except InvalidVersion:
            ok = False
        if not ok:
            problems.append(f"VERSION {req.name} {installed} does not satisfy {req.specifier}")
    for extra in sorted(req.extras):
        for sub in _extra_requirements(req.name, extra, env):
            sub.marker = None  # already evaluated against the extra
            problems += check_requirement(sub, env, f"{sub} (via {req.name}[{extra}])")
    return problems


def check_file(path: Path) -> list[str]:
    env = default_environment()
    reqs, problems = parse_requirements(path)
    if not reqs and not problems:
        problems.append(f"EMPTY {path}: no requirements found (refusing to pass an empty check)")
    for _origin, req in reqs:
        problems += check_requirement(req, env)
    return problems


def upgrade_changes(report: dict) -> list[str]:
    """From a `pip install --dry-run --report` JSON, list ALREADY-installed packages
    whose version the install would change ("name old -> new"). New installs (not yet
    present) are not listed: they cannot affect the release that is running now."""
    changes = []
    for item in report.get("install") or []:
        meta = item.get("metadata") or {}
        name, new = meta.get("name"), meta.get("version")
        if not name or not new:
            changes.append(f"UNREADABLE report entry: {item!r:.120}")  # fail closed
            continue
        old = _installed_version(name)
        if old is not None and old != new:
            changes.append(f"{name} {old} -> {new}")
    return changes


def upgrade_preview(report_path: Path, allow: bool) -> int:
    """Exit 1 when the install would change an installed package, unless allowed.

    Why: the venv is SHARED with the release that is serving right now; an in-place
    version change happens before the flip and stays even if the deploy aborts."""
    import json
    import os

    allow = allow or os.environ.get("DEPLOY_ALLOW_UPGRADE") == "1"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL: cannot read pip install report {report_path}: {exc}")
        return 1
    changes = upgrade_changes(report)
    for line in changes:
        print(f"UPGRADE {line}")
    if changes and not allow:
        print(
            f"FAIL: {len(changes)} installed package(s) would change version in the shared "
            "venv the running release uses. Re-run with DEPLOY_ALLOW_UPGRADE=1 to accept."
        )
        return 1
    print(f"OK: upgrade preview: {len(changes)} installed package(s) change"
          + (" (allowed by DEPLOY_ALLOW_UPGRADE=1)" if changes else ""))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--upgrade-preview":
        return upgrade_preview(Path(argv[2]), "--allow-upgrade" in argv[3:])
    path = Path(argv[1]) if len(argv) > 1 else Path("requirements.txt")
    problems = check_file(path)
    for line in problems:
        print(line)
    if problems:
        print(f"FAIL: {len(problems)} requirement problem(s) in {path} for {sys.executable}")
        return 1
    print(f"OK: every requirement in {path} is installed and satisfied ({sys.executable})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
