"""Frozen shared links — every link a customer was given keeps working (CLAUDE.md §6h).

Owner rule 2026-11-27, strict: "the previous links should never be removed, deleted or
updated. They should continue to work as it is because they have been shared with the
customers." No code OR settings change may alter where an entry of
docs/links/frozen-links.json lands until the owner approves it (the PR label
`link-change-approved`, checked by scripts/check_frozen_links_approval.py).

What this test checks, for EVERY entry, through the REAL URLconf built with
production's feature flags and under production's link settings (both recorded in
the register):
  * the outcome is exactly the frozen one (see apps/referrals/frozen_links.py);
  * every gorefer.in link inside a share message is itself on the register;
  * every public route in gorefer/urls.py is covered by at least one entry, so a new
    route cannot ship without being frozen.

ADDING entries (never needs approval):
    FROZEN_LINKS_ADD="/new/path|human,/new/path|bot" python -m pytest tests/test_frozen_links.py -q
The test observes each new path and APPENDS it. It never rewrites an existing entry:
changing one is a hand edit to the register, which the approval check blocks without
the owner's label. There is deliberately no "update all" switch.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config.cascade import set_tenant
from apps.referrals.frozen_links import REGISTER_PATH, load_register, observe, register_paths
from apps.tenants.resolve import get_bootstrap_tenant

ROOT = Path(__file__).resolve().parent.parent
REGISTER = load_register()

#: Routes that are not links anyone was given: machine and staff surfaces, and the
#: share hub's opening-line form, which only ever receives a POST from the hub page.
NOT_SHARED_PREFIXES = ("/api/", "/admin-panel/", "/django-admin/")
NOT_SHARED_ROUTES = ("/hub/opener", "/hub/<str:token>/opener")
#: A signed, per-referrer token (hub and records links in messages). The test mints a
#: real one for the example referrer, so the frozen outcome is the valid-token page.
RECORDS_TOKEN = "{records_token}"
EXAMPLE_ID = "AB1234"


@pytest.fixture
def prod_like(db, settings):
    """Seeded program + production's link settings + production's feature flags."""
    call_command("seed_program")
    tenant = get_bootstrap_tenant()
    for key, value in REGISTER["prod_settings"].items():
        set_tenant(key, value, tenant_id=tenant.id)
    settings.PUBLIC_BASE_URL = f"https://{REGISTER['public_host']}"
    settings.FEATURE_FLAGS = {**(settings.FEATURE_FLAGS or {}), **REGISTER["prod_flags"]}
    settings.ROOT_URLCONF = "tests.urls_frozen_prod"
    return tenant


def _observe(entry) -> dict:
    from django.core.cache import cache

    cache.clear()  # the per-address rate limits must never decide an outcome
    path = entry["path"]
    if RECORDS_TOKEN in path:
        path = path.replace(RECORDS_TOKEN, _records_token())
    return observe(Client(), path, ua=entry.get("ua", "human"), public_host=REGISTER["public_host"])


def _records_token() -> str:
    from apps.accounts.records_link import mint_records_token
    from apps.referrals.models import ReferralIdentity

    identities = ReferralIdentity.objects.for_tenant(get_bootstrap_tenant())
    identity = identities.filter(client_id=EXAMPLE_ID).first()
    if identity is None:  # a first click creates the referrer, as in production
        observe(Client(), f"/r/{EXAMPLE_ID}", public_host=REGISTER["public_host"])
        identity = identities.get(client_id=EXAMPLE_ID)
    return mint_records_token(identity)


def _key(entry) -> str:
    return f'{entry["path"]} [{entry.get("ua", "human")}]'


@pytest.mark.django_db(transaction=True)
def test_every_frozen_link_still_does_what_it_did(prod_like):
    broken = []
    for entry in REGISTER["links"]:
        got = _observe(entry)
        if got != entry["expect"]:
            broken.append(f"  {_key(entry)}\n    frozen: {entry['expect']}\n    now:    {got}")
    assert not broken, (
        "A link customers were given would now behave differently (CLAUDE.md §6h).\n"
        "Fix the change so these links behave as before. Changing a frozen link needs the\n"
        "owner's explicit approval: the label `link-change-approved` on the PR.\n" + "\n".join(broken)
    )


def test_every_link_inside_a_share_message_is_frozen_too():
    frozen = register_paths(REGISTER)
    missing = sorted({
        f"{link}  (inside the message of {_key(e)})"
        for e in REGISTER["links"] if e["expect"]["kind"] == "share"
        for link in e["expect"]["gorefer_links"] if link not in frozen
    })
    assert not missing, "A shared message carries a link that is not on the register:\n" + "\n".join(missing)


def _public_routes() -> list[str]:
    source = (ROOT / "gorefer" / "urls.py").read_text(encoding="utf-8")
    routes = sorted({"/" + r for r in re.findall(r'\bpath\(\s*"([^"]*)"', source)})
    return [r for r in routes if not r.startswith(NOT_SHARED_PREFIXES) and r not in NOT_SHARED_ROUTES]


def _route_regex(route: str) -> re.Pattern:
    pattern = re.escape(route)
    pattern = re.sub(r"<[^>]*>", "[^/]+", pattern.replace(r"\<", "<").replace(r"\>", ">"))
    return re.compile("^" + pattern + "$")


def test_every_public_route_is_on_the_register():
    paths = {p.replace(RECORDS_TOKEN, "token") for p in register_paths(REGISTER)}
    uncovered = [r for r in _public_routes() if not any(_route_regex(r).match(p) for p in paths)]
    assert not uncovered, (
        "A public route has no frozen entry. Freeze it in this PR (adding needs no approval):\n"
        '  FROZEN_LINKS_ADD="/example/path|human" python -m pytest tests/test_frozen_links.py -q\n'
        + "\n".join(f"  {r}" for r in uncovered)
    )


def test_register_entries_are_unique_and_well_formed():
    keys = [_key(e) for e in REGISTER["links"]]
    assert len(keys) == len(set(keys)), "duplicate register entries"
    for e in REGISTER["links"]:
        assert e["path"].startswith("/") and e.get("ua", "human") in ("human", "bot"), e
        assert e["expect"]["kind"] in ("redirect", "share", "page", "status"), e


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.environ.get("FROZEN_LINKS_ADD"), reason="add mode only")
def test_add_new_entries(prod_like):
    """FROZEN_LINKS_ADD mode: observe and APPEND new paths. Existing entries are untouched."""
    register = load_register()
    existing = {_key(e) for e in register["links"]}
    for item in filter(None, (x.strip() for x in os.environ["FROZEN_LINKS_ADD"].split(","))):
        path, _, ua = item.partition("|")
        entry = {"path": path, "ua": ua or "human"}
        if _key(entry) in existing:
            continue  # never overwrite: changing an entry needs the owner's approval
        entry["expect"] = _observe(entry)
        register["links"].append(entry)
        existing.add(_key(entry))
    REGISTER_PATH.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
