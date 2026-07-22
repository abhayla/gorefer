# GoRefer — CURRENT STATE (read this FIRST, before COORDINATION archaeology)

> **What this is.** The verified now-state snapshot. `COORDINATION.md` (~3,700 lines) is the
> append-only log of record — this file is the **cache of its conclusion**, so a session never
> has to reconstruct "now" from a tail read (the 2026-07-21 incident: a mis-computed tail
> offset made the Engineer re-stage a go-live that was already live; see the CORRECTION entry).
>
> **Update rule (protocol):** whoever changes state — a flag flip, a deploy, a mission
> start/finish, a template approval — updates this file **in the same turn** as their
> COORDINATION entry. If this file and COORDINATION disagree, the newest COORDINATION entry
> wins; if either disagrees with the live system, **the live system wins** — verify, don't
> trust (commands at the bottom).
>
> **Last updated:** 2026-07-22 (Engineer, explorer column sorting deploy) — deploy + health verified live; flag values below carry the 2026-07-21 verification date.

## Production

| Fact | Value |
|---|---|
| Deployed SHA | `d68f6bd` (PR #23 — explorer status derives funnel depth from events + bot-free last activity; on top of #22 sortable columns. Deployed 2026-07-22, live-verified: authed render 200, derived status mix live, health 200) |
| Host | Hostinger VPS `72.61.240.224`, Cloudflare-proxied, gunicorn + qcluster (`Q_ASYNC=true`) |
| DB | `gorefer_prod` (Postgres) — migration `accounts.0001` applied |

## Integration flags — LIVE VALUES (cascade-resolved, verified 2026-07-21)

| Flag | State | Since / note |
|---|---|---|
| `ENABLE_WATI_SEND` | **ON** | Settings override ~17-Jul. `WATI_ALLOW_ALL_RECIPIENTS="true"` — allowlist OPEN, real sends to real recipients daily |
| `ENABLE_ZOHO_WRITE` | **ON** | Settings override ~17-Jul (DF-9 effectively closed then) |
| `ENABLE_ZOHO_READ` | **ON** | Settings override ~17-Jul |
| `ENABLE_ZOHO_WEBHOOK_HMAC` | **ON** | 18-Jul; Deluge signer pasted + workflow rule active in Zoho; seal proven end-to-end |
| `ENABLE_CUSTOMER_LOGIN` | **ON** | 21-Jul (M13 go-live, owner "go"): prod `.env` true. `/login/` live (Google OAuth primary + OTP fallback), `/my/referrals` live, admin Verifications queue live |
| `ENABLE_OTP_LOGIN` | **ON** | 21-Jul: AUTH template `gr_platform_gorefer_login_otp_en_2026_07_21` APPROVED by Meta + live-verified DELIVERED (`waTemplateId 27564734539863645`) |

The prod `.env` lines say `false` for the three integration flags — those are **overridden
defaults**; the truth is the ConfigGlobal override read through `resolve_flag()`. Never read
`.env` alone for flag state.

## Zoho ingest — LIVE

Conversion webhook (`POST /api/zoho/status-webhook`) sealed + ingesting. Conversions in DB:
`GW5500` (opened 2026-05-02, historical import) · `RJ4521` (opened 18-Jul, webhook-ingested
same evening). Zoho Variable `gorefer_webhook_secret` exists and matches prod.

## Daily report (O-6a / R-DRR)

Three-sided (Zoho supposed-to-send ⋈ Wati delivered ⋈ GoRefer funnel), scheduled 21:30 IST
(`Wati-DailyDeliveryReport` task; engine `5Wealths\Wati-Project\daily_report.py`).
`GOREFER_ZOHO_INGEST_LIVE=true` — accounts-opened line shows real numbers. WhatsApp summary
template: v3 `gr_platform_gorefer_funnel_report_en_2026_07_21` **PENDING at Meta**
(auto-cutover v3→v2→v1 on approval).

## In flight

- **M13 is DONE and LIVE** (2026-07-21): PR #20 merged + deployed; Google OAuth creds in prod
  `.env` (owner-created); OTP AUTH template approved + delivery-verified; both login flags ON.
  Contract: `docs/sprint2/S2-05-M13-Referrer-Login-Goal-Contract.md`. Q-M-OTP-2 CLOSED.
  (Correction to an earlier line here: PR #12/Q-M-OTP was in fact MERGED 2026-07-16 — the
  "held" note was stale; M13 built on it.)
- Known messaging problem: delivery rate ~42% (131049 per-user cap dominated) — the daily
  report is the instrument on it.

## Verify-live commands (truth beats this file)

```bash
ssh root@72.61.240.224 "cat /var/www/gorefer/DEPLOYED_SHA"
ssh root@72.61.240.224 "cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c \"
from apps.config.integration_flags import resolve_flag
print([(f, resolve_flag(f)) for f in ['ENABLE_WATI_SEND','ENABLE_ZOHO_WRITE','ENABLE_ZOHO_READ']])\""
# COORDINATION tail — by CONTENT, never by a computed offset (blank-line counts lie):
tail -n 80 COORDINATION.md   # confirm the last entry's date before trusting any state claim
```
