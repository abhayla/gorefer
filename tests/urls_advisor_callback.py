"""Test URLConf: the prod tree PLUS a standalone mount of the T-097 callback-request
router at /api/callback-request/, bypassing the `ENABLE_ADVISOR_CALLBACK` env-time
gate in api/router.py (which is read once at process import, so it can't be flipped
per-test — Constitution §4, no dead route when off). Mirrors the trick used by
tests/urls_share_intent.py / urls_records_link.py, but a Ninja sub-API rather than a
single Django view, since `/api/` is one NinjaAPI instance mounted at import time.

Django's resolver falls through to the NEXT top-level urlpattern when an included
urlconf's sub-resolver raises Resolver404, so appending this AFTER `base_urlpatterns`
is enough: the prod `/api/` NinjaAPI (router absent, flag off) 404s internally for
`callback-request/...`, and resolution continues to this module's own `/api/` mount.
Used via `@pytest.mark.urls("tests.urls_advisor_callback")`.
"""
from django.urls import path
from ninja import NinjaAPI

from api.callback_request import router as callback_request_router
from gorefer.urls import urlpatterns as base_urlpatterns

_test_api = NinjaAPI(urls_namespace="callback_request_test")
_test_api.add_router("/callback-request", callback_request_router)

urlpatterns = [
    *base_urlpatterns,
    path("api/", _test_api.urls),
]
