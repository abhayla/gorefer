"""Datacenter network table: classifier + table builder (ADR-019 amendment 2026-11-04).

Pure tests, no database. The DUMP lines below are verbatim rows of the public-domain
iptoasn.com ip2asn-v4/v6 dumps downloaded 2026-11-04 (tab separated: start, end, AS
number, country, AS description) - the real format the refresh command parses.
"""
import gzip
import logging
from pathlib import Path

import pytest

from apps.events import netranges, netranges_refresh
from apps.events.management.commands.setup_schedules import SCHEDULES

DUMP_V4 = [
    "1.38.0.0\t1.38.5.255\t38266\tIN\tVIL-AS-AP - Vodafone Idea Ltd",
    "1.44.96.0\t1.44.96.255\t16509\tUS\tAMAZON-02 - Amazon.com, Inc.",
    "1.187.64.0\t1.187.79.255\t45271\tIN\tVIL-AS-AP - Vodafone Idea Ltd",
    "2.16.0.0\t2.16.2.255\t20940\tNL\tAKAMAI-ASN1 Akamai International B.V.",
    "2.18.241.0\t2.18.241.255\t9498\tIN\tBBIL-AP - BHARTI Airtel Ltd.",
    "2.24.0.0\t2.24.39.255\t47583\tCY\tAS-HOSTINGER Hostinger International Limited",
    "4.0.0.0\t4.19.11.255\t3356\tUS\tLEVEL3 - Level 3 Parent, LLC",
    "5.9.0.0\t5.9.255.255\t24940\tDE\tHETZNER-AS Hetzner Online GmbH",
    "5.101.96.0\t5.101.111.255\t14061\tUS\tDIGITALOCEAN-ASN - DigitalOcean, LLC",
    "8.8.4.0\t8.8.4.255\t15169\tUS\tGOOGLE - Google LLC",
    "16.5.61.0\t16.5.61.255\t54113\tUS\tFASTLY - Fastly, Inc.",
    "17.57.181.0\t17.58.47.255\t714\tUS\tAPPLE-ENGINEERING - Apple Inc.",
    "23.34.252.0\t23.34.255.255\t9829\tIN\tBSNL-NIB - National Internet Backbone",
    "23.62.12.0\t23.62.13.255\t24309\tIN\tCABLELITE-AS-AP - Atria Convergence Technologies Pvt. Ltd. "
    "Broadband Internet Service Provider INDIA",
    "23.228.128.0\t23.228.191.255\t16591\tUS\tGOOGLE-FIBER - Google Fiber Inc.",
    "27.4.0.0\t27.4.87.255\t17488\tIN\tHATHWAY-NET-AP - Hathway IP Over Cable Internet",
    "27.56.128.0\t27.56.135.255\t24560\tIN\tAIRTELBROADBAND-AS-AP - Bharti Airtel Ltd., Telemedia Services",
    "35.96.5.0\t35.96.5.255\t801\tUS\tAMAZON-LEO - Amazon Technologies Inc.",
    "43.224.115.0\t43.224.115.255\t58682\tBD\tLEVEL3-BD - Level3 Carrier Ltd.",
    "49.35.219.0\t49.36.0.255\t55836\tIN\tRELIANCEJIO-IN - Reliance Jio Infocomm Limited",
    "69.171.224.0\t69.171.250.255\t32934\tUS\tFACEBOOK - Facebook, Inc.",
    "104.16.0.0\t104.20.63.255\t13335\tUS\tCLOUDFLARENET - Cloudflare, Inc.",
    "106.192.0.0\t106.192.143.255\t45609\tIN\tBHARTI-MOBILITY-AS-AP - Bharti Airtel Ltd. AS for GPRS Service",
    "109.104.148.0\t109.104.149.255\t25799\tUS\tM247AI-AS-US - 24/7.ai, Inc",
    "117.192.0.0\t117.199.69.255\t9829\tIN\tBSNL-NIB - National Internet Backbone",
    "172.224.0.0\t172.224.5.255\t36183\tUS\tAKAMAI-AS - Akamai Technologies, Inc.",
    "1.0.1.0\t1.0.3.255\t0\tNone\tNot routed",
]
DUMP_V6 = [
    "2001:428:3816::\t2001:428:3816:ffff:ffff:ffff:ffff:ffff\t3356\tUS\tLEVEL3 - Level 3 Parent, LLC",
    "2001:4860::\t2001:4860:1024:ffff:ffff:ffff:ffff:ffff\t15169\tUS\tGOOGLE - Google LLC",
    "2001:df0:45f::\t2001:df0:45f:ffff:ffff:ffff:ffff:ffff\t54113\tUS\tFASTLY - Fastly, Inc.",
    "2001:df0:9ec0::\t2001:df0:9ec0:ffff:ffff:ffff:ffff:ffff\t9498\tIN\tBBIL-AP - BHARTI Airtel Ltd.",
    "2400:5200:401::\t2400:5200:404:ffff:ffff:ffff:ffff:ffff\t55410\tIN\tVIL-AS-AP - Vodafone Idea Ltd",
    "2400:6180::\t2400:6180:0:ffff:ffff:ffff:ffff:ffff\t14061\tUS\tDIGITALOCEAN-ASN - DigitalOcean, LLC",
    "2401:4900:1c00::\t2401:4900:1c03:ffff:ffff:ffff:ffff:ffff\t24560\tIN\tAIRTELBROADBAND-AS-AP - "
    "Bharti Airtel Ltd., Telemedia Services",
    "2403:c00::\t2403:c00:4:ffff:ffff:ffff:ffff:ffff\t17488\tIN\tHATHWAY-NET-AP - "
    "Hathway IP Over Cable Internet",
    "2405:200:1677::\t2405:201:7ff:ffff:ffff:ffff:ffff:ffff\t55836\tIN\tRELIANCEJIO-IN - "
    "Reliance Jio Infocomm Limited",
    "2605:a600::\t2605:a601:ffff:ffff:ffff:ffff:ffff:ffff\t16591\tUS\tGOOGLE-FIBER - Google Fiber Inc.",
    "2a02:26f7:2::\t2a02:26f7:2:ffff:ffff:ffff:ffff:ffff\t36183\tUS\tAKAMAI-AS - Akamai Technologies, Inc.",
    "2a03:2880:f12d::\t2a03:2880:f13a:ffff:ffff:ffff:ffff:ffff\t32934\tUS\tFACEBOOK - Facebook, Inc.",
]

