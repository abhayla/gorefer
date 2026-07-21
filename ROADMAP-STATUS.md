# GoRefer — Feature Roadmap & Status

> **As of 2026-07-21.** Grounded in `COORDINATION.md` (DA⇆Engineer log), `CLAUDE.md`, `review/Deferred-Features-Backlog.md`, `docs/sprint2/`. Status vocabulary: **Discussed** (spec'd only) · **Implemented** (code+tests, on a branch, not yet in prod) · **Deployed** (on `main` and running at gorefer.in). **For live flag/deploy state, `CURRENT-STATE.md` is the maintained snapshot — this file's headline is refreshed on milestones only** (the stale 07-13 headline here corroborated the 2026-07-21 wrong-state incident; hence the split).

## Deploy headline
GoRefer is **LIVE in production AND live-integrated** at **https://gorefer.in** — Hostinger VPS `72.61.240.224`, Cloudflare proxied, SSL Full-strict, live since 2026-07-09; deployed SHA `5a96000`. **The go-live flips happened ~2026-07-17/18**: `ENABLE_WATI_SEND`, `ENABLE_ZOHO_WRITE`, `ENABLE_ZOHO_READ` are **ON** (Settings/cascade overrides — the `.env` defaults still read `false`; never judge flag state from `.env`), the WATI recipient allowlist is **open** (real sends daily), and the **Zoho conversion webhook is live with the DF-2 HMAC seal ON** (signer + workflow rule active in Zoho; conversions ingesting — first live ingest `RJ4521`, 18-Jul). Only **Q-M-OTP** remains built-but-held (PR #12, awaiting the M13 customer-login gate; `ENABLE_OTP_LOGIN`/`ENABLE_CUSTOMER_LOGIN` still `false`). The **M13 login mission is in progress** (branch `mission-13-referrer-login`). Daily ops instrument: the three-sided 21:30 IST delivery+funnel report (O-6a/R-DRR, `Wati-Project/daily_report.py`).

---

## Sprint 1 — Foundation (the referral pipe)

| Feature | Status | Remarks |
|---|---|---|
| **M1 — Repo/skeleton, config + feature-flags, env-bootstrap admin** | Deployed | Django+Ninja+HTMX+Tailwind+Postgres; single-schema `tenant_id` isolation from day 1; seeded Zerodha/ZMPHZC program. |
| **M2 — `/r/{client_id}` redirect + lazy journey + click event** | Deployed | Validate→log click→302 with `c=ZMPHZC` injected server-side; `/open` partner-direct; bot-UA filtering. This is the core live pipe recording clicks. |
| **M3 — Branded landing + capture form + two buttons** | Deployed | PIFS-branded, saves lead first; Continue→Zerodha, Share→wa.me to WATI number; disclosure + consent baked in. |
| **M4 — Analytics / journey / funnel rollups** | Deployed | Read-only aggregation, daily/monthly rollups; unique/human counts labelled approximate; never fabricates conversions. |
| **M5 — WATI hooks (3 lead-time notifications)** | Deployed — **flag ON (~17-Jul)** | Live adapter, allowlist open. Terminal-status verification, dedup, opt-in aware. |
| **M6 — Zoho lead + status sync** | Deployed — **flags ON (~17-Jul); webhook + HMAC seal live (18-Jul)** | Status only ever from Zoho (never fabricated). Conversions ingesting live (first: RJ4521, 18-Jul). |
| **M7 — Admin dashboard / referral explorer / journey detail** | Deployed | Read-only KPIs from rollups, filters, conversion side-panel; PII masked. Last Sprint-1 feature mission. |
| **M8 — Hardening + independent verification endgame** | Deployed | Adversarial E2E vs the Acceptance Test Plan; removed Tailwind CDN → compiled CSS + vendored HTMX; fresh-agent UI/functional verification. |
| **M9 — Zoho-READ enrichment + Referral Profile + Variant C re-skin** | Deployed (READ flag OFF) | `/admin-panel/referrer/{client_id}/` (Clicks + Referred-People tabs); whole-app re-skinned to Variant C · Cobalt. New `ENABLE_ZOHO_READ=false`. |
| **M10 — Postgres-only hardening** | Deployed | SQLite removed entirely; Postgres sole engine dev/test/CI/prod with fail-fast guard. |

---

## Sprint 2 — Share Amplification (WhatsApp/Wati-first; broader share deferred to Sprint 3)

| Feature | Status | Remarks |
|---|---|---|
| **M11 — OG preview card + `?s=` share-channel capture** | Deployed | Forwarded links render a WhatsApp preview card; share-channel recorded then stripped before the 302; crawler ≠ click. |
| **B1 — Q-M-CHANNELPATH: `/r/{channel}/{client_id}`** | Deployed | Clean channel-prefix links (e.g. `/r/wa/RJ4521`); legacy `?s=` retained. |
| **B2 — Q-M-DISC: `/d/{slug}` disclosure page** | Deployed | Per-sub-broker, regulator-ordered (SEBI/NSE→IRDAI→RBI), config-driven, no PII. Live at `/d/pifs`. |
| **B3 — Q-M-LAND: per-tenant landing mode (page vs direct)** | Deployed | `LANDING_MODE` couples to disclosure level so you can't bypass the landing page without moving disclosure into the message. PIFS is running **Direct** mode live. |
| **B4 — Q-M-ASSIST: `/api/wati/webhook` assisted capture → Zoho lead** | Deployed (fail-closed) | "Refer directly, we'll assist" path. Fail-OPEN bug caught in review and fixed to 401-before-schema; `WATI_WEBHOOK_KEY` unset on prod = webhook closed. Zoho write still behind its flag. |
| **Q-M-PREF — Preferences / Settings screen** | Deployed | `/admin-panel/preferences` wires every control (landing mode, reward text, helpline, WA number, share channels, assisted toggle, active partnerships) to the config cascade — no code change to reconfigure. |
| **Q-M-OTP — pluggable OTP channel port (for future login)** | **Implemented — NOT deployed** | Branch `feature/q-m-otp` (PR #12), behind `ENABLE_OTP_LOGIN=false`. Secure OTP engine (hashed/peppered/salted, single-use, rate-limited, recipient from on-file channel only), WhatsApp-primary. Independently verified GO (262/262 + 20/20 tests) but **deliberately held off `main` until the Sprint-2 customer-login gate**. No login UI/identity-binding built. |

---

## Sprint 2 / 3 — Discussed / spec'd only (not built)

| Feature | Status | Remarks |
|---|---|---|
| **Q-M-MENU — referrer 3-branch WhatsApp menu** | Discussed | Share / Get-my-link / Refer-directly. Mostly a Wati-flow (dashboard) build; only the webhook hook shipped (as B4). Spec in `docs/sprint2/S2-03`. |
| **M12 — Multi-platform share launcher + 8 creatives** | Discussed | `/my/referrals/share`, per-platform `?s=` attribution. Deferred to Sprint 3 in the WhatsApp-only rescope. Spec `S2-01`. |
| **M13 — Customer/referrer login + Client-ID binding + self "My Referrals"** | Discussed | Flip `ENABLE_CUSTOMER_LOGIN`, OAuth, Zoho-verified identity binding, role-scoped self-view. **This is the gate that unblocks Q-M-OTP merge.** Spec `S2-01`/`S2-03`, ADR-035. |
| **M14 — Poster / downloadable branded image** | Discussed | IG/Story/WhatsApp-status creative, no QR. Explicitly "do not build now" (Phase 4). |
| **WM-A / WM-C — Wati nudge templates + admin nudge trigger** | Discussed | Stale-lead / re-engagement nudges. Templates staged in `wati-templates.json`; live send gated on `ENABLE_WATI_SEND` + Meta approval. |
| **Explicitly out of Sprint 1** (customer self-service, stale-lead auto-nudge REQ-F01, reward computation/payments, multi-partner UI, public self-registration, mobile app, asset generator, multi-language) | Discussed | All confirmed off behind flags; architecture supports them, intentionally unbuilt. |

---

## Deferred backlog (DF-*)

The full, tracked backlog (14 items — DF-1…DF-11, DF-OTP-SMS, DF-TESTDB-ISOLATION, Q-M-OTP-2 — each with status/priority/trigger) lives in the living tracker: **`review/Deferred-Features-Backlog.md`**. That file is the single source of truth; this roadmap intentionally does not duplicate it.

---

## Plan / what's next

1. ~~Flip the live integrations on~~ **DONE (~17/18-Jul)** — all three integration flags ON, HMAC seal live, conversions ingesting (DF-9 closed with the WRITE flip). **Remaining from this item: the delivery-rate problem itself** — ~42% delivery, dominated by the Meta per-user marketing cap (131049) — instrumented by the daily three-sided report (O-6a/R-DRR, 21:30 IST) which now also shows the click-through funnel (20-Jul: 66 referral-link deliveries → 0 prospect clicks; 21-Jul: first real prospect clicks).
2. **Open the Sprint-2 customer-login gate (M13)** — **in progress** (branch `mission-13-referrer-login`). The hard part (OTP engine, Q-M-OTP) is done; the remaining work is the login screen + Zoho-verified identity binding; then merge PR #12 and flip `ENABLE_CUSTOMER_LOGIN`/`ENABLE_OTP_LOGIN`.
3. **Sprint 3** picks up multi-platform share (M12) + creatives (M14) once WhatsApp-first is proven.
