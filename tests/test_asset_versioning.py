"""static_v cache-buster: the CSS/JS URL carries a content-hash query so a changed
asset is a NEW url no browser has cached — the fix for stale browser caches serving an
old app.css after a deploy (the toggle-CSS-invisible-until-purge incident)."""
import re

from django.template import Context, Template

from apps.config.templatetags import assetver


def _render(path: str) -> str:
    return Template("{% load assetver %}{% static_v '" + path + "' %}").render(Context({}))


def test_static_v_appends_content_hash():
    url = _render("css/app.css")
    assert url.startswith("/static/css/app.css?v=")
    ver = url.split("?v=")[1]
    assert re.fullmatch(r"[0-9a-f]{8}", ver), f"expected an 8-char hex hash, got {ver!r}"


def test_static_v_hash_changes_with_content(tmp_path, monkeypatch):
    """Different bytes → different version, so an updated asset busts the browser cache."""
    assetver._HASH_CACHE.clear()
    (tmp_path / "css").mkdir()
    f = tmp_path / "css" / "probe.css"
    f.write_text("a{color:red}", encoding="utf-8")
    monkeypatch.setattr(assetver.finders, "find", lambda p: str(tmp_path / p))
    v1 = assetver.static_v("css/probe.css").split("?v=")[1]
    assetver._HASH_CACHE.clear()
    f.write_text("a{color:blue}", encoding="utf-8")
    v2 = assetver.static_v("css/probe.css").split("?v=")[1]
    assert v1 != v2


def test_static_v_falls_back_when_missing(monkeypatch):
    """A missing file → plain static url (no crash, no bogus ?v=)."""
    assetver._HASH_CACHE.clear()
    monkeypatch.setattr(assetver.finders, "find", lambda p: None)
    monkeypatch.setattr(assetver, "settings", type("S", (), {"STATIC_ROOT": None})())
    url = assetver.static_v("css/does-not-exist.css")
    assert "?v=" not in url
