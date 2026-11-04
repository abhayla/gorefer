"""Datacenter/crawler clicks are bots for COUNTING only (ADR-019 amendment 2026-11-04).

The response a datacenter IP gets is byte-for-byte the same route as a residential IP
(a real person on a VPN must still reach Zerodha); only Event.is_bot + metadata change.
IPs are public provider ranges (Facebook, Hetzner) and TEST-NET / Jio public ranges.
"""
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config.models import ConfigCentral
from apps.events import netranges, netranges_refresh
from apps.events.models import ClickNonce, DirtyPeriod, Event, VisitorPII
from apps.referrals.models import Referral

TABLE = (
    "69.171.224.0\t69.171.250.255\tAS32934 FACEBOOK - Facebook, Inc.\n"
    "5.9.0.0\t5.9.255.255\tAS24940 HETZNER-AS Hetzner Online GmbH\n"
    "2a03:2880:f12d::\t2a03:2880:f13a:ffff:ffff:ffff:ffff:ffff\tAS32934 FACEBOOK - Facebook, Inc.\n"
)
FB = "AS32934 FACEBOOK - Facebook, Inc."
HZ = "AS24940 HETZNER-AS Hetzner Online GmbH"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36"
RESIDENTIAL = "49.36.0.1"   # Reliance Jio
DATACENTER = "5.9.10.1"     # Hetzner


@pytest.fixture
def table(tmp_path, monkeypatch):
    path = tmp_path / "network-ranges.tsv"
    path.write_text(TABLE, encoding="utf-8")
    monkeypatch.setattr(netranges, "table_path", lambda: path)
    netranges.reset_cache()
    yield path
    netranges.reset_cache()


@pytest.fixture
def seeded(db):
    call_command("seed_program")


def _hit(path, ip, capture):
    with capture(execute=True):
        return Client().get(path, HTTP_USER_AGENT=UA, REMOTE_ADDR=ip)


def _clicks():
    return list(Event.objects.filter(event_type="click").order_by("id"))


def test_response_identical_and_only_counting_flag_changes(
    seeded, table, django_capture_on_commit_callbacks
):
    for path in ("/r/RJ4521", "/zerodha/open", "/r/wa/RJ4521"):
        Event.objects.all().delete()
        home = _hit(path, RESIDENTIAL, django_capture_on_commit_callbacks)
        dc = _hit(path, DATACENTER, django_capture_on_commit_callbacks)
        assert dc.status_code == home.status_code, path
        assert dc.headers.get("Location") == home.headers.get("Location"), path
        assert [t.name for t in dc.templates] == [t.name for t in home.templates], path
        human, bot = _clicks()
        assert (human.is_bot, human.metadata.get("bot_reason")) == (False, None), path
        assert bot.is_bot is True, path
        assert {k: bot.metadata[k] for k in ("bot_reason", "network")} == {
            "bot_reason": "datacenter", "network": HZ}, path
    # /zerodha/open is a 302 to the partner, so the VPN user still reaches Zerodha
    assert _hit("/zerodha/open", DATACENTER, django_capture_on_commit_callbacks)["Location"] == \
        "https://signup.zerodha.com/?c=ZMPHZC"


