# GoRefer — Deploy Target (AUTHORITATIVE)

> **Read this before any deploy, DNS, TLS, or infra decision.** This file is the single source of truth for *where GoRefer runs*. If any other doc, note, or assumption disagrees with this, **this file wins** — fix the other doc.
>
> **Locked:** 2026-07-09 by Abhay. **Applies to:** Sprint 1+ production of `gorefer.in`.

---

## The target

**GoRefer production runs on the Hostinger VPS `72.61.240.224`.**

| Item | Value |
|---|---|
| Host | Hostinger VPS |
| Public IP | **`72.61.240.224`** |
| Hostname | `srv1707492.hstgr.cloud` |
| OS | Ubuntu 24.04 |
| Access | **SSH only** — key `~/.ssh/firekaro_v6_vps`, user `root` |
| Web server | **Linux nginx** (multi-site vhosts) |
| TLS | **certbot / Let's Encrypt** (origin certs) |
| Database | **fresh local Postgres on this box** (NOT the local dev `gorefer_dev`) |
| App runtime | Django via gunicorn + systemd |
| Secrets | `C:\Abhay\VideCoding\GLOBAL.env` — never commit |
| Co-tenants | firekaro / realfuelprices / bestdemataccount / calculatekaro |

## NOT the target

- ❌ **`103.118.16.189`** — this is the **local Windows fleet box** the repo/dev sits on (Windows nginx `C:\Apps\nginx`, Cloudflare-edge TLS, dev Postgres `gorefer_dev`, and the sites algochanakya.com / ipodhan / cricscores.in / bestdemataccount.com). GoRefer is **not** deployed here. Its infra facts (Windows nginx, CF-edge TLS, "no grey-cloud needed") **do not apply** to production.
- Do not deploy "on the box the repo happens to be on." Deploy **remotely to `72.61.240.224` over SSH.**

## DNS + TLS (Cloudflare)

`gorefer.in` DNS is on **Cloudflare** (account `Abhayinfosys@gmail.com`).

| Record | Value | Proxy during cert issuance | Proxy after cert |
|---|---|---|---|
| `gorefer.in` (apex) A | `72.61.240.224` | **DNS-only (grey)** | Proxied |
| `www` CNAME | `gorefer.in` | **DNS-only (grey)** | Proxied |

**Ordering (Linux + certbot):** records stay **grey-cloud** so certbot's HTTP-01 challenge reaches the origin; once the cert issues, flip both to **Proxied** with Cloudflare **SSL/TLS = Full (strict)**.

- **DA owns** the Cloudflare records (created via the dashboard; the CF API token on file is read-only).
- **Engineer owns** the app + nginx vhost + certbot on `72.61.240.224`.
- Current state (2026-07-09): records set to `72.61.240.224` grey-cloud; GoDaddy parking A records deleted; awaiting cert issuance to flip to Proxied.

## P5 deploy checklist — background worker (REQUIRED, not optional)

> **Why this is here:** "the retry exists" and "the retry is running" are different
> claims. The Zoho WRITE retry + backfill sweep is *code* in the repo, but it only
> ever executes if the two steps below are done on the box. Skip them and a lead
> stranded by a transient Zoho outage **never retries** — silently, and precisely the
> failure the retry layer was built to prevent. (DA review 2026-07-16, carried
> forward as a hard P5 step.)

On `72.61.240.224`, after `migrate` + `seed_program`:

| # | Step | Command | Why |
|---|---|---|---|
| 1 | Async mode on | set `Q_ASYNC=true` in the prod env | Dev/CI default is inline (`false`); leaving it inline means no worker semantics in prod. |
| 2 | Register schedules | `python manage.py setup_schedules` | Idempotent. Registers the rollup recompute (5 min) **and the Zoho WRITE backfill sweep (10 min)**. |
| 3 | Run the worker | `python manage.py qcluster` under **systemd** (not a shell) | Executes the async Zoho lead upsert, WATI sends + terminal-status polling, and the schedules. A hand-started qcluster dies with the session. |
| 4 | Verify | admin → Leads → **"Zoho sync"** filter | `unsynced` / `needs attention` / `awaiting retry` should not accumulate. A growing "awaiting retry" with a dead worker is the signature of skipping steps 2–3. |

**Gate:** steps 1–3 are **required before `ENABLE_ZOHO_WRITE` is flipped on**. Without
them the write leg still works on the happy path, so the omission is invisible until
the first Zoho outage — by which time leads are already stranded and Ashok never sees
them in the CRM. Exhausted leads (attempts ≥ 5) are deliberately left for a human and
surface under "needs attention" with a **"Retry Zoho sync"** action.

## Rendered check — what curl cannot see (REQUIRED after any CSS/template change)

> **Why this is here:** the Settings toggles shipped to prod rendering as an invisible /
> collapsed switch, and **every** existing check passed while it was broken. The HTML was
> correct, so `curl | grep 'enable_zoho_write'` found the input and reported "3 checkboxes
> present"; unit tests assert logic, not rendering. The class `bg-ink-300/50` simply
> emitted **no CSS rule** — a silent Tailwind failure, no build error. Nothing that reads
> HTML or runs Python can catch that; only something that resolves CSS can.
> (DA bug 2026-07-16.)

**On every PR (automatic, no browser):** `tests/test_css_utilities_resolve.py` asserts that
every styling class the templates use actually resolves to a rule in the built
`static/css/app.css`, and that the colour tokens stay channel triplets. This catches the
whole "utility silently vanished" class — purge dropped it, or the config refuses to emit
it — deterministically and in ~0.2s. It is the primary guard; it would have caught this bug
on the PR that introduced it.

