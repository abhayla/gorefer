"""T-073 — fail-closed computed-variable guard + per-recipient invite sender.

The bug this locks out: a template carrying a SERVER-COMPUTED `{{token}}` gets sent
by something that cannot mint one (a Wati dashboard broadcast), the variable comes
back blank, and every recipient receives `https://gorefer.in/hub/` — a dead link —
marked delivered. Nothing in the stack noticed.

So these tests assert the inverse rule end to end:

  * the registry knows which templates need which computed variables, across
    version/language re-cuts of the same family;
  * a missing / blank / whitespace-only computed value REFUSES the send — at the
    port (raises, zero adapter call) and at the sender (skips that recipient with
    the stable reason `missing_computed_var:token`, zero Wati call, zero write);
  * `--send` refuses a template the vendor does not report as APPROVED — the invite
    template is a DRAFT today, so this is the live behaviour, not a hypothetical;
  * the invite sender mints a DISTINCT token per recipient, byte-identical to what
    the mint API / hub CTA would produce for that same identity;
  * every T-057 gate still applies to the new family, delivery is asserted on the
    TERMINAL status, and the token never reaches a log or the event stream.
"""
from __future__ import annotations

import dataclasses

import pytest
from django.core.management import CommandError, call_command

from apps.config.cascade import set_tenant
from apps.config.preferences import (
    INVITE_SEND_MAX_PER_RUN,
    INVITE_SEND_MIN_GAP_DAYS,
    INVITE_TEMPLATE_EN,
    INVITE_TEMPLATE_EN_DEFAULT,
)
from apps.events.models import Event
from apps.followups.models import FollowupWindow
from apps.integrations import computed_vars as cv
from apps.integrations import ports
from apps.integrations import records_link_send as rls
from apps.integrations.models import Notification
from apps.integrations.wati import status as wati_status
from apps.integrations.wati.adapter import DeliveryResult, SendResult, TemplateStatus
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

CID = "RJ4521"            # LogOnlyZohoReadAdapter demo fixture — mobile 9876504321
CID2 = "DA1707"           # second demo fixture
NO_MOBILE_CID = "EKU497"


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
    """Records every send; template state and terminal status controllable per test."""

    kind = "log_only"

    def __init__(self, *, accepted=True, terminal_status=wati_status.STATUS_DELIVERED,
                 template_state="APPROVED", status_raises=False):
        self.sent = []
        self.status_probes = []
        self._accepted = accepted
        self._terminal_status = terminal_status
        self._template_state = template_state
        self._status_raises = status_raises

    def send_template(self, *, to, template, params):
        self.sent.append({"to": to, "template": template, "params": params})
        return SendResult(
            accepted=self._accepted, provider_message_id="fake-mid",
            raw_status=wati_status.STATUS_ACCEPTED if self._accepted else wati_status.STATUS_FAILED,
        )

    def get_message_status(self, *, provider_message_id, recipient_mobile=None, template=None):
        return DeliveryResult(status=self._terminal_status, meta_error_code=None, classification=None)

    def get_template_status(self, *, template):
        self.status_probes.append(template)
        if self._status_raises:
            raise RuntimeError("vendor unreachable")
        return TemplateStatus(name=template, status=self._template_state, category="MARKETING")


class _NoTemplateCheckAdapter(_FakeAdapter):
    """An adapter with no way to prove approval — must refuse, never assume."""

    get_template_status = None


def _use(monkeypatch, fake):
    monkeypatch.setattr(rls, "get_messaging_port", lambda: fake)
    return fake


# --------------------------------------------------------------------------- the registry


def test_registry_knows_the_token_families():
    assert cv.required_computed_vars(INVITE_TEMPLATE_EN_DEFAULT) == frozenset({"token"})
    assert cv.required_computed_vars("gr_platform_gorefer_refrecord_en_2026_08_07") == frozenset({"token"})


def test_registry_survives_a_recut_or_language_twin():
    """A version bump / Hindi twin is the SAME template with the same computed
    variable — a rename must not silently drop the guard."""
    assert cv.required_computed_vars("gr_brokers_zerodha_referandearn_invite_hi_2026_09_01_v2") \
        == frozenset({"token"})
    assert cv.required_computed_vars("gr_platform_gorefer_refrecord_hi_2027_01_01") \
        == frozenset({"token"})


def test_templates_without_computed_vars_are_untouched():
    assert cv.required_computed_vars("gr_platform_gorefer_otp_en") == frozenset()
    cv.assert_computed_vars_filled("gr_platform_gorefer_otp_en", {"template_params": []})


