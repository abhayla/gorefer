# GoRefer nginx — origin lockdown (Cloudflare-only) + release-layout paths

## `gorefer-paths.conf` (T-162)

The `location` blocks for the release-directory layout: `/static/` is served from
`/var/www/gorefer/shared/staticfiles/` (the shared path every release symlinks in), and
`/` proxies to gunicorn on `127.0.0.1:8000`. Because nginx touches neither the release
directories nor the `current` symlink, **a deploy or a rollback needs no nginx reload** —
the pointer flip plus a service restart is the whole cutover. Applied at first cutover;
see `docs/deploy/DEPLOY-TARGET.md`.

## `cloudflare-allow.conf`

An nginx `allow`/`deny` snippet that restricts the GoRefer origin to **Cloudflare edge
IP ranges only**, closing the direct-to-origin bypass the Fable5 verifier flagged: before
this, `https://<origin-ip>/…` answered 200, so an attacker who knew the origin IP could
connect directly and forge `X-Forwarded-For` headers to defeat the hop-based client-IP
resolution (and any IP allowlist). With the origin locked to Cloudflare, every request
that reaches the app provably transited Cloudflare, so `DJANGO_TRUSTED_PROXY_HOPS=2`
(Cloudflare → nginx) is now **enforced**, not merely assumed.

### How it's wired (prod: `<PROD-VPS>`)

- Installed at `/etc/nginx/snippets/cloudflare-allow.conf`.
- `include`d inside the **`location /`** of the gorefer.in **:443** server block (the app
  + webhook proxy), just before `proxy_pass`. It is intentionally NOT applied to the
  `:80 /.well-known/acme-challenge/` location, so **certbot renewals keep working**
  (Let's Encrypt validates over :80 directly, not via Cloudflare).
- No `real_ip` restoration is used: `$remote_addr` at nginx stays the Cloudflare edge IP
  (which the allowlist matches), and the app reads the real client from the hop-2
  `X-Forwarded-For` entry. This avoids the `realip`-vs-`allow` ordering trap (real_ip
  would rewrite `$remote_addr` before `allow`/`deny`, blocking real users).

### Verified behaviour

| Path | Result |
|---|---|
| `https://gorefer.in/…` (via Cloudflare — real users + Zoho webhook) | 200 — unaffected |
| `https://<origin-ip>/…` (direct-to-origin bypass) | **403** — blocked |
| `http://gorefer.in/.well-known/acme-challenge/…` (:80, certbot) | reachable — renewals OK |
| Other sites on the same nginx (firekaro.com, …) | unaffected |

### Updating the Cloudflare ranges

Cloudflare's IP ranges change rarely. To refresh:

```bash
curl -s https://www.cloudflare.com/ips-v4   # regenerate the allow lines
curl -s https://www.cloudflare.com/ips-v6
# rebuild the snippet, then on the box:
sudo install -m 644 cloudflare-allow.conf /etc/nginx/snippets/cloudflare-allow.conf
sudo nginx -t && sudo systemctl reload nginx
```

A pre-change backup of the site config lives at `/etc/nginx/backups/gorefer.in.bak-<ts>`.
