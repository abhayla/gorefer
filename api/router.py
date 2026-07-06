"""Django Ninja API root.

M1 mounts the API with a single health endpoint so the JSON layer is wired and
CI can assert it responds. Later missions add routers (redirect resolver support,
leads, share) — each as its own Ninja router added here.
"""
from __future__ import annotations

from ninja import NinjaAPI

from gorefer.flags import flags

api = NinjaAPI(title="GoRefer API", version="0.1.0", description="GoRefer referral intelligence API")


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
