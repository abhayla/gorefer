"""Tracking of the owner's account-opening links (T-link-tracking, owner 2026-11-27).

What every human use of the focus links records, PII-free:
  - Kite ID pop-up (both modes): each view (with the visitor cookie, so views can be
    counted per visitor), and each button as `kite_prompt_action`:
      entered -> the validated, public client_id (ADR-001);
      skip    -> "Share without my ID" / "I don't have one, continue";
      wrong   -> ONLY a reason (empty / shape / placeholder / deleted), NEVER the typed text,
                 which may be a mobile number (DPDP, Round-2 amendment #16).
  - every partner-direct click carries metadata["origin"], so /open, /r/open and the
    pop-up's Skip are no longer one indistinguishable pile;
  - a one-tap share from a datacenter address is is_bot=True (same rule as clicks);
  - no event stores the raw IP.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events import netranges, vocab
from apps.events.models import Event

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}


@pytest.fixture
def seeded(db):
    call_command("seed_program")


def _get(path, capture, client=None, **kw):
    with capture(execute=True):
        return (client or Client()).get(path, **(kw or HUMAN))


def _actions():
    return list(Event.objects.filter(event_type=vocab.KITE_PROMPT_ACTION).order_by("id"))


def _assert_no_ip_anywhere():
    for ev in Event.objects.all():
        assert "203.0.113.9" not in str(ev.metadata)


# --- the pop-up view ------------------------------------------------------------

def test_popup_view_sets_and_records_the_visitor(seeded, django_capture_on_commit_callbacks):
    client = Client()
    resp = _get("/zerodha/r/wa/KITEID", django_capture_on_commit_callbacks, client)
    _get("/zerodha/r/wa/KITEID", django_capture_on_commit_callbacks, client)  # reload
    assert "gr_vid" in resp.cookies
    views = Event.objects.filter(event_type=vocab.SHARE_RECOVERY_VIEWED)
    assert views.count() == 2  # every view is kept ...
    assert views.values("visitor_id").distinct().count() == 1  # ... but it is one visitor
    assert views.first().visitor_id == resp.cookies["gr_vid"].value


# --- entered ----------------------------------------------------------------------

@pytest.mark.parametrize("path,prompt", [
    ("/zerodha/r/wa/KITEID?kite_id=ab1234", vocab.PROMPT_MODE_REFERRAL),
])
def test_valid_entry_records_the_public_id(seeded, django_capture_on_commit_callbacks, path, prompt):
    resp = _get(path, django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    (action,) = _actions()
    assert action.metadata == {
        "channel": "WhatsApp", "prompt": prompt, "action": vocab.PROMPT_ACTION_ENTERED, "client_id": "AB1234",
    }


@pytest.mark.urls("tests.urls_share_intent")
def test_share_popup_entry_records_the_id_then_the_share(seeded, django_capture_on_commit_callbacks):
    client = Client()
    resp = _get("/zerodha/share/wa/KITEID?kite_id=AB1234", django_capture_on_commit_callbacks, client)
    assert resp.status_code == 302
    (action,) = _actions()
    assert action.metadata["prompt"] == vocab.PROMPT_MODE_SHARE
    assert action.metadata["client_id"] == "AB1234"
    _get(resp.headers["Location"], django_capture_on_commit_callbacks, client)
    share = Event.objects.get(event_type=vocab.SHARE_INTENT)
    assert share.referral.referral_identity.client_id == "AB1234"


# --- wrong ------------------------------------------------------------------------

@pytest.mark.parametrize("typed,reason", [
    ("", vocab.PROMPT_WRONG_EMPTY),
    ("9876543210", vocab.PROMPT_WRONG_SHAPE),  # a mobile number: counted, never stored
    ("KITEID", vocab.PROMPT_WRONG_PLACEHOLDER),
])
def test_wrong_entry_records_only_the_reason(seeded, django_capture_on_commit_callbacks, typed, reason):
    resp = _get(f"/zerodha/r/wa/KITEID?kite_id={typed}", django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    (action,) = _actions()
    assert action.metadata == {
        "channel": "WhatsApp", "prompt": vocab.PROMPT_MODE_REFERRAL,
        "action": vocab.PROMPT_ACTION_WRONG, "reason": reason,
    }
    if typed:
        for ev in Event.objects.all():
            assert typed not in str(ev.metadata)


# --- skip + origin ------------------------------------------------------------------

def test_referral_skip_records_the_tap_and_tags_the_click(seeded, django_capture_on_commit_callbacks):
    _get("/zerodha/r/wa/KITEID?skip=1", django_capture_on_commit_callbacks)
    (action,) = _actions()
    assert action.metadata["action"] == vocab.PROMPT_ACTION_SKIP
    click = Event.objects.get(event_type=vocab.CLICK)
    assert click.metadata["origin"] == vocab.ORIGIN_POPUP_SKIP


@pytest.mark.urls("tests.urls_share_intent")
def test_share_skip_records_the_tap_and_the_no_id_share(seeded, django_capture_on_commit_callbacks):
    _get("/zerodha/share/wa/KITEID?skip=1", django_capture_on_commit_callbacks)
    (action,) = _actions()
    assert (action.metadata["prompt"], action.metadata["action"]) == (
        vocab.PROMPT_MODE_SHARE, vocab.PROMPT_ACTION_SKIP,
    )
    assert Event.objects.get(event_type=vocab.SHARE_INTENT).metadata["without_id"] is True


@pytest.mark.parametrize("path,origin", [
    ("/zerodha/open", vocab.ORIGIN_OPEN),
    ("/open/yt/hi", vocab.ORIGIN_OPEN),
    ("/zerodha/r/open", vocab.ORIGIN_R_OPEN),
    ("/r/open", vocab.ORIGIN_R_OPEN),
])
def test_partner_direct_clicks_carry_their_origin(seeded, django_capture_on_commit_callbacks, path, origin):
    _get(path, django_capture_on_commit_callbacks)
    assert Event.objects.get(event_type=vocab.CLICK).metadata["origin"] == origin
    _assert_no_ip_anywhere()


def test_bot_on_the_popup_writes_nothing(seeded, django_capture_on_commit_callbacks):
    for q in ("", "?kite_id=AB1234", "?skip=1"):
        _get("/zerodha/r/wa/KITEID" + q, django_capture_on_commit_callbacks,
             HTTP_USER_AGENT="WhatsApp/2.23.20 A")
    assert Event.objects.count() == 0


# --- datacenter addresses -------------------------------------------------------------

@pytest.fixture
def datacenter(monkeypatch):
    monkeypatch.setattr(netranges, "classify_ip", lambda ip: (True, "EXAMPLE-CLOUD"))
    from apps.referrals import redirect_service
    monkeypatch.setattr(redirect_service, "classify_ip", lambda ip: (True, "EXAMPLE-CLOUD"))


@pytest.mark.urls("tests.urls_share_intent")
def test_datacenter_share_is_marked_bot(seeded, datacenter, django_capture_on_commit_callbacks):
    _get("/zerodha/share/wa/AB1234", django_capture_on_commit_callbacks)
    share = Event.objects.get(event_type=vocab.SHARE_INTENT)
    assert share.is_bot is True
    assert share.metadata["bot_reason"] == netranges.DATACENTER_BOT_REASON
    assert share.person_ref_id is None


def test_datacenter_disclosure_and_popup_are_marked_bot(
    seeded, datacenter, django_capture_on_commit_callbacks
):
    _get("/d/pifs", django_capture_on_commit_callbacks)
    _get("/zerodha/r/wa/KITEID", django_capture_on_commit_callbacks)
    for etype in (vocab.DISCLOSURE_VIEWED, vocab.SHARE_RECOVERY_VIEWED):
        assert Event.objects.get(event_type=etype).is_bot is True


# --- Step 2 of the one-tap message (owner 2026-11-27) --------------------------------

def test_step_two_link_is_tagged_and_is_a_cascade_key(seeded, settings):
    """Rail E-6 spot test: Step 2 is /zerodha/open/wa by default, the path is the cascade
    key `share_onetap_wa_open_path`, and a bad value falls back to the plain open link."""
    from apps.config import preferences as prefkeys
    from apps.config.cascade import set_tenant
    from apps.referrals.share_intent_service import onetap_open_link
    from apps.tenants.resolve import get_bootstrap_tenant

    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    tenant = get_bootstrap_tenant()
    assert onetap_open_link(tenant) == "https://gorefer.in/zerodha/open/wa"
    set_tenant(prefkeys.SHARE_ONETAP_WA_OPEN_PATH, "/open", tenant_id=tenant.id)
    assert onetap_open_link(tenant) == "https://gorefer.in/zerodha/open"
    set_tenant(prefkeys.SHARE_ONETAP_WA_OPEN_PATH, "no slash", tenant_id=tenant.id)
    assert onetap_open_link(tenant) == "https://gorefer.in/zerodha/open"


def test_step_two_tap_lands_on_the_same_page_and_is_counted_apart(
    seeded, django_capture_on_commit_callbacks
):
    plain = _get("/zerodha/open", django_capture_on_commit_callbacks)
    step2 = _get("/zerodha/open/wa", django_capture_on_commit_callbacks)
    assert plain.headers["Location"] == step2.headers["Location"]  # same partner page, same credit
    clicks = Event.objects.filter(event_type=vocab.CLICK).order_by("id")
    channels = [e.metadata.get("channel") for e in clicks]
    assert channels == [None, "WhatsApp"]