**After deploying any CSS/template change, verify the real page renders** (a rendered check
still catches what static analysis cannot: overlap, stacking, layout collapse). No headless
browser is installed on the box, so drive it from a session that has one:

| Check | How | Expected |
|---|---|---|
| Toggle geometry | Load `/admin-panel/preferences` (authed) and measure a toggle's track span | computed **width ≥ 40px** (design = 44px) and **height ≈ 24px** |
| Toggle visibility | Read the track's `backgroundColor` for an **OFF** toggle | a real colour (`rgba(148,163,184,0.5)`), **never** `rgba(0, 0, 0, 0)` — transparent = the bug |
| Token resolution | Scan computed styles for any value still containing `var(` | **zero** — an unresolved token means a broken colour form |

```js
// Paste in the browser console on /admin-panel/preferences. Prints a PASS/FAIL line.
const t = [...document.querySelectorAll('label.relative.inline-flex')].map(l => {
  const s = l.querySelector('span'), cb = l.querySelector('input[type=checkbox]');
  const r = s.getBoundingClientRect();
  return { name: cb?.name, on: cb?.checked, w: Math.round(r.width),
           bg: getComputedStyle(s).backgroundColor };
});
console.log(t.every(x => x.w >= 40 && x.bg !== 'rgba(0, 0, 0, 0)')
  ? `PASS — ${t.length} toggles render` : 'FAIL', t);
```

**Gate:** run this after any deploy that touches `static/css/*`, `tailwind.config.js`, or a
template with themed classes. A green curl check is **not** evidence the page renders.

## DF-2 wax-seal — the Zoho-side signer contract (needed before flipping the flag)

> **Order matters:** `ENABLE_ZOHO_WEBHOOK_HMAC=true` makes the seal **mandatory** (the
> static key stops working). Flip it **only after** the Zoho-side Deluge signer below
> is live, or every real webhook 401s.

The Zoho Deluge function must send three headers with each status webhook:

| Header | Value |
|---|---|
| `X-Zoho-Timestamp` | current epoch seconds (integer) |
| `X-Zoho-Nonce` | a fresh unique string per request (never reused) |
| `X-Zoho-Signature` | `HMAC-SHA256(secret, "<timestamp>.<nonce>.<raw_body>")`, hex |

Rules the signer must honour (GoRefer rejects otherwise):
- The signed material is `timestamp + "." + nonce + "." + raw_body` — the timestamp and
  nonce are **inside** the signature, not merely alongside it.
- `raw_body` is the **exact bytes sent**. Re-serializing the JSON after signing (key
  reordering, whitespace changes) breaks verification.
- The nonce must be unique per request — a reused nonce is treated as a replay.
- Requests older/newer than `ZOHO_WEBHOOK_MAX_SKEW_SECONDS` (default 300) are rejected.
- The shared secret lives in `ZOHO_WEBHOOK_HMAC_SECRET` on GoRefer and a Zoho Variable
  on the Zoho side — **never inline in Deluge** (doc-08 A7, the hardcoded-JWT lesson).

Rollout: deploy the signer → set `ZOHO_WEBHOOK_HMAC_SECRET` on both sides → flip
`ENABLE_ZOHO_WEBHOOK_HMAC=true`. Rollback is flipping the flag back off.

## Deploy runner — `scripts/deploy.sh`

> **Why this exists:** every prior deploy re-typed the same manual pattern by hand — dozens
> of COORDINATION.md entries read "git-show pipe … blob-hash-verified." `scripts/deploy.sh`
> mechanizes that exact pattern so a deploy is one command, not a re-derivation each time.

```bash
scripts/deploy.sh                # deploy local HEAD (refuses a dirty tree)
scripts/deploy.sh <commit-ish>   # deploy a specific commit/branch/tag
scripts/deploy.sh --force        # allow a dirty working tree (still deploys HEAD)
```

What it does: streams the exact committed tree for the target commit into `/var/www/gorefer`
via `git archive | ssh … tar -x` (never touching the box's runtime state — `.env`, `.venv`,
`staticfiles/`, `DEPLOYED_SHA`), hash-verifies every file byte-exact against its git blob,
runs `migrate` + `collectstatic --noinput` + `manage.py check` as `www-data`, restarts
`gorefer` + `gorefer-qcluster` and waits for both (plus `nginx`) to report `active`, writes
`DEPLOYED_SHA` on the box, then probes `https://gorefer.in/api/health` and fails the run if it
doesn't return 200.

Access, by default, is `root@72.61.240.224` with key `~/.ssh/firekaro_v6_vps` — exactly this
doc's "The target" table above. Override via `DEPLOY_SSH_HOST` / `DEPLOY_SSH_KEY` /
`DEPLOY_SSH_USER` / `DEPLOY_REMOTE_DIR` / `DEPLOY_HEALTH_URL` env vars if a local setup needs
something different; the script never assumes an SSH config alias exists.

**Windows git-archive CRLF trap:** a Windows dev box with global `core.autocrlf=true` makes a
bare `git archive` silently rewrite LF → CRLF in every text file it streams, which then fails
hash verification against the LF git blobs — the same trap noted elsewhere in this repo's
history from manual deploys. The script forces `-c core.autocrlf=false` on the archive step so
this can't recur.

## Why Hostinger (not the local box)

Abhay's decision: keep GoRefer on the Hostinger multi-site VPS alongside the other production sites, on its proven Linux nginx + certbot pattern. The local Windows box is a dev/other-fleet machine, not GoRefer's production home.
