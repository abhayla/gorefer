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
> **Last updated:** 2026-07-25 (M-FUP-1 auto-trigger LIVE via polling `f0fa385` — scheduled
> `followup_inbound_poll` opens windows + enqueues cadences autonomously, verified on 917767009136)
> — earlier 2026-07-24 (main CI RESTORED GREEN, `347947a` — PR #33, test-only fix for a
> quiet-hours wall-clock flake in `tests/test_followups.py`; no production code changed, nothing
> redeployed) — same day M-FUP-1 follow-up engine deployed + LIVE on prod, `bbc32c8`,
> `followups_enabled=True`, live session nudge DELIVERED+READ; earlier same day M-WATI-1 `/share`
> LIVE (`f7f8656`). Flag values below carry the 2026-07-21 verification date.

## Production

| Fact | Value |
|---|---|
| Deployed SHA | `f7f8656` (M-WATI-1 one-tap `/share` LIVE 2026-07-24 — `ENABLE_SHARE_INTENT=true`; deployed over `da060a5`, no migrations/deps/static). Prior `da060a5` (PRs #26+#27 — lead-history honesty: 'Lead captured (since removed)' resolution vs live Lead rows; synthetic-traffic class (GoLiveSmoke/curl) excluded from ALL counts; live-verified EKU497 2/0/2/0, DA1707 39/12/1/0) |
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
- **M-FUP-1 (24h-window follow-up engine, Phase 1) — LIVE on prod** (2026-07-24, owner-authorized
  Sprint-2 mission + prod deploy; CLAUDE.md §6 deferral lifted). PR #30 merged (`bbc32c8`), deployed
  to `/var/www/gorefer` (DEPLOYED_SHA `bbc32c8`, backup `predeploy-fup-20260724-223741.tgz`), migration
  `followups.0001` applied, `followup_sweep` registered (every 5 min → `fire_due_followups`), cadence
  seeded (**every 3h through 24h**: nudge_3h…nudge_21h), **`followups_enabled=True` for PIFS**, both
  services restarted. **Live end-to-end proof:** owner messaged the WATI business number → window
  opened → `record_inbound` enqueued the 7-step cadence → the sweep sent a session nudge →
  **DELIVERED + READ** (terminal-verified) on 917972672473. Quiet hours 23:00–06:00 IST enforced
  (night steps auto-defer to 06:00 IST). Session endpoint CONFIRMED (`/api/v1/sendSessionMessage`).
  Tenant-scoped only (doc-13 §5, NO PartnerGroup).
  **AUTO-TRIGGER now LIVE via POLLING** (2026-07-25, `f0fa385`): the Wati inbound webhook is
  chatbot-suppressed ("New Contact Message" doesn't fire when the Welcome flow auto-replies; no
  "Message Received" event exists), so windows are opened by `followup_inbound_poll` (every 5 min →
  `poll_inbound_windows`): it reads `getMessages` for a per-AP watch-list (`followup_poll_watch_mobiles`,
  set to the test numbers) + recent Prospect mobiles, and on a new inbound calls `record_inbound` →
  window opens + cadence enqueues. **Verified autonomous:** the scheduled poll opened 917767009136's
  window (from its "Hi") and enqueued the 7-step cadence with ZERO manual action; idempotent on re-run.
  The `?token=`-authed `/api/wati/inbound` webhook stays wired (harmless bonus). Full loop live:
  prospect messages business → poll (≤5 min) → window → 3h cadence → sweep sends (session, quiet-hours).
- **M-WATI-1 (one-tap `/share/{channel}/{client_id}` endpoint) is LIVE** (2026-07-24, owner "make it
  live now"): PR #28 merged (`f7f8656`); the 6 code files deployed to prod (file-copy, backup
  `.predeploy-backup-20260724-150205`), `ENABLE_SHARE_INTENT=true` in prod `.env`, both services
  restarted. Live-verified at destination: `GET /share/wa/DA1707` → **302 → wa.me** (pre-filled
  referral message), homepage 200, unsupported channel `/share/xx/` → 404 (spec-correct). No
  migrations/deps/static in this deploy. Rollback = set flag false + restart (route unregisters).

## Verify-live commands (truth beats this file)

```bash
ssh root@72.61.240.224 "cat /var/www/gorefer/DEPLOYED_SHA"
ssh root@72.61.240.224 "cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c \"
from apps.config.integration_flags import resolve_flag
print([(f, resolve_flag(f)) for f in ['ENABLE_WATI_SEND','ENABLE_ZOHO_WRITE','ENABLE_ZOHO_READ']])\""
# COORDINATION tail — by CONTENT, never by a computed offset (blank-line counts lie):
tail -n 80 COORDINATION.md   # confirm the last entry's date before trusting any state claim
```
