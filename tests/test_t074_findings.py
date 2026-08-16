"""T-074 — closes two non-blocking findings the T-073 checker raised.

RULING-3: the invite send family's link_flag must be ENABLE_SHARE_HUB (the invite
button points at /hub/{token}, mounted only under ENABLE_SHARE_HUB) — NOT
ENABLE_RECORDS_LINK (the unrelated /records/ page). A SHARE_HUB-off +
RECORDS_LINK-on tenant must never be able to send the invite.

FINDING-A: `apps.integrations.wati.tasks.send_notification` must route through the
guarded messaging port (`get_messaging_port()`), not the raw adapter, so a future
token-carrying template enqueued there is also fail-closed-checked. Today's M5
role templates carry no computed variable, so this is asserted as a pass-through.
"""
from __future__ import annotations

import dataclasses

import pytest
from django.core.management import call_command

# Forces apps.config.integration_flags to import NOW, before any test below mutates
# gorefer.flags.flags — a lazy first import inside a test binds a stale copy (see
# `_set_flags`), and this test file runs order-independent of the rest of the suite.
import apps.config.integration_flags  # noqa: F401
from apps.config.preferences import INVITE_TEMPLATE_EN_DEFAULT
from apps.integrations import computed_vars as cv
from apps.integrations import ports
from apps.integrations import records_link_send as rls
from apps.integrations.models import Notification
from apps.integrations.wati import status as wati_status
from apps.integrations.wati import tasks as wati_tasks
from apps.integrations.wati.adapter import DeliveryResult, SendResult, TemplateStatus
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

CID = "RJ4521"  # LogOnlyZohoReadAdapter demo fixture — mobile 9876504321


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


class _FakeAdapter:
    kind = "log_only"

    def __init__(self, *, accepted=True, terminal_status=wati_status.STATUS_DELIVERED,
                 template_state="APPROVED"):
        self.sent = []
        self._accepted = accepted
        self._terminal_status = terminal_status
        self._template_state = template_state

    def send_template(self, *, to, template, params):
        self.sent.append({"to": to, "template": template, "params": params})
        return SendResult(
            accepted=self._accepted, provider_message_id="fake-mid",
            raw_status=wati_status.STATUS_ACCEPTED if self._accepted else wati_status.STATUS_FAILED,
        )

    def get_message_status(self, *, provider_message_id, recipient_mobile=None, template=None):
        return DeliveryResult(status=self._terminal_status, meta_error_code=None, classification=None)

    def get_template_status(self, *, template):
        return TemplateStatus(name=template, status=self._template_state, category="MARKETING")


# --------------------------------------------------------------------- RULING-3


def test_invite_link_flag_is_share_hub_not_records_link():
    assert rls.INVITE_FAMILY.link_flag == "ENABLE_SHARE_HUB"
    assert rls.RECORDS_FAMILY.link_flag == "ENABLE_RECORDS_LINK"


def test_invite_send_refused_when_share_hub_off_even_with_records_link_on(seeded, monkeypatch):
    """The exact T-073 checker gap: SHARE_HUB off + RECORDS_LINK on used to wrongly
    let the invite --send through."""
    _identity(seeded, CID)
    _set_flags(monkeypatch, ENABLE_SHARE_HUB=False, ENABLE_RECORDS_LINK=True, ENABLE_WATI_SEND=True)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: ports.GuardedMessagingPort(fake))

    with pytest.raises(rls.SendRefused) as exc:
        rls.send_invite_links([CID], dry_run=False)

    assert "ENABLE_SHARE_HUB" in str(exc.value)
    assert fake.sent == []


def test_invite_send_allowed_when_share_hub_on_and_records_link_off(seeded, monkeypatch):
    """Inverse case: SHARE_HUB on (RECORDS_LINK off) is enough for the invite gate."""
    _identity(seeded, CID)
    _set_flags(monkeypatch, ENABLE_SHARE_HUB=True, ENABLE_RECORDS_LINK=False, ENABLE_WATI_SEND=True)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: ports.GuardedMessagingPort(fake))

    result = rls.send_invite_links([CID], dry_run=False)

    assert result["sent"] == 1
    assert len(fake.sent) == 1


def test_records_send_still_gated_on_records_link_not_share_hub(seeded, monkeypatch):
    """The records family must be unaffected: still ENABLE_RECORDS_LINK, and a
    SHARE_HUB-only tenant must NOT be able to send records links."""
    _identity(seeded, CID)
    _set_flags(monkeypatch, ENABLE_SHARE_HUB=True, ENABLE_RECORDS_LINK=False, ENABLE_WATI_SEND=True)
    fake = _FakeAdapter()
    monkeypatch.setattr(rls, "get_messaging_port", lambda: ports.GuardedMessagingPort(fake))

    with pytest.raises(rls.SendRefused) as exc:
        rls.send_records_links([CID], dry_run=False)

    assert "ENABLE_RECORDS_LINK" in str(exc.value)
    assert fake.sent == []

    # ...and turning RECORDS_LINK on (SHARE_HUB irrelevant) lets it through.
    _set_flags(monkeypatch, ENABLE_SHARE_HUB=False, ENABLE_RECORDS_LINK=True, ENABLE_WATI_SEND=True)
    result = rls.send_records_links([CID], dry_run=False)
    assert result["sent"] == 1


# --------------------------------------------------------------------- FINDING-A


def test_send_notification_routes_through_the_guarded_port_and_refuses_a_blank_token(
    seeded, monkeypatch,
):
    """A future token-family template enqueued via send_notification must be refused
    by the same fail-closed guard the invite sender uses — zero adapter calls."""
    fake = _FakeAdapter()
    # Wrap in the REAL GuardedMessagingPort (not the raw fake) — this proves
    # send_notification calls get_messaging_port() (the guarded factory), not
    # get_wati_adapter() directly, per FINDING-A.
    monkeypatch.setattr(wati_tasks, "get_messaging_port", lambda: ports.GuardedMessagingPort(fake))

    n = Notification.objects.create(
        tenant=seeded, recipient_role="referrer", recipient_mobile="919876504321",
        template=INVITE_TEMPLATE_EN_DEFAULT,
        template_params=[
            {"name": "name", "value": "Rajesh"},
            {"name": "client_id", "value": CID},
            {"name": "token", "value": ""},   # blank computed var
        ],
        status="queued",
    )

    with pytest.raises(cv.MissingComputedVar):
        wati_tasks.send_notification(n.id)

    assert fake.sent == []


def test_send_notification_still_sends_a_non_token_role_template_unchanged(seeded, monkeypatch):
    """M5 role templates carry no computed variable — the guard must be a pure
    pass-through for them, so existing sends are unaffected."""
    fake = _FakeAdapter(terminal_status=wati_status.STATUS_DELIVERED)
    monkeypatch.setattr(wati_tasks, "get_messaging_port", lambda: ports.GuardedMessagingPort(fake))

    n = Notification.objects.create(
        tenant=seeded, recipient_role="office", recipient_mobile="919876504321",
        template="gr_brokers_zerodha_office_lead_alert_en_2026_07_19",
        template_params=[{"name": "prospect_name", "value": "Rahul"}],
        status="queued",
    )

    status = wati_tasks.send_notification(n.id)

    assert status == wati_status.STATUS_DELIVERED
    assert len(fake.sent) == 1
    n.refresh_from_db()
    assert n.status == wati_status.STATUS_DELIVERED
    assert n.adapter_kind == "log_only"
