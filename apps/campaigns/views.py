"""Campaigns admin CRUD (T-124 W1) — `/admin-panel/campaigns`.

Same staff-only auth convention as `apps.dashboard.views` (`login_required` +
`is_staff`), tenant-scoped like every other admin surface (ADR-023 isolation).
Server-rendered Django templates + HTMX partial swaps for the step ladder
(add/remove/reorder) — no React/SPA, no new JS dependency (ADR-024).

This module is CONFIGURATION CRUD ONLY. It reads/writes `MessagingCampaign` /
`MessagingCampaignStep` rows and nothing else — no sending/scheduling/enqueueing
logic, and no import from `apps/integrations/**`.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.tenants.resolve import get_current_tenant

from .models import (
    WEEKDAY_LABELS,
    MessagingCampaign,
    MessagingCampaignStep,
    days_from_mask,
    days_mask_from_codes,
)


def _staff_required(view):
    """Gate a view behind login + is_staff — mirrors apps.dashboard.views._staff_required
    (kept local rather than imported to avoid a dashboard<->campaigns import coupling
    for a two-line helper)."""
    return login_required(
        user_passes_test(lambda u: u.is_staff, login_url="dashboard_login")(view),
        login_url="dashboard_login",
    )


def _campaign_or_404(tenant, campaign_id: int) -> MessagingCampaign:
    return get_object_or_404(MessagingCampaign.objects.for_tenant(tenant), id=campaign_id)


def _checkbox(data, name: str) -> bool:
    return (data.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_mobiles(raw: str) -> list[str]:
    """One mobile per line/comma, blank-stripped, empty entries dropped."""
    if not raw:
        return []
    parts: list[str] = []
    for chunk in raw.replace(",", "\n").splitlines():
        v = chunk.strip()
        if v:
            parts.append(v)
    return parts


def _campaign_view_ctx(tenant, campaign: MessagingCampaign) -> dict:
    return {
        "campaign": campaign,
        "steps": campaign.steps.all().order_by("order"),
        "weekday_labels": WEEKDAY_LABELS,
        "selected_days": set(days_from_mask(campaign.send_days_mask)),
        "manual_include_text": "\n".join(campaign.manual_include_mobiles or []),
        "manual_exclude_text": "\n".join(campaign.manual_exclude_mobiles or []),
        "language_map_rows": sorted((campaign.language_template_map or {}).items()),
    }


@_staff_required
def campaign_list(request):
    """List view: slug, name, enabled, step count."""
    tenant = get_current_tenant(request)
    campaigns = (
        MessagingCampaign.objects.for_tenant(tenant)
        .order_by("name", "id")
        .prefetch_related("steps")
    )
    rows = [
        {"campaign": c, "step_count": c.steps.count()}
        for c in campaigns
    ]
    return render(request, "campaigns/list.html", {"rows": rows, "nav_active": "campaigns"})


@_staff_required
@require_http_methods(["GET", "POST"])
def campaign_edit(request, campaign_id: int):
    """Edit one campaign: switch, eligibility, budgets, send-days/hour, template map.

    The step ladder itself is edited via the HTMX partial endpoints below — this view
    only owns the campaign-level fields.
    """
    tenant = get_current_tenant(request)
    campaign = _campaign_or_404(tenant, campaign_id)
    notices: list[str] = []
    saved = False

    if request.method == "POST":
        data = request.POST
        errors: list[str] = []

        name = (data.get("name") or "").strip() or campaign.name
        enabled = _checkbox(data, "enabled")
        exclude_converted = _checkbox(data, "exclude_converted")

        try:
            min_records = int(data.get("min_records") or 0)
            if min_records < 0:
                raise ValueError
        except ValueError:
            errors.append("“Minimum records” must be a non-negative whole number.")
            min_records = None

        window_raw = (data.get("activity_window_days") or "").strip()
        if window_raw == "":
            activity_window_days = None
        else:
            try:
                activity_window_days = int(window_raw)
                if activity_window_days < 0:
                    raise ValueError
            except ValueError:
                errors.append("“Activity window (days)” must be a non-negative whole number.")
                activity_window_days = None

        budgets = {}
        for field, label in (
            ("max_msgs_per_24h", "Max messages / 24h"),
            ("max_msgs_per_72h", "Max messages / 72h"),
            ("max_msgs_per_7d", "Max messages / 7d"),
        ):
            try:
                val = int(data.get(field))
                if val < 0:
                    raise ValueError
                budgets[field] = val
            except (TypeError, ValueError):
                errors.append(f"“{label}” must be a non-negative whole number.")

        try:
            send_hour_ist = int(data.get("send_hour_ist"))
            if not (0 <= send_hour_ist <= 23):
                raise ValueError
        except (TypeError, ValueError):
            errors.append("“Send hour (IST)” must be 0-23.")
            send_hour_ist = None

        selected_days = data.getlist("send_days") if hasattr(data, "getlist") else data.get("send_days", [])
        try:
            send_days_mask = days_mask_from_codes(selected_days) if selected_days else 0
        except (TypeError, ValueError):
            errors.append("Send-days selection was invalid.")
            send_days_mask = None

        anchor_event_key = (data.get("anchor_event_key") or "").strip()
        manual_include_mobiles = _clean_mobiles(data.get("manual_include_mobiles", ""))
        manual_exclude_mobiles = _clean_mobiles(data.get("manual_exclude_mobiles", ""))

        # Language -> template map, submitted as parallel lists of lang/template rows,
        # plus the "add new language" row.
        langs = data.getlist("lang_code") if hasattr(data, "getlist") else data.get("lang_code", [])
        names = data.getlist("lang_template") if hasattr(data, "getlist") else data.get("lang_template", [])
        new_map: dict[str, str] = {}
        for lang, tmpl in zip(langs, names):
            lang = (lang or "").strip().lower()
            tmpl = (tmpl or "").strip()
            if lang and tmpl:
                new_map[lang] = tmpl

        if errors:
            # No partial save: any invalid field rejects the WHOLE submission, and the
            # form re-renders the campaign's UNCHANGED stored values.
            notices.extend(errors)
        else:
            campaign.name = name
            campaign.enabled = enabled
            campaign.exclude_converted = exclude_converted
            campaign.min_records = min_records
            campaign.activity_window_days = activity_window_days
            for field, val in budgets.items():
                setattr(campaign, field, val)
            campaign.send_hour_ist = send_hour_ist
            campaign.send_days_mask = send_days_mask
            campaign.anchor_event_key = anchor_event_key
            campaign.manual_include_mobiles = manual_include_mobiles
            campaign.manual_exclude_mobiles = manual_exclude_mobiles
            campaign.language_template_map = new_map
            try:
                campaign.clean()  # bounds-checks send_hour_ist / send_days_mask
            except ValidationError as exc:
                notices.append("Some values could not be validated and were not saved: " + "; ".join(
                    f"{field}: {', '.join(msgs)}" for field, msgs in exc.message_dict.items()
                ))
            else:
                campaign.save()
                saved = True

    ctx = _campaign_view_ctx(tenant, campaign)
    ctx.update({"notices": notices, "saved": saved, "nav_active": "campaigns"})
    return render(request, "campaigns/edit.html", ctx)


# --------------------------------------------------------------- step ladder (HTMX)


@_staff_required
@require_http_methods(["POST"])
def step_add(request, campaign_id: int):
    tenant = get_current_tenant(request)
    campaign = _campaign_or_404(tenant, campaign_id)
    with transaction.atomic():
        max_order = campaign.steps.order_by("-order").values_list("order", flat=True).first() or 0
        MessagingCampaignStep.objects.create(
            tenant=tenant,
            campaign=campaign,
            order=max_order + 1,
            gap_days_from_previous=1,
            language="en",
            template_role="",
            template_name="",
            enabled=True,
        )
    return render(request, "campaigns/partials/steps.html", _campaign_view_ctx(tenant, campaign))


@_staff_required
@require_http_methods(["POST"])
def step_remove(request, campaign_id: int, step_id: int):
    tenant = get_current_tenant(request)
    campaign = _campaign_or_404(tenant, campaign_id)
    step = get_object_or_404(MessagingCampaignStep.objects.for_tenant(tenant), id=step_id, campaign=campaign)
    with transaction.atomic():
        removed_order = step.order
        step.delete()
        # Re-number remaining steps to keep a dense, gap-free order sequence.
        for s in campaign.steps.filter(order__gt=removed_order).order_by("order"):
            s.order -= 1
            s.save(update_fields=["order"])
    return render(request, "campaigns/partials/steps.html", _campaign_view_ctx(tenant, campaign))


@_staff_required
@require_http_methods(["POST"])
def step_move(request, campaign_id: int, step_id: int, direction: str):
    if direction not in {"up", "down"}:
        raise Http404("unknown direction")
    tenant = get_current_tenant(request)
    campaign = _campaign_or_404(tenant, campaign_id)
    step = get_object_or_404(MessagingCampaignStep.objects.for_tenant(tenant), id=step_id, campaign=campaign)
    with transaction.atomic():
        neighbour_order = step.order - 1 if direction == "up" else step.order + 1
        neighbour = campaign.steps.filter(order=neighbour_order).first()
        if neighbour is not None:
            # Swap through a temporary sentinel order (beyond any real order in this
            # campaign) to dodge the (campaign, order) unique constraint while both
            # rows are mid-save. order is a PositiveIntegerField, so the sentinel must
            # stay positive — a negative placeholder trips the DB CHECK constraint.
            this_order, that_order = step.order, neighbour.order
            max_order = campaign.steps.order_by("-order").values_list("order", flat=True).first() or 0
            step.order = max_order + 1
            step.save(update_fields=["order"])
            neighbour.order = this_order
            neighbour.save(update_fields=["order"])
            step.order = that_order
            step.save(update_fields=["order"])
    return render(request, "campaigns/partials/steps.html", _campaign_view_ctx(tenant, campaign))


@_staff_required
@require_http_methods(["POST"])
def step_update(request, campaign_id: int, step_id: int):
    """Update one step's gap/language/template/role/enabled fields (HTMX partial swap)."""
    tenant = get_current_tenant(request)
    campaign = _campaign_or_404(tenant, campaign_id)
    step = get_object_or_404(MessagingCampaignStep.objects.for_tenant(tenant), id=step_id, campaign=campaign)
    data = request.POST
    ctx = _campaign_view_ctx(tenant, campaign)

    try:
        gap = int(data.get("gap_days_from_previous"))
        if gap < 0:
            raise ValueError
    except (TypeError, ValueError):
        # No partial save: reject the whole row edit and re-render the UNCHANGED
        # stored values, with the error surfaced on the partial.
        ctx["step_error"] = f"Step #{step.order}: gap must be a non-negative whole number — not saved."
        return render(request, "campaigns/partials/steps.html", ctx)

    step.gap_days_from_previous = gap
    step.language = (data.get("language") or step.language or "en").strip().lower()[:5] or "en"
    step.template_role = (data.get("template_role") or "").strip()
    step.template_name = (data.get("template_name") or "").strip()
    step.enabled = _checkbox(data, "enabled")
    step.save()

    return render(request, "campaigns/partials/steps.html", _campaign_view_ctx(tenant, campaign))
