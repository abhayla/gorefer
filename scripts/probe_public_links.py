"""Probe every public GoRefer link once, without following redirects (read-only check).

    python scripts/probe_public_links.py https://gorefer.in          # after a deploy
    python scripts/probe_public_links.py http://127.0.0.1:8000       # a local build
    PROBE_CID=AB1234 python scripts/probe_public_links.py URL        # links with an ID

Prints one line per link: the status, where it goes, and for the WhatsApp / Telegram / X
share redirects the links inside the pre-typed message. Flags any 5xx, network error, or a
no-ID WhatsApp message whose Step 1 is the bare /r/wa (the 2026-11-18 finding).

Links with an ID write a share/click record under that ID on the target site, so the
default ID is the made-up ZZ9999 (prod's strict validator rejects it, creating nothing).
Pass a real ID only when you mean to. Uses HTTPS_PROXY when set. Stdlib only.
"""
import http.client
import os
import re
import sys
from urllib.parse import parse_qs, unquote, urlparse

BASE = sys.argv[1].rstrip("/")
UA = {
    "human": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
    "bot": "WhatsApp/2.23.20.0",
}["bot" if "--ua" in sys.argv and sys.argv[sys.argv.index("--ua") + 1] == "bot" else "human"]

CID = os.environ.get("PROBE_CID", "ZZ9999")
LINKS = [
    # one-tap share: with ID, no ID, skip, placeholder, languages, channels
    f"/zerodha/share/wa/{CID}", f"/share/wa/{CID}", f"/zerodha/share/wa/{CID}?lang=hi",
    "/zerodha/share/wa/KITEID", "/zerodha/share/wa/", "/zerodha/share/wa", "/share/wa", "/share/wa/",
    "/zerodha/share/wa/KITEID?skip=1", "/zerodha/share/wa/?skip=1", "/zerodha/share/wa?skip=1",
    "/share/wa?skip=1", "/share/wa/?skip=1", "/zerodha/share/wa/?skip=1&lang=hi",
    f"/zerodha/share/wa/KITEID?kite_id={CID}",
    f"/zerodha/share/tg/{CID}", f"/zerodha/share/x/{CID}",
    "/zerodha/share/tg/?skip=1", "/zerodha/share/x/?skip=1",
    f"/zerodha/share/fb/{CID}", f"/zerodha/share/li/{CID}", "/share/fb/",
    # referral links
    f"/zerodha/r/wa/{CID}", f"/r/wa/{CID}", f"/zerodha/r/{CID}", f"/r/{CID}", f"/zerodha/r/tg/{CID}",
    f"/zerodha/r/x/{CID}", f"/zerodha/r/{CID}/continue", f"/zerodha/r/wa/{CID}/continue",
    "/zerodha/r/wa", "/zerodha/r/wa/", "/r/wa", "/r/wa/", "/zerodha/r/", "/zerodha/r", "/r/", "/r",
    "/zerodha/r/wa/KITEID", "/zerodha/r/wa/KITEID?skip=1", f"/zerodha/r/wa/KITEID?kite_id={CID}",
    "/zerodha/r/open", "/r/open", "/r/WA",
    # partner-direct + tagged
    "/zerodha/open", "/open", "/zerodha/open/yt", "/zerodha/open/yt/hi", "/open/yt/hi", "/zerodha/open/ig/mr",
    "/zerodha/open/yt/xx", "/zerodha/open/zz/hi", "/Zerodha/Open/YT/HI/",
    # fallbacks and other pages
    f"/zerodha/open/{CID}", f"/groww/r/{CID}", "/zeroda/open", "/anything/at/all", "/zerodha/opn/yt/hi",
    "/d/pifs", "/privacy", "/", "/login/", "/my/referrals", "/rr", f"/rr/{CID}", "/hub",
    "/admin-panel/nope", "/wp-login.php", "/og/card.png", "/api/health",
]


def get(path):
    import ssl

    u = urlparse(BASE + path)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if u.scheme == "https" and proxy:
        p = urlparse(proxy)
        ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt")
        conn = http.client.HTTPSConnection(p.hostname, p.port, timeout=30, context=ctx)
        hdrs = {}
        if p.username:
            import base64
            hdrs["Proxy-Authorization"] = "Basic " + base64.b64encode(
                f"{unquote(p.username)}:{unquote(p.password or '')}".encode()).decode()
        conn.set_tunnel(u.hostname, 443, headers=hdrs)
    else:
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = cls(u.netloc, timeout=20)
    conn.request("GET", u.path + (("?" + u.query) if u.query else ""), headers={"User-Agent": UA})
    r = conn.getresponse()
    body = r.read(4000).decode("utf-8", "replace")
    return r.status, r.getheader("Location") or "", body


def describe(status, loc, body):
    if loc.startswith(("https://wa.me", "https://api.whatsapp.com", "whatsapp:")):
        text = parse_qs(urlparse(loc).query).get("text", [""])[0]
        links = re.findall(r"https?://\S+", text)
        step1 = re.search(r"(?:Step 1|स्टेप 1)[^\n]*\n(\S+)", text)
        return f"WhatsApp msg | step1={step1.group(1) if step1 else '-'} | links={links[:3]}"
    if "t.me/share" in loc or "x.com/intent" in loc or "twitter.com/intent" in loc:
        q = parse_qs(urlparse(loc).query)
        txt = (q.get("text", [""])[0] + " " + q.get("url", [""])[0])
        found = re.findall(r"https?://[^\s]+", txt)[:2]
        return f"{urlparse(loc).netloc} | links={found}"
    if loc:
        return f"-> {unquote(loc)}"
    title = re.search(r"<title>(.*?)</title>", body, re.S)
    return f"page: {title.group(1).strip()[:70] if title else body[:60]!r}"


bad = 0
for p in LINKS:
    try:
        s, loc, body = get(p)
        line = describe(s, loc, body)
    except Exception as e:  # network trouble is a result too
        s, line = "ERR", repr(e)
    server_error = s == "ERR" or (isinstance(s, int) and s >= 500)
    if server_error or "step1=https://gorefer.in/r/wa " in line:
        bad += 1
    print(f"{s!s:>4}  {p:45}  {line}")
print(f"\n{len(LINKS)} links, {bad} flagged (5xx / error / bare /r/wa step 1)")
sys.exit(1 if bad else 0)