# Networks that must NEVER be kept with the default keywords: Indian consumer ISPs
# (Jio, Airtel, Vi, BSNL, Hathway, ACT) and the CDNs iCloud Private Relay users egress
# through (Cloudflare, Akamai, Fastly), plus the measured near-miss false positives.
NEVER_KEPT_ASNS = {
    "55836", "45609", "9498", "24560", "38266", "45271", "55410", "9829", "17488", "24309",
    "13335", "20940", "36183", "54113",
    "16591", "801", "25799", "58682",
}


def _build(tmp_path, keywords=None) -> netranges.NetworkTable:
    lines = netranges.filter_dump(DUMP_V4 + DUMP_V6, keywords or netranges.KEYWORDS_DEFAULT)
    path = tmp_path / "network-ranges.tsv"
    path.write_text("# header\n" + "\n".join(lines) + "\n", encoding="utf-8")
    table = netranges.load_table(path)
    assert table is not None
    return table


@pytest.fixture
def use_table(tmp_path, monkeypatch):
    """Point the process-wide lazy table at a temp file; returns the file path."""
    path = tmp_path / "network-ranges.tsv"
    monkeypatch.setattr(netranges, "table_path", lambda: path)
    netranges.reset_cache()
    yield path
    netranges.reset_cache()


# --- answer states ------------------------------------------------------------------


def test_ipv4_hit_returns_org(tmp_path):
    t = _build(tmp_path)
    assert t.lookup("69.171.250.1") == (True, "AS32934 FACEBOOK - Facebook, Inc.")
    assert t.lookup("5.9.10.1") == (True, "AS24940 HETZNER-AS Hetzner Online GmbH")
    assert t.lookup("17.58.0.1") == (True, "AS714 APPLE-ENGINEERING - Apple Inc.")


def test_ipv6_hit_returns_org(tmp_path):
    t = _build(tmp_path)
    assert t.lookup("2a03:2880:f12f::1") == (True, "AS32934 FACEBOOK - Facebook, Inc.")
    assert t.lookup("2400:6180::1") == (True, "AS14061 DIGITALOCEAN-ASN - DigitalOcean, LLC")


