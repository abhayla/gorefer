"""Follow-up engine CRUD API (Django Ninja, tenant-scoped, staff-only).

Doc 14 §C: "admin + API now; the permission-scoped in-product page later." This is the
programmatic surface — rule CRUD (the cadence) + instance CRUD (one contact's pending
follow-up: cancel / reschedule while SCHEDULED, immutable once SENT).

NB — framework: doc 14 §4 said "DRF CRUD", but the LOCKED stack (ADR-024) is Django Ninja
and DRF is not installed. Building on Ninja to match every other `api/*` router is following
the locked ADR over a loose word in a DESIGN-status doc — surfaced in COORDINATION for DA
confirmation, not a silent pick.

Auth: staff session user only, via `apps.common.api_auth.staff_session_auth` — a
`SessionAuth` subclass, so every unsafe method (POST/PATCH/DELETE) is CSRF-checked as
well as session-authed. It replaced a plain-callable auth that authenticated the cookie
but checked no CSRF token, which left this CRUD surface forgeable from any page a
logged-in staff member visited (T-047, 2026-08-06). Every query is tenant-scoped, so one
AP can never see or edit another's rules/rows (ADR-023 isolation).
"""
from __future__ import annotations

from datetime import datetime

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.api_auth import staff_session_auth
from apps.tenants.resolve import get_current_tenant

from .models import FollowupRule, ScheduledFollowup

router = Router(auth=staff_session_auth)


# --- Schemas ------------------------------------------------------------------

class RuleIn(Schema):
    step_key: str
    offset_minutes: int
    channel: str = FollowupRule.CHANNEL_SESSION
    template_name: str = ""
    body_en: str = ""
    body_hi: str = ""
    enabled: bool = True
    only_if_window_open: bool = True
    stop_on_reply: bool = True
    order: int = 100


class RuleUpdate(Schema):
    step_key: str | None = None
    offset_minutes: int | None = None
    channel: str | None = None
    template_name: str | None = None
    body_en: str | None = None
    body_hi: str | None = None
    enabled: bool | None = None
    only_if_window_open: bool | None = None
    stop_on_reply: bool | None = None
    order: int | None = None


class RuleOut(Schema):
    id: int
    step_key: str
    offset_minutes: int
    channel: str
    template_name: str
    body_en: str
    body_hi: str
    enabled: bool
    only_if_window_open: bool
    stop_on_reply: bool
    order: int


class ScheduledOut(Schema):
    id: int
    mobile: str
    rule_id: int
    status: str
    fire_at: datetime
    window_opened_at: datetime
    sent_at: datetime | None = None
    reason: str


class RescheduleIn(Schema):
    fire_at: str  # ISO-8601


# --- Rule CRUD ----------------------------------------------------------------

@router.get("/rules", response=list[RuleOut])
def list_rules(request):
    tenant = get_current_tenant(request)
    return list(FollowupRule.objects.for_tenant(tenant).order_by("order", "id"))


@router.post("/rules", response={201: RuleOut})
def create_rule(request, payload: RuleIn):
    tenant = get_current_tenant(request)
    if payload.channel not in {FollowupRule.CHANNEL_SESSION, FollowupRule.CHANNEL_TEMPLATE}:
        raise HttpError(422, "channel must be 'session' or 'template'")
    if FollowupRule.objects.for_tenant(tenant).filter(step_key=payload.step_key).exists():
        raise HttpError(409, f"a rule with step_key '{payload.step_key}' already exists")
    rule = FollowupRule.objects.create(tenant=tenant, **payload.dict())
    return 201, rule


@router.get("/rules/{rule_id}", response=RuleOut)
def get_rule(request, rule_id: int):
    return _get_rule_or_404(request, rule_id)


@router.patch("/rules/{rule_id}", response=RuleOut)
def update_rule(request, rule_id: int, payload: RuleUpdate):
    rule = _get_rule_or_404(request, rule_id)
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if "channel" in data and data["channel"] not in {
        FollowupRule.CHANNEL_SESSION, FollowupRule.CHANNEL_TEMPLATE
    }:
        raise HttpError(422, "channel must be 'session' or 'template'")
    for key, value in data.items():
        setattr(rule, key, value)
    rule.save()
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(request, rule_id: int):
    rule = _get_rule_or_404(request, rule_id)
    # PROTECT on ScheduledFollowup.rule blocks deleting a rule with history; cancel its
    # pending rows first so a deleted step stops firing (doc 14 §3: delete a step →
    # its pending rows CANCELLED) without violating the FK.
    ScheduledFollowup.objects.filter(
        rule=rule, status=ScheduledFollowup.STATUS_SCHEDULED
    ).update(status=ScheduledFollowup.STATUS_CANCELLED, reason="rule deleted")
    if ScheduledFollowup.objects.filter(rule=rule).exists():
        # History exists — disable instead of a hard delete (keeps the audit trail).
        rule.enabled = False
        rule.save(update_fields=["enabled", "updated_at"])
        return {"deleted": False, "disabled": True,
                "detail": "rule has history; disabled and pending rows cancelled"}
    rule.delete()
    return {"deleted": True}


# --- Instance CRUD (one contact's scheduled follow-up) ------------------------

@router.get("/scheduled", response=list[ScheduledOut])
def list_scheduled(request, status: str | None = None, mobile: str | None = None):
    tenant = get_current_tenant(request)
    qs = ScheduledFollowup.objects.for_tenant(tenant)
    if status:
        qs = qs.filter(status=status)
    if mobile:
        qs = qs.filter(mobile=mobile)
    return list(qs.order_by("-fire_at")[:500])


@router.post("/scheduled/{sf_id}/cancel", response=ScheduledOut)
def cancel_scheduled(request, sf_id: int):
    sf = _get_scheduled_or_404(request, sf_id)
    if sf.status != ScheduledFollowup.STATUS_SCHEDULED:
        raise HttpError(409, f"cannot cancel a follow-up in status '{sf.status}'")
    sf.status = ScheduledFollowup.STATUS_CANCELLED
    sf.reason = "cancelled via API"
    sf.save(update_fields=["status", "reason", "updated_at"])
    return sf


@router.post("/scheduled/{sf_id}/reschedule", response=ScheduledOut)
def reschedule_scheduled(request, sf_id: int, payload: RescheduleIn):
    from django.utils.dateparse import parse_datetime

    sf = _get_scheduled_or_404(request, sf_id)
    if sf.status != ScheduledFollowup.STATUS_SCHEDULED:
        raise HttpError(409, f"cannot reschedule a follow-up in status '{sf.status}'")
    new_fire = parse_datetime(payload.fire_at)
    if new_fire is None:
        raise HttpError(422, "fire_at must be an ISO-8601 datetime")
    sf.fire_at = new_fire
    sf.save(update_fields=["fire_at", "updated_at"])
    return sf


# --- helpers ------------------------------------------------------------------

def _get_rule_or_404(request, rule_id: int) -> FollowupRule:
    tenant = get_current_tenant(request)
    rule = FollowupRule.objects.for_tenant(tenant).filter(id=rule_id).first()
    if rule is None:
        raise HttpError(404, "rule not found")
    return rule


def _get_scheduled_or_404(request, sf_id: int) -> ScheduledFollowup:
    tenant = get_current_tenant(request)
    sf = ScheduledFollowup.objects.for_tenant(tenant).filter(id=sf_id).first()
    if sf is None:
        raise HttpError(404, "scheduled follow-up not found")
    return sf
