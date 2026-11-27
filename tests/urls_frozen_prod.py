"""Test URLConf: the REAL gorefer/urls.py, built with production's feature flags ON.

gorefer/urls.py mounts its flag-gated routes (/share, /rr, /hub, login, My Referrals)
at import time from settings.FEATURE_FLAGS. Instead of mirroring that mounting by hand
(which can drift), this module executes the real urls.py source in a fresh module with
the production flag values from the frozen register, then restores the settings.
Used by tests/test_frozen_links.py.
"""
import importlib.util
from pathlib import Path

from django.conf import settings

from apps.referrals.frozen_links import load_register

_URLS = Path(__file__).resolve().parent.parent / "gorefer" / "urls.py"

_saved = dict(getattr(settings, "FEATURE_FLAGS", {}) or {})
settings.FEATURE_FLAGS = {**_saved, **load_register()["prod_flags"]}
try:
    _spec = importlib.util.spec_from_file_location("_frozen_prod_urls", _URLS)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
finally:
    settings.FEATURE_FLAGS = _saved

urlpatterns = _mod.urlpatterns
