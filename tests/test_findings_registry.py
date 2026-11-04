"""Findings registry generator (scripts/build_findings_registry.py). No DB."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_findings_registry", ROOT / "scripts" / "build_findings_registry.py")
reg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reg)

GOOD = {
    "slug": "sample-class",
    "title": "Sample class",
    "class_symptom": "Generic symptom.",
    "mechanism": "Generic mechanism.",
    "first_seen": {"date": "2026-11-04", "evidence": ["one instance, 3 of 10 rows"]},
    "measurements": ["query X returned 3 of 10"],
    "detection": {"status": "unguarded", "reason": "no check yet"},
    "related": ["PR #1"],
}


def _setup(tmp_path, data=None, name="sample-class"):
    d = tmp_path / "fc"
    d.mkdir(exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(data or GOOD), encoding="utf-8")
    return d, tmp_path / "FINDINGS.md"


def _run(d, out, *extra):
    return reg.main(["--dir", str(d), "--out", str(out), *extra])


def test_valid_file_renders_every_field(tmp_path):
    d, out = _setup(tmp_path)
    assert _run(d, out) == 0
    text = out.read_text(encoding="utf-8")
    for needle in ("sample-class", "Generic symptom.", "Generic mechanism.",
                   "one instance, 3 of 10 rows", "query X returned 3 of 10",
                   "no check yet", "PR #1", "unguarded"):
        assert needle in text
    assert _run(d, out, "--check") == 0


def test_missing_required_key_fails(tmp_path):
    bad = copy.deepcopy(GOOD)
    del bad["mechanism"]
    d, out = _setup(tmp_path, bad)
    assert _run(d, out) == 1
    assert not out.exists()


def test_bad_status_fails(tmp_path):
    bad = copy.deepcopy(GOOD)
    bad["detection"] = {"status": "maybe"}
    d, out = _setup(tmp_path, bad)
    assert _run(d, out) == 1


def test_guarded_without_check_fails(tmp_path):
    bad = copy.deepcopy(GOOD)
    bad["detection"] = {"status": "guarded"}
    d, out = _setup(tmp_path, bad)
    assert _run(d, out) == 1


def test_stale_aggregate_fails_check(tmp_path):
    d, out = _setup(tmp_path)
    assert _run(d, out) == 0
    changed = copy.deepcopy(GOOD)
    changed["measurements"] = ["query X returned 4 of 10"]
    (d / "sample-class.json").write_text(json.dumps(changed), encoding="utf-8")
    assert _run(d, out, "--check") == 1
    assert _run(d, out) == 0
    assert _run(d, out, "--check") == 0


def test_missing_aggregate_fails_check(tmp_path):
    d, out = _setup(tmp_path)
    assert _run(d, out, "--check") == 1


def test_unknown_extra_key_is_rendered(tmp_path):
    extra = copy.deepcopy(GOOD)
    extra["measurements_extra"] = {"note": "UNIQUE-EXTRA-VALUE"}
    d, out = _setup(tmp_path, extra)
    assert _run(d, out) == 0
    text = out.read_text(encoding="utf-8")
    assert "measurements_extra" in text and "UNIQUE-EXTRA-VALUE" in text


def test_slug_must_match_filename(tmp_path):
    d, out = _setup(tmp_path, GOOD, name="other-name")
    assert _run(d, out) == 1


def test_repo_aggregate_is_current_and_has_seeded_findings():
    assert reg.main(["--check"]) == 0
    text = (ROOT / "docs" / "reviews" / "FINDINGS.md").read_text(encoding="utf-8")
    for slug in ("datacenter-clicks-counted-as-human",
                 "deploy-never-installs-requirements",
                 "beacon-confirmed-human-rare-in-direct-mode",
                 "genericipaddressfield-empty-string-filter-matches-nothing"):
        assert slug in text
