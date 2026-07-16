"""`golive_smoke` + `set_landing_mode` — the browser-free operator commands.

golive_smoke drives the REAL capture loop (redirect_service + lead_service), so these
tests assert the properties an operator relies on when reading its report:
  - it honors the flags (OFF => log-only, zero network),
  - it is idempotent (a re-run yields no twin journey/lead),
  - it never fabricates conversion status (guardrail #2),
  - it keeps PII out of the immutable event log (#16),
  - it works regardless of LANDING_MODE (the point: capture is testable in `direct`).
"""
import socket

import pytest
from django.core.management import CommandError, call_command
from django.core.management import call_command as _cc

from apps.config.preferences import LANDING_MODE
from apps.events.models import Event
from apps.referrals.landing_mode import LANDING_MODE_DIRECT, LANDING_MODE_PAGE, resolve_landing_mode
from apps.referrals.management.commands.golive_smoke import run_smoke
from apps.referrals.models import Lead, Referral

REFERRER = "RJ4521"
MOBILE = "9876543210"


@pytest.fixture
def seeded(db):
    _cc("seed_program")


# --- golive_smoke -----------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_smoke_runs_full_loop_and_reports(seeded):
    report = run_smoke(referrer=REFERRER, mobile=MOBILE, name="Smoke One")

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["referrer_client_id"] == REFERRER
    assert report["journey_id"]
    assert report["lead_id"]
    assert report["gorefer_reference"] == f"GR-{report['journey_id']}"

    # The loop really ran through the services: journey + lead exist, funnel recorded.
    assert Referral.objects.filter(pk=report["journey_id"]).exists()
    assert Lead.objects.filter(pk=report["lead_id"]).exists()
    types = set(Event.objects.filter(referral_id=report["journey_id"]).values_list("event_type", flat=True))
    assert "click" in types and "lead_captured" in types

    # All three notification roles are accounted for — a skipped one reports WHY.
    roles = {n["role"] for n in report["notifications"]}
    assert roles == {"office", "prospect", "referrer"}


@pytest.mark.django_db(transaction=True)
def test_smoke_is_idempotent_no_twin(seeded):
    first = run_smoke(referrer=REFERRER, mobile=MOBILE)
    second = run_smoke(referrer=REFERRER, mobile=MOBILE)

    assert second["journey_id"] == first["journey_id"], "re-run created a twin journey"
    assert second["lead_id"] == first["lead_id"], "re-run created a twin lead"
    assert Lead.objects.filter(deleted_at__isnull=True).count() == 1
    assert Referral.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_smoke_makes_no_network_call_when_flags_off(seeded, monkeypatch):
    """Flags OFF => log-only => not a single socket opened. This is the property that
    makes the command safe to run against prod before go-live."""
    real_connect = socket.socket.connect

    def _guarded(self, address):  # pragma: no cover - only trips on violation
        raise AssertionError(f"golive_smoke attempted a network connection to {address}")

    monkeypatch.setattr(socket.socket, "connect", _guarded)
    try:
        report = run_smoke(referrer=REFERRER, mobile=MOBILE)
    finally:
        monkeypatch.setattr(socket.socket, "connect", real_connect)

    assert report["ok"] is True
    assert report["zoho"]["action"] == "log-only"
    assert report["zoho"]["zoho_lead_id"].startswith("demo-"), "flag-off must use the demo adapter id"
    for n in report["notifications"]:
        assert n["status"] == "log-only" or n["status"].startswith("skipped")


@pytest.mark.django_db(transaction=True)
def test_smoke_never_fabricates_conversion_status(seeded):
    """Guardrail #2: status is Zoho-inbound only. The smoke run must not invent one."""
    report = run_smoke(referrer=REFERRER, mobile=MOBILE)
    assert report["conversion_status"] == ""
    referral = Referral.objects.get(pk=report["journey_id"])
    assert (referral.conversion_status or "") == ""
    assert not Event.objects.filter(referral=referral, event_type="account_opened").exists()


@pytest.mark.django_db(transaction=True)
def test_smoke_keeps_pii_out_of_events(seeded):
    """#16: name/mobile/email live on prospect/lead, never in the immutable log."""
    run_smoke(referrer=REFERRER, mobile=MOBILE, name="Rahul Verma", email="rahul@example.com")
    for event in Event.objects.all():
        blob = f"{event.metadata}"
        assert "Rahul" not in blob
        assert MOBILE not in blob
        assert "919876543210" not in blob
        assert "rahul@example.com" not in blob