def test_range_edges_are_inclusive(tmp_path):
    t = _build(tmp_path)
    assert t.lookup("5.9.0.0")[0] is True
    assert t.lookup("5.9.255.255")[0] is True
    assert t.lookup("5.10.0.0") == (False, None)
    assert t.lookup("5.8.255.255") == (False, None)


def test_ipv4_mapped_ipv6_is_looked_up_as_ipv4(tmp_path):
    t = _build(tmp_path)
    assert t.lookup("::ffff:5.9.10.1")[0] is True


@pytest.mark.parametrize("ip", ["49.36.0.1", "2405:201::1", "106.192.0.1", "117.192.0.1",
                                "1.38.0.1", "27.4.0.1", "104.16.0.1", "203.0.113.7"])
def test_not_found_is_not_datacenter(tmp_path, ip):
    assert _build(tmp_path).lookup(ip) == (False, None)


@pytest.mark.parametrize("ip", [None, "", "   "])
def test_missing_ip_is_not_datacenter(tmp_path, ip):
    assert _build(tmp_path).lookup(ip) == (False, None)


@pytest.mark.parametrize("ip", ["not-an-ip", "999.1.1.1", "5.9.10", "2a03:::1:2::3", "unknown"])
def test_malformed_ip_is_not_datacenter(tmp_path, ip):
    assert _build(tmp_path).lookup(ip) == (False, None)


def test_missing_table_fails_open_with_one_warning(use_table, caplog):
    assert not use_table.exists()
    with caplog.at_level(logging.WARNING, logger="apps.events.netranges"):
        assert netranges.classify_ip("5.9.10.1") == (False, None)
        assert netranges.classify_ip("69.171.250.1") == (False, None)
    warnings = [r for r in caplog.records if "network table missing" in r.getMessage()]
    assert len(warnings) == 1


def test_empty_table_is_not_datacenter(use_table):
    use_table.write_text("", encoding="utf-8")
    assert netranges.classify_ip("5.9.10.1") == (False, None)


def test_classify_ip_hit_through_lazy_table(use_table):
    use_table.write_text("5.9.0.0\t5.9.255.255\tAS24940 HETZNER-AS Hetzner Online GmbH\n", encoding="utf-8")
    assert netranges.classify_ip("5.9.10.1") == (True, "AS24940 HETZNER-AS Hetzner Online GmbH")
    assert netranges.classify_ip(None) == (False, None)


def test_table_reloads_when_file_changes(use_table, monkeypatch):
    use_table.write_text("5.9.0.0\t5.9.255.255\tAS24940 Hetzner\n", encoding="utf-8")
    assert netranges.classify_ip("69.171.250.1") == (False, None)
    use_table.write_text("69.171.224.0\t69.171.250.255\tAS32934 Facebook\n", encoding="utf-8")
    import os
    st = use_table.stat()
    os.utime(use_table, (st.st_atime, st.st_mtime + 10))
    monkeypatch.setattr(netranges, "RECHECK_SECONDS", 0)
    assert netranges.classify_ip("69.171.250.1") == (True, "AS32934 Facebook")


def test_corrupt_lines_are_skipped():
    t = netranges.parse_table(["garbage", "5.9.0.0\tnope\tX", "5.9.0.0\t5.9.255.255\tAS24940 H", "# c"])
    assert len(t) == 1 and t.lookup("5.9.1.1") == (True, "AS24940 H")


# --- the table builder (refresh) ----------------------------------------------------


def test_default_keywords_never_keep_indian_isps_or_relay_cdns():
    kept = netranges.filter_dump(DUMP_V4 + DUMP_V6, netranges.KEYWORDS_DEFAULT)
    kept_asns = {line.split("\t")[2].split(" ", 1)[0].removeprefix("AS") for line in kept}
    assert kept_asns & NEVER_KEPT_ASNS == set()
    # and it does keep the measured crawler networks
    assert {"32934", "24940", "714", "47583", "15169", "16509", "14061", "3356"} <= kept_asns


def test_default_keywords_name_no_cdn_or_indian_isp():
    joined = " ".join(netranges.KEYWORDS_DEFAULT).lower()
    for banned in ("cloudflare", "akamai", "fastly", "jio", "airtel", "vodafone", "idea", "bsnl",
                   "hathway", "atria", "reliance"):
        assert banned not in joined