def test_register_computed_vars_adds_an_exact_name():
    cv.register_computed_vars("gr_test_t073_dynamic", ["token"])
    try:
        assert cv.required_computed_vars("gr_test_t073_dynamic") == frozenset({"token"})
    finally:
        cv._EXACT.pop("gr_test_t073_dynamic", None)


@pytest.mark.parametrize("value", ["", "   ", None])
def test_missing_blank_and_whitespace_all_refuse(value):
    params = {"template_params": [{"name": "name", "value": "A"}, {"name": "token", "value": value}]}
    with pytest.raises(cv.MissingComputedVar) as exc:
        cv.assert_computed_vars_filled(INVITE_TEMPLATE_EN_DEFAULT, params)
    assert exc.value.reason == "missing_computed_var:token"


def test_absent_param_entirely_refuses():
    with pytest.raises(cv.MissingComputedVar):
        cv.assert_computed_vars_filled(
            INVITE_TEMPLATE_EN_DEFAULT, {"template_params": [{"name": "name", "value": "A"}]}
        )


def test_a_filled_token_passes():
    cv.assert_computed_vars_filled(
        INVITE_TEMPLATE_EN_DEFAULT,
        {"template_params": [{"name": "token", "value": "abc.def"}]},
    )


# --------------------------------------------------------------------------- the port guard


def test_guarded_port_refuses_a_blank_token_with_zero_adapter_calls():
    fake = _FakeAdapter()
    port = ports.GuardedMessagingPort(fake)

    with pytest.raises(cv.MissingComputedVar):
        port.send_template(
            to="919876543210", template=INVITE_TEMPLATE_EN_DEFAULT,
            params={"template_params": [{"name": "token", "value": ""}]},
        )

    assert fake.sent == []  # the guard fires BEFORE the adapter, so nothing left the box


def test_guarded_port_passes_a_filled_token_through():
    fake = _FakeAdapter()
    port = ports.GuardedMessagingPort(fake)
    port.send_template(
        to="919876543210", template=INVITE_TEMPLATE_EN_DEFAULT,
        params={"template_params": [{"name": "token", "value": "tok"}]},
    )
    assert len(fake.sent) == 1


def test_the_factory_itself_is_guarded():
    """Any caller anywhere — followups, OTP, congrats — gets the guard, because it
    is fitted at the port factory rather than in one sender's good manners."""
    port = ports.get_messaging_port()
    assert isinstance(port, ports.GuardedMessagingPort)
    with pytest.raises(cv.MissingComputedVar):
        port.send_template(
            to="919876543210", template=INVITE_TEMPLATE_EN_DEFAULT,
            params={"template_params": [{"name": "token", "value": ""}]},
        )


# --------------------------------------------------------------------------- sender: guard


def test_sender_skips_a_recipient_whose_token_cannot_be_minted(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())

    # A resolver that hands back a blank token — the exact shape a broadcast would
    # have produced silently.
    monkeypatch.setattr(
        rls, "resolve_link_details",
        lambda tenant, cid: {"client_id": cid, "token": "", "name": "Rajesh", "record_date": "07 Aug 2026"},
    )

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["skipped"] == 1
    assert result["sent"] == 0
    assert result["items"][0]["reason"] == "missing_computed_var:token"
    assert fake.sent == []            # zero Wati call
    assert Notification.objects.count() == 0   # zero blank param persisted anywhere


def test_whitespace_token_is_treated_as_blank_by_the_sender(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())
    monkeypatch.setattr(
        rls, "resolve_link_details",
        lambda tenant, cid: {"client_id": cid, "token": "   ", "name": "R", "record_date": ""},
    )

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["items"][0]["reason"] == "missing_computed_var:token"
    assert fake.sent == []


# --------------------------------------------------------------------------- approval gate


def test_send_refuses_a_draft_template(seeded, monkeypatch):
    """The invite template is a DRAFT at Meta today — `--send` must refuse it NOW."""
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter(template_state="DRAFT"))

    with pytest.raises(rls.SendRefused) as exc:
        rls.send_invite_links([CID], dry_run=False)

    assert "not APPROVED" in str(exc.value)
    assert fake.sent == []
    assert fake.status_probes == [INVITE_TEMPLATE_EN_DEFAULT]


