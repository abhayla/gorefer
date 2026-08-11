"""Django Ninja API root.

M1 mounts the API with a single health endpoint so the JSON layer is wired and
CI can assert it responds. Later missions add routers (redirect resolver support,
leads, share) — each as its own Ninja router added here.
"""
from __future__ import annotations

from ninja import NinjaAPI

from apps.followups.api import router as followups_router
from apps.integrations.router import wati_router, zoho_router
from gorefer.flags import flags

from .analytics import router as analytics_router
from .callback_request import router as callback_request_router
from .click import router as click_router
from .leads import router as leads_router
from .records_tokens import router as records_tokens_router
from .share import router as share_router

api = NinjaAPI(title="GoRefer API", version="0.1.0", description="GoRefer referral intelligence API")
api.add_router("/click", click_router)
api.add_router("/leads", leads_router)
api.add_router("/share", share_router)
api.add_router("/analytics", analytics_router)
# T-054 token mint — key-authed server-to-server (external senders that carry a
# [Referral Records] / [Refer Link] button cannot compute a signed token themselves).
api.add_router("/records-tokens", records_tokens_router)
api.add_router("/zoho", zoho_router)
api.add_router("/wati", wati_router)
# Follow-up engine CRUD (M-FUP-1) — staff-only, tenant-scoped (auth on the router itself).
api.add_router("/followups", followups_router)
# T-097 advisor callback — mounted only when the flag is on (Constitution §4: no dead route).
if flags.ENABLE_ADVISOR_CALLBACK:
    api.add_router("/callback-request", callback_request_router)


@api.get("/health")
def health(request):
    """Liveness probe. Exposes only non-sensitive build/flag state.

    Deliberately exposes NO partner code, Zerodha URL, or internal id (guardrail 3).
    """
    return {
        "status": "ok",
        "service": "gorefer",
        "demo_mode": flags.ENABLE_DEMO_MODE,
    }
