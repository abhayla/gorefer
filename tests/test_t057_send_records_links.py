"""T-057 — `send_records_links` operator command.

Locks down:
  - dry-run is the default and never sends/writes anything;
  - `--send` refuses unless BOTH ENABLE_WATI_SEND and ENABLE_RECORDS_LINK are on;
  - mobile is resolved from the vendor-neutral CRM READ port, never fabricated —
    an unknown client_id or one with no mobile on file is skipped, not guessed;
  - token/name/record_date come from the SAME helper the mint API uses;
  - per-run cap, min-gap dedupe and opt-out all gate real sends;
  - a real send is recorded via the accepted -> terminal-status machinery (never
    HTTP-200-as-success), and the funnel event carries client_id + template + outcome
    but NEVER the token (T-051 precedent) and NEVER PII.
"""
from __future__ import annotations

import dataclasses

import pytest
from django.core.management import CommandError, call_command

from apps.config.cascade import set_tenant
from apps.config.preferences import RECORDS_LINK_SEND_MAX_PER_RUN, RECORDS_LINK_SEND_MIN_GAP_DAYS
from apps.events.models import Event
from apps.followups.models import FollowupWindow
from apps.integrations import records_link_send as rls
from apps.integrations.models import Notification
from apps.integrations.wati import status as wati_status
from apps.integrations.wati.adapter import DeliveryResult, SendResult, TemplateStatus
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

CID = "RJ4521"          # in the LogOnlyZohoReadAdapter demo fixtures — mobile 9876504321
UNKNOWN_CID = "ZZ9999"  # well-formed, but no GoRefer ReferralIdentity
NO_MOBILE_CID = "EKU497"  # a GoRefer identity exists, but no Zoho demo fixture (no mobile)


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _identity(tenant, client_id: str) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _set_flags(monkeypatch, **overrides):
    """Rebuild the frozen flags snapshot with overrides (mirrors test_qmotp._set_flags)."""
    from gorefer import flags as flags_mod

    new = dataclasses.replace(flags_mod.flags, **overrides)
    monkeypatch.setattr(flags_mod, "flags", new)
    if "ENABLE_WATI_SEND" in overrides:
        import apps.config.integration_flags as ifl

        want = overrides["ENABLE_WATI_SEND"]
        monkeypatch.setattr(
            ifl, "resolve_flag",
            lambda key, **kw: want if key == ifl.ENABLE_WATI_SEND else ifl.env_default(key),
        )
    return new


def _sending_enabled(monkeypatch):
    _set_flags(monkeypatch, ENABLE_RECORDS_LINK=True, ENABLE_WATI_SEND=True)


class _FakeAdapter:
    """Records every send; terminal status is controllable per test."""

    kind = "log_only"

    def __init__(self, *, accepted=True, terminal_status=wati_status.STATUS_DELIVERED):
        self.sent = []
        self._accepted = accepted
        self._terminal_status = terminal_status

    def send_template(self, *, to, template, params):
        self.sent.append({"to": to, "template": template, "params": params})
        return SendResult(
            accepted=self._accepted, provider_message_id="fake-mid",
            raw_status=wati_status.STATUS_ACCEPTED if self._accepted else wati_status.STATUS_FAILED,
        )

    def get_message_status(self, *, provider_message_id, recipient_mobile=None, template=None):
        return DeliveryResult(status=self._terminal_status, meta_error_code=None, classification=None)

    def get_template_status(self, *, template):
        # T-073: a real send now proves vendor-side approval first. The records-link
        # template IS approved in production, so the fake reports it as such.
        return TemplateStatus(name=template, status="APPROVED", category="UTILITY")


# --------------------------------------------------------------------------- dry-run


def test_dry_run_is_the_default_and_sends_nothing(seeded, monkeypatch):
    _identity(seeded, CID)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([CID])  # dry_run defaults True

    assert result["dry_run"] is True
    assert result["would_send"] == 1
    assert result["sent"] == 0
    assert fake.sent == []  # the adapter was never even constructed/used
    assert Notification.objects.count() == 0
    assert Event.objects.count() == 0
    item = result["items"][0]
    assert item["client_id"] == CID
    assert item["mobile"] == "98••••••21"  # masked, never raw
    assert item["record_date"]
    assert item["outcome"] == "would_send"


def test_command_dry_run_cli(seeded, monkeypatch, capsys):
    _identity(seeded, CID)
    call_command("send_records_links", "--client-ids", CID)
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "9876504321" not in out  # never the raw mobile


# --------------------------------------------------------------------------- refusal gate


def test_send_refused_when_flags_off(seeded, monkeypatch):
    _identity(seeded, CID)
    with pytest.raises(rls.SendRefused):
        rls.send_records_links([CID], dry_run=False)