def test_command_send_of_the_draft_invite_is_a_command_error(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    _use(monkeypatch, _FakeAdapter(template_state="DRAFT"))
    with pytest.raises(CommandError):
        call_command("send_invite_links", "--client-ids", CID, "--send")


def test_send_refuses_when_the_vendor_check_errors(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter(status_raises=True))
    with pytest.raises(rls.SendRefused):
        rls.send_invite_links([CID], dry_run=False)
    assert fake.sent == []


def test_send_refuses_when_approval_cannot_be_asked_at_all(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _NoTemplateCheckAdapter())
    with pytest.raises(rls.SendRefused):
        rls.send_invite_links([CID], dry_run=False)
    assert fake.sent == []


def test_live_adapter_reports_unknown_when_wati_is_unreachable(monkeypatch):
    from apps.integrations.wati.adapter import LiveWatiAdapter

    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "t")
    adapter = LiveWatiAdapter(transport=lambda *a, **k: (599, ""))
    assert adapter.get_template_status(template="x").approved is False


def test_live_adapter_reads_the_real_inventory_shape(monkeypatch):
    import json as _json

    from apps.integrations.wati.adapter import LiveWatiAdapter

    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "t")
    body = _json.dumps({"messageTemplates": [
        {"elementName": "gr_a", "status": "APPROVED", "category": "UTILITY"},
        {"elementName": "gr_b", "status": "DRAFT", "category": "MARKETING"},
    ]})
    adapter = LiveWatiAdapter(transport=lambda *a, **k: (200, body))

    assert adapter.get_template_status(template="gr_a").approved is True
    assert adapter.get_template_status(template="gr_a").category == "UTILITY"
    assert adapter.get_template_status(template="gr_b").approved is False
    # A name the inventory has never heard of is UNKNOWN, never a hopeful APPROVED.
    assert adapter.get_template_status(template="gr_missing").status == "UNKNOWN"


# --------------------------------------------------------------------------- one token path


def test_the_sender_token_is_byte_identical_to_the_mint_helpers(seeded):
    """A hub link from a broadcast and one from the logged-in hub CTA must never
    diverge — same identity, same code path, same bytes."""
    from api.records_tokens import resolve_link_details
    from apps.accounts.records_link import mint_records_token

    identity = _identity(seeded, CID)
    via_sender = resolve_link_details(seeded, CID)["token"]
    via_helper = mint_records_token(identity)

    assert via_sender and via_sender == via_helper


def test_each_recipient_gets_a_DISTINCT_token(seeded, monkeypatch):
    _identity(seeded, CID)
    _identity(seeded, CID2)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())

    rls.send_invite_links([CID, CID2], dry_run=False)

    assert len(fake.sent) == 2
    tokens = [
        next(p["value"] for p in call["params"]["template_params"] if p["name"] == "token")
        for call in fake.sent
    ]
    assert all(tokens)
    assert tokens[0] != tokens[1]


# --------------------------------------------------------------------------- invite send


def test_invite_send_carries_name_client_id_and_token(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter(terminal_status=wati_status.STATUS_DELIVERED))

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["sent"] == 1
    call = fake.sent[0]
    assert call["to"] == "919876504321"
    assert call["params"]["template_params_named"] is True
    params = {p["name"]: p["value"] for p in call["params"]["template_params"]}
    assert set(params) == {"name", "client_id", "token"}
    assert params["client_id"] == CID
    assert params["token"]

    n = Notification.objects.get()
    # TERMINAL status, not an HTTP-200 "accepted" (doc-08 A3).
    assert n.status == wati_status.STATUS_DELIVERED
    assert n.category == "MARKETING"


def test_invite_delivery_failure_is_recorded_failed(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    _use(monkeypatch, _FakeAdapter(terminal_status=wati_status.STATUS_FAILED))

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["failed"] == 1
    assert Notification.objects.get().status == wati_status.STATUS_FAILED


def test_invite_event_never_carries_the_token_or_pii(seeded, monkeypatch, caplog):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())

    with caplog.at_level("INFO"):
        rls.send_invite_links([CID], dry_run=False)

    token = next(p["value"] for p in fake.sent[0]["params"]["template_params"] if p["name"] == "token")
    event = Event.objects.get()
    assert event.metadata["kind"] == "referral_invite"
    assert event.metadata["client_id"] == CID
    dumped = str(event.metadata)
    assert token not in dumped
    assert "9876504321" not in dumped
    assert token not in caplog.text          # a logged token is a live credential
    assert "9876504321" not in caplog.text


# --------------------------------------------------------------------------- dry run


def test_invite_dry_run_is_the_default_and_sends_nothing(seeded, monkeypatch):
    _identity(seeded, CID)
    fake = _use(monkeypatch, _FakeAdapter())

    result = rls.send_invite_links([CID])

    assert result["dry_run"] is True
    assert result["would_send"] == 1
    assert fake.sent == []
    assert fake.status_probes == []   # dry-run never touches the vendor at all
    assert Notification.objects.count() == 0
    assert Event.objects.count() == 0
    item = result["items"][0]
    assert item["mobile"] == "98••••••21"    # masked, never raw
    assert item["token_minted"] is True