@pytest.mark.django_db(transaction=True)
def test_smoke_works_in_direct_landing_mode(seeded):
    """The reason this command exists: in `direct` mode a browser never sees the
    form, but capture must still be testable."""
    from apps.config.cascade import set_tenant
    from apps.tenants.resolve import get_current_tenant

    tenant = get_current_tenant()
    set_tenant(LANDING_MODE, LANDING_MODE_DIRECT, tenant_id=tenant.id)
    assert resolve_landing_mode(tenant.id) == LANDING_MODE_DIRECT

    report = run_smoke(referrer=REFERRER, mobile=MOBILE)
    assert report["ok"] is True
    assert report["lead_id"], "capture must run independently of LANDING_MODE"


@pytest.mark.django_db(transaction=True)
def test_smoke_rejects_bad_input(seeded):
    with pytest.raises(CommandError):
        run_smoke(referrer="", mobile=MOBILE)
    with pytest.raises(CommandError):
        run_smoke(referrer=REFERRER, mobile="abc")


@pytest.mark.django_db(transaction=True)
def test_smoke_command_entrypoint_renders(seeded, capsys):
    call_command("golive_smoke", "--referrer", REFERRER, "--mobile", MOBILE)
    out = capsys.readouterr().out
    assert "RESULT: OK" in out
    assert "ENABLE_ZOHO_WRITE" in out
    # The report must not print the destination/partner code (guardrail #3 hygiene).
    assert "ZMPHZC" not in out
    assert "signup.zerodha.com" not in out


# --- set_landing_mode -------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_set_landing_mode_writes_and_is_idempotent(seeded):
    from apps.tenants.resolve import get_current_tenant

    tenant = get_current_tenant()

    call_command("set_landing_mode", LANDING_MODE_PAGE)
    assert resolve_landing_mode(tenant.id) == LANDING_MODE_PAGE

    # Re-running is a no-op, not an error and not a duplicate row.
    call_command("set_landing_mode", LANDING_MODE_PAGE)
    assert resolve_landing_mode(tenant.id) == LANDING_MODE_PAGE

    from apps.config.models import ConfigGlobal

    assert ConfigGlobal.objects.filter(key=LANDING_MODE, tenant=tenant).count() == 1


@pytest.mark.django_db(transaction=True)
def test_set_landing_mode_enforces_adr032_coupling(seeded, monkeypatch):
    """`direct` without a live /d/{slug} must be refused — the same rule the screen
    enforces. The command must NOT be a side door around the compliance coupling.
    """
    import apps.dashboard.preferences_service as svc
    from apps.tenants.resolve import get_current_tenant

    monkeypatch.setattr(svc, "has_live_disclosure_page", lambda tenant: False)
    tenant = get_current_tenant()

    with pytest.raises(CommandError):
        call_command("set_landing_mode", LANDING_MODE_DIRECT)

    # ...and it stayed on the safe mode rather than half-applying.
    assert resolve_landing_mode(tenant.id) == LANDING_MODE_PAGE


@pytest.mark.django_db(transaction=True)
def test_set_landing_mode_allows_direct_when_disclosure_is_live(seeded, monkeypatch):
    import apps.dashboard.preferences_service as svc
    from apps.tenants.resolve import get_current_tenant

    monkeypatch.setattr(svc, "has_live_disclosure_page", lambda tenant: True)
    tenant = get_current_tenant()

    call_command("set_landing_mode", LANDING_MODE_DIRECT)
    assert resolve_landing_mode(tenant.id) == LANDING_MODE_DIRECT


@pytest.mark.django_db(transaction=True)
def test_set_landing_mode_and_screen_share_one_write_path(seeded, monkeypatch):
    """UI + command must agree. Both go through preferences_service.set_landing_mode,
    so a rule added in one is automatically enforced for the other."""
    import apps.dashboard.preferences_service as svc
    from apps.tenants.resolve import get_current_tenant

    tenant = get_current_tenant()
    monkeypatch.setattr(svc, "has_live_disclosure_page", lambda tenant: False)

    # The screen's own save path refuses `direct` for the same reason...
    notices = svc.save_preferences(tenant, {"landing_mode": LANDING_MODE_DIRECT})
    assert resolve_landing_mode(tenant.id) == LANDING_MODE_PAGE
    assert any("disclosure page" in n for n in notices)

    # ...and so does the command.
    with pytest.raises(CommandError):
        call_command("set_landing_mode", LANDING_MODE_DIRECT)


@pytest.mark.django_db(transaction=True)
def test_set_landing_mode_unknown_tenant_errors(seeded):
    with pytest.raises(CommandError):
        call_command("set_landing_mode", LANDING_MODE_PAGE, "--tenant", "nope")
