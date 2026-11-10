"""Deploy installs + verifies Python requirements before the flip (2026-11-04).

Class: any new/changed entry in requirements.txt. Pillow>=10.0 was added 2026-08-17
and never installed on production because scripts/deploy.sh had no pip step; the v2
preview card then 500ed on every request. Two layers are pinned here:

1. scripts/check_requirements_installed.py really detects a missing / unsatisfied
   requirement (and fails closed on shapes it cannot verify).
2. scripts/deploy.sh runs pip install + that check BEFORE migrate and BEFORE the
   pre-flip health probe — a refactor that drops or reorders them fails CI.

No database needed: plain functions + a subprocess, so no django_db marker.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check_requirements_installed.py"
DEPLOY = ROOT / "scripts" / "deploy.sh"
MISSING_PKG = "definitely-not-installed-pkg-xyz"

_spec = importlib.util.spec_from_file_location("check_requirements_installed", CHECKER)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


def _write(tmp_path: Path, text: str, name: str = "requirements.txt") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, timeout=60
    )


# ----------------------------------------------------------------- the checker


def test_installed_and_satisfied_exits_zero(tmp_path):
    path = _write(tmp_path, "Django>=5.1,<5.2\ndjango-ninja>=1.6\n")
    result = _run(path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK:")


def test_missing_package_exits_one_and_names_it(tmp_path):
    path = _write(tmp_path, f"Django>=5.1\n{MISSING_PKG}>=1.0\n")
    result = _run(path)
    assert result.returncode == 1
    assert f"MISSING {MISSING_PKG}>=1.0" in result.stdout.splitlines()


def test_version_too_low_is_reported(tmp_path):
    installed = metadata.version("Django")
    path = _write(tmp_path, "Django>=99.0\n")
    result = _run(path)
    assert result.returncode == 1
    assert f"VERSION Django {installed} does not satisfy >=99.0" in result.stdout


def test_comments_blank_lines_options_and_continuations(tmp_path):
    path = _write(
        tmp_path,
        "# a full-line comment\n"
        "\n"
        "--index-url https://pypi.org/simple\n"
        "Django>=5.1   # inline comment\n"
        "django-ninja\\\n"
        ">=1.6\n"
        "   \n",
    )
    reqs, problems = checker.parse_requirements(path)
    assert problems == []
    assert [str(r) for _, r in reqs] == ["Django>=5.1", "django-ninja>=1.6"]
    assert checker.check_file(path) == []


def test_environment_markers_are_honoured(tmp_path):
    skip = _write(tmp_path, f'{MISSING_PKG}; python_version < "3.0"\nDjango\n', "skip.txt")
    assert checker.check_file(skip) == []
    apply = _write(tmp_path, f'{MISSING_PKG}; python_version >= "3.0"\n', "apply.txt")
    assert checker.check_file(apply) == [f'MISSING {MISSING_PKG}; python_version >= "3.0"']


def test_extras_check_the_dependencies_the_extra_adds(tmp_path):
    # Django declares extra "bcrypt" -> requires bcrypt. Expected outcome is computed from
    # this interpreter's own metadata, so the test is deterministic in any venv.
    path = _write(tmp_path, "Django[bcrypt]>=5.1\n")
    problems = checker.check_file(path)
    try:
        metadata.version("bcrypt")
        assert problems == []
    except metadata.PackageNotFoundError:
        assert len(problems) == 1
        assert problems[0].startswith("MISSING bcrypt") and "via Django[bcrypt]" in problems[0]


def test_requirement_includes_are_followed(tmp_path):
    _write(tmp_path, f"{MISSING_PKG}\n", "base.txt")
    path = _write(tmp_path, "-r base.txt\nDjango\n")
    assert checker.check_file(path) == [f"MISSING {MISSING_PKG}"]


@pytest.mark.parametrize(
    "line, prefix",
    [
        ("-e git+https://example.invalid/x.git#egg=x", "UNPARSEABLE"),
        ("git+https://example.invalid/x.git", "UNPARSEABLE"),
        ("!!not a requirement", "UNPARSEABLE"),
    ],
)
def test_unverifiable_lines_fail_closed(tmp_path, line, prefix):
    path = _write(tmp_path, f"Django\n{line}\n")
    problems = checker.check_file(path)
    assert len(problems) == 1 and problems[0].startswith(prefix), problems


def test_empty_or_missing_file_fails_closed(tmp_path):
    empty = _write(tmp_path, "# nothing\n\n", "empty.txt")
    assert checker.check_file(empty)[0].startswith("EMPTY")
    assert _run(tmp_path / "nope.txt").returncode == 1


def test_repo_requirements_file_parses_cleanly():
    # Every line of the real file must be parseable; installation is CI's concern.
    _reqs, problems = checker.parse_requirements(ROOT / "requirements.txt")
    assert problems == []
    names = {r.name.lower() for _, r in _reqs}
    assert "pillow" in names and "django" in names


# ------------------------------------------------------------- deploy.sh order


def _real_deploy_body() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def test_deploy_installs_and_checks_before_migrate_probe_and_flip():
    text = _real_deploy_body()
    pip_at = text.find("-m pip install")
    check_at = text.find("scripts/check_requirements_installed.py requirements.txt")
    migrate_at = text.find("manage.py migrate --noinput")
    probe_at = text.find("Health-probing the NEW release")
    flip_at = text.find("==> Flipping 'current'")
    for name, at in [("pip", pip_at), ("check", check_at), ("migrate", migrate_at),
                     ("probe", probe_at), ("flip", flip_at)]:
        assert at != -1, f"deploy.sh lost its {name} step"
    assert pip_at < check_at < migrate_at < probe_at < flip_at


def _real_step_block() -> str:
    """The NON-dry-run 4b heredoc that runs on the box."""
    text = _real_deploy_body()
    start = text.find('echo "==> Installing + verifying Python requirements')
    assert start != -1, "deploy.sh lost the real requirements step"
    end = text.find("} | remote_sh", start)
    return text[start:end]


def _if_statements(block: str):
    """(condition, then-body) for every `if ! ...; then ... fi` in the block."""
    return re.findall(r"^if ! (.*?)then\n(.*?)^fi$", block, flags=re.S | re.M)


@pytest.mark.parametrize(
    "marker",
    [
        r"-m pip install --dry-run --report",  # upgrade preview
        r"--upgrade-preview",  # preview verdict
        r"-m pip install \\\n",  # the real install (continues on the next line)
        r"scripts/check_requirements_installed\.py requirements\.txt",  # final check
    ],
)
def test_each_real_step_is_guarded_and_aborts(marker):
    stmts = [(c, b) for c, b in _if_statements(_real_step_block()) if re.search(marker, c)]
    assert len(stmts) == 1, f"step {marker!r} is not inside its own `if ! ...; then` guard"
    cond, body = stmts[0]
    assert not re.search(r"\|\|", cond), f"step {marker!r} has its failure swallowed: {cond!r}"
    assert re.search(r"^\s*exit 1\s*$", body, flags=re.M), f"step {marker!r} no longer aborts"


def test_real_pip_commands_never_upgrade():
    for cond, _body in _if_statements(_real_step_block()):
        if "-m pip install" in cond:
            assert "--upgrade" not in cond and " -U" not in cond
            assert "-r requirements.txt" in cond


def test_real_step_uses_mktemp_not_a_fixed_tmp_path():
    block = _real_step_block()
    assert 'PIP_LOG="$(mktemp)"' in block and 'PIP_REPORT="$(mktemp)"' in block
    assert re.search(r"trap 'rm -f \"\$PIP_LOG\" \"\$PIP_REPORT\"' EXIT", block)
    assert "/tmp/" not in block


# ------------------------------------------------------------ upgrade preview


def _report(tmp_path: Path, items: list[tuple[str, str]]) -> Path:
    import json

    data = {"version": "1", "install": [{"metadata": {"name": n, "version": v}} for n, v in items]}
    return _write(tmp_path, json.dumps(data), "report.json")


def test_upgrade_preview_allows_new_installs_only(tmp_path, monkeypatch):
    monkeypatch.delenv("DEPLOY_ALLOW_UPGRADE", raising=False)
    path = _report(tmp_path, [(MISSING_PKG, "1.0"), ("Django", metadata.version("Django"))])
    assert checker.upgrade_preview(path, allow=False) == 0


def test_upgrade_preview_refuses_a_changed_installed_version(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DEPLOY_ALLOW_UPGRADE", raising=False)
    old = metadata.version("Django")
    path = _report(tmp_path, [("Django", "99.0"), (MISSING_PKG, "1.0")])
    assert checker.upgrade_preview(path, allow=False) == 1
    out = capsys.readouterr().out
    assert f"UPGRADE Django {old} -> 99.0" in out
    assert MISSING_PKG not in out


def test_upgrade_preview_allowed_by_env_or_flag(tmp_path, monkeypatch):
    path = _report(tmp_path, [("Django", "99.0")])
    monkeypatch.setenv("DEPLOY_ALLOW_UPGRADE", "1")
    assert checker.upgrade_preview(path, allow=False) == 0
    monkeypatch.delenv("DEPLOY_ALLOW_UPGRADE")
    assert checker.upgrade_preview(path, allow=True) == 0


def test_upgrade_preview_fails_closed_on_bad_report(tmp_path, monkeypatch):
    monkeypatch.delenv("DEPLOY_ALLOW_UPGRADE", raising=False)
    assert checker.upgrade_preview(_write(tmp_path, "not json", "r.json"), allow=False) == 1
    bad = _write(tmp_path, '{"install": [{"metadata": {}}]}', "r2.json")
    assert checker.upgrade_preview(bad, allow=False) == 1


def test_upgrade_preview_cli(tmp_path):
    path = _report(tmp_path, [("Django", "99.0")])
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--upgrade-preview", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "DEPLOY_ALLOW_UPGRADE": "0"},
    )
    assert result.returncode == 1 and "UPGRADE Django" in result.stdout