def test_command_send_refused_is_a_command_error(seeded, monkeypatch):
    _identity(seeded, CID)
    with pytest.raises(CommandError):
        call_command("send_records_links", "--client-ids", CID, "--send")


# --------------------------------------------------------------------------- happy send


def test_send_records_delivery_and_event(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _FakeAdapter(terminal_status=wati_status.STATUS_DELIVERED)
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([CID], dry_run=False)

    assert result["sent"] == 1
    item = result["items"][0]
    assert item["outcome"] == "sent"

    assert len(fake.sent) == 1
    call = fake.sent[0]
    assert call["to"] == "919876504321"
    param_names = {p["name"] for p in call["params"]["template_params"]}
    assert param_names == {"name", "record_date", "token"}
    assert call["params"]["template_params_named"] is True

    n = Notification.objects.get()
    assert n.status == wati_status.STATUS_DELIVERED  # terminal status, not just 'accepted'
    assert n.recipient_mobile == "919876504321"

    event = Event.objects.get()
    assert event.metadata["kind"] == "records_link"
    assert event.metadata["client_id"] == CID
    assert event.metadata["template"] == result["template"]
    # NEVER the token, NEVER any PII, in the immutable event log (T-051 precedent).
    dumped = str(event.metadata)
    assert "token" not in dumped.lower() or event.metadata.get("token") is None
    assert "9876504321" not in dumped
    assert "Rajesh" not in dumped


def test_send_not_accepted_is_recorded_failed(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _FakeAdapter(accepted=False)
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([CID], dry_run=False)

    assert result["failed"] == 1
    n = Notification.objects.get()
    assert n.status == "failed"


# --------------------------------------------------------------------------- never-fabricate


def test_unknown_client_id_is_skipped_never_fabricated(seeded, monkeypatch):
    _sending_enabled(monkeypatch)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([UNKNOWN_CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert Notification.objects.count() == 0
    item = result["items"][0]
    assert item["outcome"] == "skipped"
    assert item["mobile"] == ""


def test_no_mobile_on_file_is_skipped(seeded, monkeypatch):
    _identity(seeded, NO_MOBILE_CID)
    _sending_enabled(monkeypatch)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([NO_MOBILE_CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    item = result["items"][0]
    assert "no mobile" in item["reason"]


def test_invalid_client_id_is_skipped(seeded, monkeypatch):
    result = rls.send_records_links(["!!"])
    assert result["skipped"] == 1
    assert "invalid" in result["items"][0]["reason"]


# --------------------------------------------------------------------------- safety gates


def test_per_run_cap(seeded, monkeypatch):
    for cid in (CID, NO_MOBILE_CID):
        _identity(seeded, cid)
    set_tenant(RECORDS_LINK_SEND_MAX_PER_RUN, 1, tenant_id=seeded.id)

    result = rls.send_records_links([CID, "EKU498"])  # dry-run: cap still applies

    outcomes = [i["outcome"] for i in result["items"]]
    assert outcomes[0] == "would_send"
    assert outcomes[1] == "skipped"
    assert "cap" in result["items"][1]["reason"]


def test_min_gap_dedupe_skips_recent_send(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    from apps.events import vocab

    Event.objects.create(
        tenant=seeded, event_type=vocab.NOTIFICATION, source=vocab.SRC_WATI, user_type="system",
        metadata={"kind": "records_link", "client_id": CID, "template": "t", "outcome": "sent"},
    )

    result = rls.send_records_links([CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert "min-gap" in result["items"][0]["reason"]


def test_min_gap_zero_allows_resend(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    set_tenant(RECORDS_LINK_SEND_MIN_GAP_DAYS, 0, tenant_id=seeded.id)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    from apps.events import vocab

    Event.objects.create(
        tenant=seeded, event_type=vocab.NOTIFICATION, source=vocab.SRC_WATI, user_type="system",
        metadata={"kind": "records_link", "client_id": CID, "template": "t", "outcome": "sent"},
    )

    result = rls.send_records_links([CID], dry_run=False)
    assert result["sent"] == 1


def test_opted_out_recipient_is_skipped(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    FollowupWindow.objects.create(tenant=seeded, mobile="919876504321", opted_out=True)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert "opted out" in result["items"][0]["reason"]


def test_blocked_by_allowlist_is_skipped_not_failed(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)

    class _BlockedAdapter(_FakeAdapter):
        def send_template(self, *, to, template, params):
            self.sent.append({"to": to, "template": template, "params": params})
            return SendResult(accepted=False, provider_message_id=None, raw_status=wati_status.STATUS_BLOCKED)

    fake = _BlockedAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)

    result = rls.send_records_links([CID], dry_run=False)

    assert result["skipped"] == 1
    assert result["failed"] == 0
    n = Notification.objects.get()
    assert n.status == "skipped"
    assert "allowlist" in n.skip_reason
