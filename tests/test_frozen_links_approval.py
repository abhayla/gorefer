"""The owner-approval gate for frozen links (scripts/check_frozen_links_approval.py).

Static (no database): builds throwaway git repos and fakes the GitHub API.
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = ROOT / "scripts" / "check_frozen_links_approval.py"
_spec = importlib.util.spec_from_file_location("approval", _SCRIPT)
approval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(approval)

BASE_REGISTER = {
    "public_host": "gorefer.in", "prod_flags": {"F": True}, "prod_settings": {"landing_mode": "direct"},
    "links": [
        {"path": "/open", "ua": "human", "expect": {"kind": "redirect", "location": "https://z/?c=X"}},
        {"path": "/r/AB1234", "ua": "human", "expect": {"kind": "redirect", "location": "https://z/?c=X&r=AB1234"}},
    ],
}


def _run(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _run(tmp_path, "init", "-q", "-b", "main")
    _run(tmp_path, "config", "user.email", "t@example.com")
    _run(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs/links").mkdir(parents=True)
    (tmp_path / approval.REGISTER).write_text(json.dumps(BASE_REGISTER))
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-qm", "base")
    _run(tmp_path, "checkout", "-qb", "pr")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit(repo, register=None, files=None):
    if register is not None:
        (repo / approval.REGISTER).write_text(json.dumps(register))
    for name, text in (files or {}).items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "change")


def test_adding_an_entry_needs_no_approval(repo):
    reg = json.loads(json.dumps(BASE_REGISTER))
    reg["links"].append({"path": "/new", "ua": "human", "expect": {"kind": "page", "page": "x.html"}})
    _commit(repo, reg)
    assert approval.protected_changes("main") == []


def test_an_ordinary_code_change_needs_no_approval(repo):
    _commit(repo, files={"apps/x.py": "print(1)\n"})
    assert approval.protected_changes("main") == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda r: r["links"].pop(0), "removed: /open [human]"),
    (lambda r: r["links"][1]["expect"].update(location="https://z/?c=X"), "changed: /r/AB1234 [human]"),
    (lambda r: r["prod_settings"].update(landing_mode="page"), "'prod_settings' changed"),
    (lambda r: r["prod_flags"].update(F=False), "'prod_flags' changed"),
])
def test_changing_or_removing_needs_approval(repo, mutate, needle):
    reg = json.loads(json.dumps(BASE_REGISTER))
    mutate(reg)
    _commit(repo, reg)
    reasons = approval.protected_changes("main")
    assert any(needle in r for r in reasons), reasons


@pytest.mark.parametrize("gate_file", [f for f in approval.GATE_FILES if f != approval.REGISTER])
def test_touching_the_gate_itself_needs_approval(repo, gate_file):
    _commit(repo, files={gate_file: "weakened\n"})
    assert approval.protected_changes("main") == [f"gate file changed: {gate_file}"]


def test_deleting_the_register_needs_approval(repo):
    (repo / approval.REGISTER).unlink()
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "rm")
    assert approval.protected_changes("main") == [f"{approval.REGISTER} was deleted"]


# --- who added the label ------------------------------------------------------------

def _fake_api(monkeypatch, *, labels, events, commit_date="2026-11-27T10:00:00Z"):
    def api(path):
        if path.endswith("/pulls/7"):
            return {"labels": [{"name": n} for n in labels]}
        if "/pulls/7/commits" in path:
            return [{"commit": {"committer": {"date": commit_date}}}]
        if "/issues/7/events" in path:
            return events
        raise AssertionError(path)
    monkeypatch.setattr(approval, "_api", api)


def _event(actor="abhayla", app=None, at="2026-11-27T11:00:00Z", name=approval.LABEL):
    return {"event": "labeled", "label": {"name": name}, "actor": {"login": actor},
            "performed_via_github_app": {"slug": app} if app else None, "created_at": at}


def test_owner_label_by_hand_after_the_last_commit_approves(monkeypatch):
    _fake_api(monkeypatch, labels=[approval.LABEL], events=[_event()])
    assert approval.approval_status("o/r", 7, "abhayla")[0] is True


@pytest.mark.parametrize("labels,events,why", [
    ([], [], "does not carry"),
    ([approval.LABEL], [_event(actor="someone-else")], "not by the approver"),
    ([approval.LABEL], [_event(app="claude")], "through the app"),
    ([approval.LABEL], [_event(at="2026-11-27T09:00:00Z")], "predates the latest commit"),
])
def test_anything_else_is_refused(monkeypatch, labels, events, why):
    _fake_api(monkeypatch, labels=labels, events=events)
    ok, explanation = approval.approval_status("o/r", 7, "abhayla")
    assert ok is False and why in explanation
