"""The CI contract-doc drift gate (scripts/check_contract_docs.py).

An integration adapter and the doc describing its contract must move together — a doc
that silently rots is worse than no doc, because the next person trusts it. These tests
pin the gate's decision logic so the gate itself can't quietly stop working.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "check_contract_docs.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_contract_docs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()


def test_script_exists_and_is_wired_into_ci():
    assert SCRIPT.exists(), "the gate script must exist for CI to call it"
    ci = (BASE_DIR / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "check_contract_docs.py" in ci, "gate must be invoked from CI"
    assert "fetch-depth: 0" in ci, "gate diffs against a merge base — needs full history"


# --- the core rule: code without doc FAILS -------------------------------

def test_wati_adapter_change_without_doc_fails():
    v = gate.evaluate(["apps/integrations/wati/adapter.py"])
    assert v, "changing the Wati adapter with no Wati-GoRefer/ change must fail"
    assert "Wati" in v[0]
    assert "Wati-GoRefer/" in v[0]


def test_zoho_adapter_change_without_doc_fails():
    v = gate.evaluate(["apps/integrations/zoho/ingest.py"])
    assert v and "Zoho-GoRefer/" in v[0]


def test_both_adapters_changed_without_docs_reports_both():
    v = gate.evaluate(
        ["apps/integrations/wati/adapter.py", "apps/integrations/zoho/webhook.py"]
    )
    assert len(v) == 2


# --- satisfied cases PASS -------------------------------------------------

def test_wati_change_with_matching_doc_passes():
    assert not gate.evaluate(
        [
            "apps/integrations/wati/adapter.py",
            "Wati-GoRefer/Wati-Integration-Contract.md",
        ]
    )


def test_zoho_change_with_matching_doc_passes():
    assert not gate.evaluate(
        ["apps/integrations/zoho/webhook.py", "Zoho-GoRefer/Zoho-Integration-Contract.md"]
    )


def test_the_pairing_is_per_vendor_not_interchangeable():
    """A Wati doc does NOT satisfy a Zoho code change — otherwise the gate would be
    trivially bypassable by touching whichever doc is convenient."""
    v = gate.evaluate(
        ["apps/integrations/zoho/ingest.py", "Wati-GoRefer/Wati-Integration-Contract.md"]
    )
    assert v and "Zoho" in v[0]


def test_unrelated_code_change_passes():
    assert not gate.evaluate(["apps/dashboard/views.py", "README.md"])


def test_empty_changeset_passes():
    assert not gate.evaluate([])


# --- the escape hatch -----------------------------------------------------

def test_skip_token_in_commit_message_bypasses():
    v = gate.evaluate(
        ["apps/integrations/wati/adapter.py"],
        messages="fix: correct a typo in a docstring\n\n[skip-contract-doc]",
    )
    assert not v, "the documented escape hatch must work"


def test_skip_token_absent_still_fails():
    v = gate.evaluate(
        ["apps/integrations/wati/adapter.py"], messages="fix: real behaviour change"
    )
    assert v


# --- noise that must not trigger the gate ---------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "apps/integrations/wati/__pycache__/adapter.cpython-313.pyc",
        "apps/integrations/zoho/adapter.pyc",
    ],
)
def test_compiled_artifacts_ignored(path):
    assert not gate.evaluate([path])


def test_failure_message_names_the_doc_to_update():
    """The message has to tell the developer exactly what to do — a gate that only
    says 'failed' trains people to reach for the escape hatch."""
    msg = gate.evaluate(["apps/integrations/wati/adapter.py"])[0]
    assert "Wati-GoRefer/Wati-Integration-Contract.md" in msg
    assert gate.SKIP_TOKEN in msg
