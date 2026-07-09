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

## Why Hostinger (not the local box)

Abhay's decision: keep GoRefer on the Hostinger multi-site VPS alongside the other production sites, on its proven Linux nginx + certbot pattern. The local Windows box is a dev/other-fleet machine, not GoRefer's production home.