def test_invite_command_dry_run_prints_no_token_value(seeded, monkeypatch, capsys):
    _identity(seeded, CID)
    call_command("send_invite_links", "--client-ids", CID)
    out = capsys.readouterr().out

    from api.records_tokens import resolve_link_details

    token = resolve_link_details(seeded, CID)["token"]
    assert "DRY-RUN" in out
    assert "token=minted" in out
    assert token not in out
    assert "9876504321" not in out


# --------------------------------------------------------------------------- inherited gates


def test_invite_send_refused_when_flags_off(seeded):
    _identity(seeded, CID)
    with pytest.raises(rls.SendRefused):
        rls.send_invite_links([CID], dry_run=False)


def test_invite_per_run_cap(seeded, monkeypatch):
    _identity(seeded, CID)
    _identity(seeded, CID2)
    set_tenant(INVITE_SEND_MAX_PER_RUN, 1, tenant_id=seeded.id)

    result = rls.send_invite_links([CID, CID2])

    assert [i["outcome"] for i in result["items"]] == ["would_send", "skipped"]
    assert "cap" in result["items"][1]["reason"]


def test_invite_min_gap_dedupe(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())

    from apps.events import vocab

    Event.objects.create(
        tenant=seeded, event_type=vocab.NOTIFICATION, source=vocab.SRC_WATI, user_type="system",
        metadata={"kind": "referral_invite", "client_id": CID, "template": "t", "outcome": "sent"},
    )

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert "min-gap" in result["items"][0]["reason"]


def test_invite_min_gap_is_independent_of_the_records_family(seeded, monkeypatch):
    """A records-link send last week must not suppress an invite (and vice versa)."""
    _identity(seeded, CID)
    from apps.events import vocab

    Event.objects.create(
        tenant=seeded, event_type=vocab.NOTIFICATION, source=vocab.SRC_WATI, user_type="system",
        metadata={"kind": "records_link", "client_id": CID, "template": "t", "outcome": "sent"},
    )
    set_tenant(INVITE_SEND_MIN_GAP_DAYS, 30, tenant_id=seeded.id)

    assert rls.send_invite_links([CID])["would_send"] == 1


def test_invite_opt_out_is_honoured(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())
    FollowupWindow.objects.create(tenant=seeded, mobile="919876504321", opted_out=True)

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert "opted out" in result["items"][0]["reason"]


def test_invite_unknown_client_id_is_skipped_never_fabricated(seeded, monkeypatch):
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())

    result = rls.send_invite_links(["ZZ9999"], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert Notification.objects.count() == 0


def test_invite_no_mobile_on_file_is_skipped(seeded, monkeypatch):
    _identity(seeded, NO_MOBILE_CID)
    _sending_enabled(monkeypatch)
    fake = _use(monkeypatch, _FakeAdapter())

    result = rls.send_invite_links([NO_MOBILE_CID], dry_run=False)

    assert result["skipped"] == 1
    assert fake.sent == []
    assert "no mobile" in result["items"][0]["reason"]


def test_invite_blocked_by_allowlist_is_skipped_not_failed(seeded, monkeypatch):
    _identity(seeded, CID)
    _sending_enabled(monkeypatch)

    class _Blocked(_FakeAdapter):
        def send_template(self, *, to, template, params):
            self.sent.append({"to": to, "template": template, "params": params})
            return SendResult(accepted=False, provider_message_id=None,
                              raw_status=wati_status.STATUS_BLOCKED)

    _use(monkeypatch, _Blocked())
    result = rls.send_invite_links([CID], dry_run=False)

    assert result["skipped"] == 1 and result["failed"] == 0
    assert "allowlist" in Notification.objects.get().skip_reason


# --------------------------------------------------------------------------- config


def test_template_name_comes_from_the_cascade(seeded, monkeypatch):
    _identity(seeded, CID)
    recut = "gr_brokers_zerodha_referandearn_invite_en_2026_12_01"
    set_tenant(INVITE_TEMPLATE_EN, recut, tenant_id=seeded.id)

    result = rls.send_invite_links([CID])

    assert result["template"] == "gr_brokers_zerodha_referandearn_invite_en_2026_12_01"
    # …and the renamed template is STILL guarded, by family match.
    assert cv.required_computed_vars(result["template"]) == frozenset({"token"})
