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
> **Last updated:** 2026-07-24 (M-WATI-1 one-tap `/share` flipped LIVE, owner-authorized; deploy `f7f8656`, endpoint 302-verified) — earlier 2026-07-22 (explorer column sorting deploy). Flag values below carry the 2026-07-21 verification date.

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
- **M-FUP-1 (24h-window follow-up engine, Phase 1) — BUILDING** (2026-07-24, owner-authorized
  Sprint-2 mission; CLAUDE.md §6 deferral lifted). New `apps/followups/` (FollowupRule +
  ScheduledFollowup + FollowupWindow), `followup_sweep` 5-min schedule, `send_session_text` on the
  Wati adapter, `/api/wati/inbound` window feed, send gate, Ninja CRUD. **Gated by cascade
  `followups_enabled` (default OFF) — nothing live, nothing schedulable until an operator runs
  `setup_schedules` AND flips the flag.** Branch `feat/followup-engine-phase1`; PR opens DRAFT for DA
  review. Rollout: flag-off → live-test on 7972672473 / 7767009136 → owner copy sign-off → enable.
  Tenant-scoped only (doc-13 §5, NO PartnerGroup). See COORDINATION 2026-07-24 STATUS for the three
  flagged points (DRF→Ninja, session-endpoint CONFIRM-ON-LIVE-TEST, window-state as its own row).
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