def test_not_routed_rows_are_dropped():
    assert netranges.filter_dump(["1.0.1.0\t1.0.3.255\t0\tNone\tNot routed"], ["not routed"]) == []


def test_refresh_writes_atomically_from_real_format_gz(tmp_path):
    v4 = tmp_path / "ip2asn-v4.tsv.gz"
    v6 = tmp_path / "ip2asn-v6.tsv.gz"
    v4.write_bytes(gzip.compress(("\n".join(DUMP_V4) + "\n").encode()))
    v6.write_bytes(gzip.compress(("\n".join(DUMP_V6) + "\n").encode()))
    out = tmp_path / "var" / "network-ranges.tsv"
    summary = netranges_refresh.refresh_table(sources=[v4, v6], path=out,
                                              keywords=netranges.KEYWORDS_DEFAULT)
    table = netranges.load_table(out)
    assert summary["ranges"] == len(table) > 0
    assert table.lookup("69.171.250.1")[0] and table.lookup("2a03:2880:f12f::1")[0]
    assert table.lookup("49.36.0.1") == (False, None)
    assert [p.name for p in out.parent.iterdir()] == ["network-ranges.tsv"]  # no temp left


def test_failed_refresh_keeps_old_table(tmp_path, monkeypatch):
    out = tmp_path / "network-ranges.tsv"
    out.write_text("5.9.0.0\t5.9.255.255\tAS24940 OLD\n", encoding="utf-8")

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(netranges_refresh, "_download", boom)
    with pytest.raises(netranges_refresh.RefreshError):
        netranges_refresh.refresh_table(path=out, keywords=["hetzner"])
    assert out.read_text(encoding="utf-8") == "5.9.0.0\t5.9.255.255\tAS24940 OLD\n"
    # zero matches also keeps the old table
    bad = tmp_path / "x.tsv"
    bad.write_text(DUMP_V4[0] + "\n", encoding="utf-8")
    with pytest.raises(netranges_refresh.RefreshError):
        netranges_refresh.refresh_table(sources=[bad], path=out, keywords=["hetzner"])
    assert "OLD" in out.read_text(encoding="utf-8")


def test_scheduled_refresh_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(netranges, "table_path", lambda: Path(tmp_path) / "t.tsv")
    monkeypatch.setattr(netranges, "keywords", lambda: ["hetzner"])
    monkeypatch.setattr(netranges_refresh, "_download", lambda url: (_ for _ in ()).throw(OSError("x")))
    assert netranges_refresh.scheduled_refresh().startswith("failed")


def test_weekly_refresh_is_scheduled():
    assert SCHEDULES["network_table_refresh"] == (
        "apps.events.netranges_refresh.scheduled_refresh", 10080)


def test_click_path_module_imports_no_http_client():
    src = Path(netranges.__file__).read_text(encoding="utf-8")
    assert "urllib" not in src and "import requests" not in src


# --- warm at worker boot ----------------------------------------------------------------


def _write_small_table(path):
    lines = netranges.filter_dump(DUMP_V4 + DUMP_V6, netranges.KEYWORDS_DEFAULT)
    path.write_text("# header" + chr(10) + chr(10).join(lines) + chr(10), encoding="utf-8")


def test_wsgi_import_loads_table_before_first_classify(use_table, monkeypatch):
    import importlib

    import gorefer.wsgi

    _write_small_table(use_table)
    netranges.reset_cache()
    importlib.reload(gorefer.wsgi)
    assert netranges._loaded is True and netranges._table is not None
    # first classify_ip must not load: make any load blow up
    monkeypatch.setattr(netranges, "load_table", lambda p: (_ for _ in ()).throw(AssertionError("lazy load")))
    assert netranges.classify_ip("1.44.96.10") == (True, "AS16509 AMAZON-02 - Amazon.com, Inc.")


def test_wsgi_import_with_missing_table_does_not_raise(use_table):
    import importlib

    import gorefer.wsgi

    assert not use_table.exists()
    netranges.reset_cache()
    importlib.reload(gorefer.wsgi)  # must not raise
    assert netranges.warm() is False
    assert netranges.classify_ip("1.44.96.10") == (False, None)


def test_warm_swallows_unexpected_errors(monkeypatch):
    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(netranges, "_get_table", boom)
    assert netranges.warm() is False
