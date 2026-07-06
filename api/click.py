"""Click-confirmation beacon (STUB for M2; full counting logic is M4).

The branded pages fire POST /api/click/confirm after render to mark a click as a
confirmed human (Gap 16). M2 only stubs the endpoint so the contract exists; the
nonce validation + is_confirmed_human promotion + unique-visitor counting land in
M4. The stub deliberately does NOT flip is_confirmed_human yet (no fabrication).
"""
from __future__ import annotations

from ninja import Router, Schema

router = Router()


class ConfirmIn(Schema):
    visitor_id: str | None = None


class ConfirmOut(Schema):
    status: str


@router.post("/confirm", response=ConfirmOut)
def confirm_click(request, payload: ConfirmIn):
    # M2 stub: acknowledge only. Human-confirmation counting is implemented in M4.
    return {"status": "accepted"}