def test_landing_twin_flagged_lazy_referral_kept_first_click_not_stamped(
    seeded, table, django_capture_on_commit_callbacks
):
    resp = _hit("/r/AB1234", "2a03:2880:f12f::1", django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    ref = Referral.objects.get(referral_identity__client_id="AB1234")  # lazy creation unchanged
    evs = {e.event_type: e for e in Event.objects.filter(referral=ref)}
    for et in ("click", "landing_viewed"):
        assert evs[et].is_bot is True
        assert evs[et].metadata == {"bot_reason": "datacenter", "network": FB}
    assert ref.first_click_at is None
    assert VisitorPII.objects.get().raw_ip == "2a03:2880:f12f::1"  # PII still recorded


def test_missing_table_fails_open_click_counts_as_human(
    seeded, tmp_path, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(netranges, "table_path", lambda: tmp_path / "absent.tsv")
    netranges.reset_cache()
    try:
        resp = _hit("/r/RJ4521", DATACENTER, django_capture_on_commit_callbacks)
    finally:
        netranges.reset_cache()
    assert resp.status_code == 200
    assert [c.is_bot for c in _clicks()] == [False]


def test_beacon_never_flips_datacenter_click_to_human(seeded, table, django_capture_on_commit_callbacks):
    c = Client()
    with django_capture_on_commit_callbacks(execute=True):
        c.get("/r/RJ4521", HTTP_USER_AGENT=UA, REMOTE_ADDR=DATACENTER)
    nonce = ClickNonce.objects.get()
    resp = c.post("/api/click/confirm", content_type="application/json",
                  data={"client_id": "RJ4521", "nonce": nonce.nonce,
                        "visitor_id": c.cookies["gr_vid"].value})
    assert resp.status_code == 202
    assert Event.objects.filter(is_bot=False).count() == 0
    hc = Event.objects.get(event_type="human_confirmed")
    assert (hc.is_bot, hc.is_confirmed_human, hc.metadata) == (
        True, False, {"bot_reason": "datacenter", "network": HZ})
    assert Event.objects.get(event_type="click").is_confirmed_human is False


def test_keywords_are_a_cascade_key_e6(db, tmp_path):
    """Rail E-6 spot test: the keyword list resolves from the cascade, and the refresh obeys it."""
    assert netranges.keywords() == netranges.KEYWORDS_DEFAULT
    ConfigCentral.objects.create(key=netranges.KEYWORDS_KEY, value=["hetzner"])
    assert netranges.keywords() == ["hetzner"]
    src = tmp_path / "dump.tsv"
    src.write_text(
        "5.9.0.0\t5.9.255.255\t24940\tDE\tHETZNER-AS Hetzner Online GmbH\n"
        "69.171.224.0\t69.171.250.255\t32934\tUS\tFACEBOOK - Facebook, Inc.\n", encoding="utf-8")
    out = tmp_path / "t.tsv"
    netranges_refresh.refresh_table(sources=[src], path=out)
    t = netranges.load_table(out)
    assert t.lookup(DATACENTER)[0] is True and t.lookup("69.171.250.1") == (False, None)
    ConfigCentral.objects.create(key=netranges.TABLE_PATH_KEY, value=str(out))
    assert netranges.table_path() == out


def test_reclassify_dry_run_then_apply_is_idempotent(seeded, table, django_capture_on_commit_callbacks):
    # Record three clicks BEFORE the fix existed: point the table at nothing first.
    netranges.reset_cache()
    real = netranges.table_path
    netranges.table_path = lambda: table.parent / "absent.tsv"
    try:
        _hit("/r/RJ4521", DATACENTER, django_capture_on_commit_callbacks)            # referral, Hetzner
        _hit("/zerodha/open", "69.171.250.1", django_capture_on_commit_callbacks)  # partner-direct, FB
        _hit("/r/RJ4521", RESIDENTIAL, django_capture_on_commit_callbacks)           # human, Jio
        _hit("/zerodha/open", "69.171.250.2", django_capture_on_commit_callbacks)  # FB, PII erased below
    finally:
        netranges.table_path = real
        netranges.reset_cache()
    erased = VisitorPII.objects.get(raw_ip="69.171.250.2")
    erased.raw_ip = None
    erased.save()
    Event.objects.filter(event_type="click").update(metadata={"channel": "WhatsApp"})
    assert Event.objects.filter(is_bot=True).count() == 0
    pii_before = list(VisitorPII.objects.order_by("id").values_list("id", "raw_ip", "visitor_id"))
    DirtyPeriod.objects.all().delete()

    out = StringIO()
    call_command("reclassify_datacenter_clicks", "--table", str(table), stdout=out)
    text = out.getvalue()
    assert "DRY RUN" in text and "datacenter clicks: 2" in text
    assert "partner-direct: 1" in text and "referral: 1" in text
    assert Event.objects.filter(is_bot=True).count() == 0          # dry run wrote nothing
    assert DirtyPeriod.objects.count() == 0

    call_command("reclassify_datacenter_clicks", "--table", str(table), "--apply", stdout=StringIO())
    bots = Event.objects.filter(is_bot=True, event_type="click").order_by("id")
    assert [b.metadata for b in bots] == [
        {"channel": "WhatsApp", "bot_reason": "datacenter", "network": HZ},
        {"channel": "WhatsApp", "bot_reason": "datacenter", "network": FB},
    ]
    assert Event.objects.filter(event_type="landing_viewed", is_bot=True).count() == 1  # Hetzner's twin
    assert Event.objects.filter(event_type="click", is_bot=False).count() == 2  # Jio + erased-PII
    assert DirtyPeriod.objects.filter(processed_at__isnull=True).count() == 1
    assert list(VisitorPII.objects.order_by("id").values_list("id", "raw_ip", "visitor_id")) == pii_before

    again = StringIO()
    call_command("reclassify_datacenter_clicks", "--table", str(table), "--apply", stdout=again)
    assert "datacenter clicks: 0" in again.getvalue()


def test_reclassify_refuses_without_a_table(db, tmp_path):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="missing or empty"):
        call_command("reclassify_datacenter_clicks", "--table", str(tmp_path / "none.tsv"))
