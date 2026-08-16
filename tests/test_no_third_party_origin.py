"""Every user-facing page must settle (reach browser 'idle') on its own origin.

Background: a render-blocking <link rel="stylesheet"> pointing at a third-party
origin (fonts.googleapis.com) held the document in a loading state on any network
where that origin is blackholed rather than refused — the request neither
completes nor errors, so load/idle never fires and the page is undriveable by
automation (and, worse, renders nothing for a real user on such a network).

The fix self-hosts Inter. These tests lock it in: a future edit that re-adds a
CDN/font/analytics link to a public page fails here rather than silently
reintroducing a page that never idles.
"""
import re

import pytest
from django.core.management import call_command
from django.test import Client

# Origins that must never appear in a page's markup. Anything render-blocking
# from a host we don't control can hold the document open indefinitely.
FORBIDDEN_ORIGINS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "cdnjs.cloudflare.com",
    "ajax.googleapis.com",
    "code.jquery.com",
    "googletagmanager.com",
    "google-analytics.com",
    "cdn.tailwindcss.com",
)

# The pages the DA must be able to drive: public landing, disclosure, privacy, admin login.
PUBLIC_PATHS = ("/", "/r/RJ4521", "/d/pifs", "/privacy", "/admin-panel/login/")


@pytest.fixture
def seeded(db):
    call_command("seed_program")


def _bodies(client):
    for path in PUBLIC_PATHS:
        resp = client.get(path, HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
        # Follow the landing-mode 302 so we assert on whatever actually renders.
        if resp.status_code in (301, 302):
            location = resp["Location"]
            if location.startswith("/"):
                resp = client.get(location, HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
            else:
                continue  # external 302 (direct mode -> Zerodha): no document to idle
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        yield path, resp.content.decode()


@pytest.mark.django_db(transaction=True)
def test_no_public_page_references_a_third_party_origin(seeded):
    """No page may pull a subresource from an origin we do not control."""
    for path, body in _bodies(Client()):
        for origin in FORBIDDEN_ORIGINS:
            assert origin not in body, (
                f"{path} references third-party origin {origin!r}. A render-blocking "
                f"third-party subresource can prevent the page from ever reaching idle."
            )


@pytest.mark.django_db(transaction=True)
def test_stylesheets_and_scripts_are_all_same_origin(seeded):
    """Structural form of the rule above: every <link rel=stylesheet> href and
    every <script src> must be a relative/same-origin path, not an absolute URL.

    Catches a new CDN host that isn't in FORBIDDEN_ORIGINS yet.
    """
    link_re = re.compile(r"""<link[^>]+rel=["']stylesheet["'][^>]*>""", re.I)
    href_re = re.compile(r"""href=["']([^"']+)["']""", re.I)
    script_re = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.I)

    for path, body in _bodies(Client()):
        for tag in link_re.findall(body):
            m = href_re.search(tag)
            if m:
                href = m.group(1)
                assert not href.startswith(("http://", "https://", "//")), (
                    f"{path}: stylesheet {href!r} is cross-origin; self-host it so the "
                    f"page can settle without a third party."
                )
        for src in script_re.findall(body):
            assert not src.startswith(("http://", "https://", "//")), (
                f"{path}: script {src!r} is cross-origin; self-host it."
            )


@pytest.mark.django_db(transaction=True)
def test_inter_font_is_self_hosted_and_present(seeded):
    """The design keeps Inter — self-hosted, not dropped. The woff2 must exist and
    actually be served, else we'd have traded a hanging page for a broken font.
    """
    from django.contrib.staticfiles import finders

    found = finders.find("fonts/inter-latin-var.woff2")
    assert found, "self-hosted Inter woff2 is missing from static/fonts/"
    with open(found, "rb") as fh:
        assert fh.read(4) == b"wOF2", "inter-latin-var.woff2 is not a valid woff2 file"

    # And the pages reference it rather than a remote font service.
    for path, body in _bodies(Client()):
        if "@font-face" in body:
            assert "fonts/inter-latin-var.woff2" in body, (
                f"{path} declares @font-face but not the self-hosted Inter"
            )


@pytest.mark.django_db(transaction=True)
def test_no_always_on_polling_on_public_pages(seeded):
    """The other way a page never idles: an unbounded HTMX poll / SSE / websocket.
    Public pages must have none. (An admin screen may poll a fragment; these are
    the pages the DA drives, and they must settle.)
    """
    for path, body in _bodies(Client()):
        assert not re.search(r"""hx-trigger=["'][^"']*every\s""", body, re.I), (
            f"{path} has an always-on HTMX poll (hx-trigger=every ...) — it will never idle."
        )
        for forbidden in ("new EventSource", "new WebSocket", "setInterval("):
            assert forbidden not in body, (
                f"{path} starts a persistent/repeating task ({forbidden}) — it will never idle."
            )
