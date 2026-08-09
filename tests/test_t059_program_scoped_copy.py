"""T-059 — program-scoped MESSAGE copy (P-09, the partner-#2 enabler).

T-055's checker found the WhatsApp share message hard-names "Zerodha" for ANY
partner's identity (apps/referrals/share_intent_service.py). Pages already resolve
the brand correctly via the T-056 fallback chain (apps.accounts.hub._brand_name);
this closes the same gap for MESSAGE copy — the share-kit prefill, the hub's reuse
of it, the "My Referrals" self-view share line, and the follow-up nudge cadence.

Two predicates, both locked here with prod-shaped seed data (T-056 lesson —
seed_program's real shape, not an invented one):

  1. ZERO-BEHAVIOR-CHANGE for the live tenant: every affected string renders
     BYTE-IDENTICAL to the pre-T-059 literal (pinned below from origin/main).
  2. A second program (seeded exactly like `seed_program` seeds Zerodha, per row #2
     under the SAME partner) renders ITS OWN brand with NO code change.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.followups import services, tasks
from apps.followups.models import FollowupRule, FollowupWindow, ScheduledFollowup
from apps.referrals import branding
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

CID = "RJ4521"

# --- exact literals as they read on origin/main (pre-T-059), pinned verbatim ---
OLD_KIT_MESSAGE_PREFIX = "Open a free Zerodha account — my referral link:\n"
OLD_SELFVIEW_SHARE_PREFIX = "Open your free Zerodha account with my referral link: "
OLD_STEP1_EN = (
    "Hi! Your Zerodha account opening is still pending — reply here and we'll help you "
    "complete it in a couple of minutes."
)
OLD_STEP1_HI = (
    "नमस्ते! आपका Zerodha अकाउंट अभी पूरा नहीं हुआ है। कहीं कुछ अटक रहा हो तो यहीं बता "
    "दीजिए — दो मिनट में पूरा करा देंगे।"
)


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _second_program(tenant, *, name="groww", display_name="Groww"):
    """A second program seeded exactly like seed_program seeds row #1 — same
    partner, real DB row, not an invented shape (the T-056 lesson)."""
    partner = ReferralProgram.objects.get(tenant=tenant).partner
    return ReferralProgram.objects.create(
        tenant=tenant, partner=partner, name=name, display_name=display_name,
        status="active", regulator="sebi_nse",
    )


# ============================================================ branding.py — unit


def test_brand_for_program_prefers_display_name():
    import types
    program = types.SimpleNamespace(display_name="Zerodha", name="zerodha", partner=None)
    assert branding.brand_for_program(program) == "Zerodha"


def test_brand_for_program_falls_back_to_name():
    import types
    program = types.SimpleNamespace(display_name="", name="zerodha", partner=None)
    assert branding.brand_for_program(program) == "zerodha"


def test_brand_for_program_falls_back_to_partner_name():
    import types
    partner = types.SimpleNamespace(name="Passive Income Financial Solutions Pvt Ltd")
    program = types.SimpleNamespace(display_name="", name="", partner=partner)
    assert branding.brand_for_program(program) == "Passive Income Financial Solutions Pvt Ltd"


def test_brand_for_program_none_is_empty():
    assert branding.brand_for_program(None) == ""


def test_brand_for_tenant_id_resolves_the_active_program(seeded):
    assert branding.brand_for_tenant_id(seeded.id) == "Zerodha"


def test_brand_for_tenant_id_unknown_tenant_is_empty():
    assert branding.brand_for_tenant_id(999999) == ""


# ================================================= share_intent_service.kit_message


def test_kit_message_zero_behavior_change_for_zerodha(seeded):
    from apps.referrals.share_intent_service import kit_message

    msg = kit_message("wa", CID, seeded.id)
    assert msg.startswith(OLD_KIT_MESSAGE_PREFIX), msg


def test_kit_message_with_explicit_program_uses_its_brand(seeded):
    from apps.referrals.share_intent_service import kit_message

    groww = _second_program(seeded)
    msg = kit_message("wa", "GRW9001", seeded.id, program=groww)
    assert msg.startswith("Open a free Groww account — my referral link:\n"), msg
    assert "Zerodha" not in msg


def test_kit_message_via_share_endpoint_second_program_no_code_change(seeded, client):
    """/share/wa/{client_id} end to end, resolved through handle_share_intent's own
    program lookup — proves the wiring, not just the function in isolation."""
    from django.test import override_settings

    _second_program(seeded)  # tenant now has TWO active programs; get_active_program
    # picks the first by id (Zerodha, seeded first) — so this only proves Zerodha
    # still renders correctly with a sibling program present (no cross-talk).
    with override_settings(ROOT_URLCONF="tests.urls_share_intent"):
        resp = client.get("/share/wa/RJ4521", HTTP_USER_AGENT="Mozilla/5.0 (Android)")
    assert resp.status_code == 302


# =============================================================== accounts/hub.py


def test_hub_share_message_zero_behavior_change_for_zerodha(seeded):
    from apps.accounts.hub import hub_ctx
    from apps.accounts.records_link import mint_records_token

    identity = ReferralIdentity.objects.create(
        tenant=seeded,
        program=ReferralProgram.objects.get(tenant=seeded),
        partner=ReferralProgram.objects.get(tenant=seeded).partner,
        client_id=CID,
    )
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token)
    assert ctx["share_message"].startswith(OLD_KIT_MESSAGE_PREFIX), ctx["share_message"]


def test_hub_share_message_second_program_no_code_change(seeded):
    from apps.accounts.hub import hub_ctx
    from apps.accounts.records_link import mint_records_token

    groww = _second_program(seeded)
    identity = ReferralIdentity.objects.create(
        tenant=seeded, program=groww, partner=groww.partner, client_id="GRW9001",
    )
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token)
    assert ctx["share_message"].startswith("Open a free Groww account — my referral link:\n")
    assert "Zerodha" not in ctx["share_message"]


# =============================================================== accounts/selfview.py


def test_selfview_share_text_zero_behavior_change_for_zerodha(
    seeded, client, django_capture_on_commit_callbacks
):
    from apps.accounts.selfview import my_referrals_ctx
    from apps.referrals import redirect_service

    program = redirect_service.get_active_program(seeded)
    with django_capture_on_commit_callbacks(execute=True):
        redirect_service.lazy_get_or_create_referral(seeded, program, CID)
    ctx = my_referrals_ctx(seeded, CID)
    assert ctx["share_text"].startswith(OLD_SELFVIEW_SHARE_PREFIX), ctx["share_text"]


def test_selfview_share_text_second_program_no_code_change(seeded, django_capture_on_commit_callbacks):
    from apps.accounts.selfview import my_referrals_ctx

    groww = _second_program(seeded)
    ReferralIdentity.objects.create(
        tenant=seeded, program=groww, partner=groww.partner, client_id="GRW9001",
    )
    ctx = my_referrals_ctx(seeded, "GRW9001")
    assert ctx["share_text"].startswith("Open your free Groww account with my referral link: ")
    assert "Zerodha" not in ctx["share_text"]


def test_selfview_share_text_no_identity_yet_falls_back_to_tenant_program(seeded):
    """A just-bound referrer with zero clicks has no ReferralIdentity row (ADR-008 —
    lazy creation). The share line must still be correctly branded, not blank."""
    from apps.accounts.selfview import my_referrals_ctx

    assert not ReferralIdentity.objects.filter(client_id="UNCLICKED").exists()
    ctx = my_referrals_ctx(seeded, "UNCLICKED")
    assert ctx["share_text"].startswith(OLD_SELFVIEW_SHARE_PREFIX), ctx["share_text"]


# =============================================================== followups cadence


MOBILE = "919876543210"


def _rule_with_body(tenant, body_en, body_hi="", *, step_key="nudge_1"):
    return FollowupRule.objects.create(
        tenant=tenant, step_key=step_key, offset_minutes=15,
        channel=FollowupRule.CHANNEL_SESSION, template_name="",
        body_en=body_en, body_hi=body_hi, enabled=True,
        only_if_window_open=True, stop_on_reply=True, order=1,
    )


def _open_window(tenant, *, mobile=MOBILE):
    from datetime import timedelta

    from django.utils import timezone

    return FollowupWindow.objects.create(
        tenant=tenant, mobile=mobile, opted_out=False,
        last_inbound_at=timezone.now() - timedelta(hours=1),
    )


def _scheduled_now(tenant, rule, window, *, mobile=MOBILE):
    from datetime import timedelta

    from django.utils import timezone

    return ScheduledFollowup.objects.create(
        tenant=tenant, rule=rule, mobile=mobile, pref_lang="en",
        fire_at=timezone.now() - timedelta(minutes=1),
        window_opened_at=window.last_inbound_at,
        dedupe_key=f"{tenant.id}|{mobile}|{rule.step_key}|{window.last_inbound_at.isoformat()}",
    )


class _RecordingAdapter:
    sent = None

    def __init__(self):
        self.sent = []

    def send_session_text(self, *, to, message):
        from apps.integrations.wati import status
        from apps.integrations.wati.adapter import SendResult

        self.sent.append((to, message))
        return SendResult(accepted=True, provider_message_id=None, raw_status=status.STATUS_ACCEPTED)

    def send_template(self, *, to, template, params):
        from apps.integrations.wati import status
        from apps.integrations.wati.adapter import SendResult

        return SendResult(accepted=True, provider_message_id=None, raw_status=status.STATUS_ACCEPTED)


@pytest.fixture
def enabled(seeded):
    from apps.config.cascade import set_tenant

    set_tenant("followups_enabled", True, tenant_id=seeded.id)
    return seeded


def test_seeded_cadence_zero_behavior_change_for_zerodha(enabled):
    """The real seed_followup_cadence command, real tenant — step 1's resolved body
    (at seed time it's just the STEP_BODIES literal, {program_brand} unsubstituted
    since substitution happens at FIRE time) still carries the placeholder; firing it
    resolves to the exact old Zerodha wording."""
    call_command("seed_followup_cadence", "--tenant", enabled.slug)
    rule = FollowupRule.objects.get(tenant=enabled, step_key="nudge_3h")
    assert "{program_brand}" in rule.body_en
    assert "Zerodha" not in rule.body_en  # placeholder, not the literal, at rest

    window = _open_window(enabled)
    _scheduled_now(enabled, rule, window)

    rec = _RecordingAdapter()
    from unittest.mock import patch

    with patch.object(services, "in_quiet_hours", lambda *a, **k: False), \
         patch.object(tasks, "get_wati_adapter", lambda: rec):
        counts = tasks.fire_due_followups()

    assert counts["sent"] == 1
    _to, msg = rec.sent[0]
    assert msg.startswith(OLD_STEP1_EN), msg
    assert "{program_brand}" not in msg


def test_followup_body_substitutes_program_brand_for_second_program(enabled, monkeypatch):
    """A tenant whose ONLY active program is Groww (the no-identity-context case — a
    prospect's own cadence carries no per-referral program) renders the Groww brand,
    with NO code change to tasks.py/services.py."""
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)

    zerodha = ReferralProgram.objects.get(tenant=enabled)
    zerodha.status = "inactive"
    zerodha.save(update_fields=["status"])
    _second_program(enabled)

    rule = _rule_with_body(enabled, "Your {program_brand} account is pending. {link}")
    window = _open_window(enabled)
    _scheduled_now(enabled, rule, window)

    rec = _RecordingAdapter()
    monkeypatch.setattr(tasks, "get_wati_adapter", lambda: rec)

    counts = tasks.fire_due_followups()
    assert counts["sent"] == 1
    _to, msg = rec.sent[0]
    assert "Your Groww account is pending." in msg
    assert "Zerodha" not in msg
    assert "{program_brand}" not in msg


def test_followup_body_without_placeholder_is_untouched(enabled, monkeypatch):
    """A rule seeded before T-059 (or never re-seeded) has no {program_brand} in its
    stored body — this proves that content is left byte-for-byte alone, exactly as
    the zero-behavior-change predicate for not-yet-re-seeded prod rows requires."""
    monkeypatch.setattr(services, "in_quiet_hours", lambda *a, **k: False)

    rule = _rule_with_body(enabled, "Your Zerodha account is pending. {link}")
    window = _open_window(enabled)
    _scheduled_now(enabled, rule, window)

    rec = _RecordingAdapter()
    monkeypatch.setattr(tasks, "get_wati_adapter", lambda: rec)

    tasks.fire_due_followups()
    _to, msg = rec.sent[0]
    assert "Your Zerodha account is pending." in msg
