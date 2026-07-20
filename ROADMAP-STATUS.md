# GoRefer — Feature Roadmap & Status

> **As of 2026-07-13.** Grounded in `COORDINATION.md` (DA⇆Engineer log), `CLAUDE.md`, `review/Deferred-Features-Backlog.md`, `docs/sprint2/`. Status vocabulary: **Discussed** (spec'd only) · **Implemented** (code+tests, on a branch, not yet in prod) · **Deployed** (on `main` and running at gorefer.in).

## Deploy headline
GoRefer is **LIVE in production** at **https://gorefer.in** — Hostinger VPS `72.61.240.224`, Cloudflare proxied, SSL Full-strict, live since 2026-07-09. Everything in Sprint 1 + Sprint-2 Track B + the Preferences screen is deployed. Only **Q-M-OTP** is built-but-not-deployed (deliberately held). Several deployed features are **live-but-dormant behind flags** (`ENABLE_ZOHO_WRITE`, `ENABLE_ZOHO_READ`, `ENABLE_WATI_SEND`, `ENABLE_OTP_LOGIN` all `false`) pending go-live preconditions.

---

## Sprint 1 — Foundation (the referral pipe)

| Feature | Status | Remarks |
|---|---|---|
| **M1 — Repo/skeleton, config + feature-flags, env-bootstrap admin** | Deployed | Django+Ninja+HTMX+Tailwind+Postgres; single-schema `tenant_id` isolation from day 1; seeded Zerodha/ZMPHZC program. |
| **M2 — `/r/{client_id}` redirect + lazy journey + click event** | Deployed | Validate→log click→302 with `c=ZMPHZC` injected server-side; `/open` partner-direct; bot-UA filtering. This is the core live pipe recording clicks. |
| **M3 — Branded landing + capture form + two buttons** | Deployed | PIFS-branded, saves lead first; Continue→Zerodha, Share→wa.me to WATI number; disclosure + consent baked in. |
| **M4 — Analytics / journey / funnel rollups** | Deployed | Read-only aggregation, daily/monthly rollups; unique/human counts labelled approximate; never fabricates conversions. |
| **M5 — WATI hooks (3 lead-time notifications)** | Deployed (flag OFF) | Behind `ENABLE_WATI_SEND=false` → adapter logs intended calls, sends nothing live. Terminal-status verification, dedup, opt-in aware. |
| **M6 — Zoho lead + status sync** | Deployed (flag OFF) | Behind `ENABLE_ZOHO_WRITE=false`. Status only ever from Zoho (never fabricated). Conversions mirror Zoho as-mapped. |
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

1. **Flip the live integrations on** (highest leverage, no new build): resolve the two go-live preconditions — fix Wati's ~60% delivery reliability and get the Wati templates Meta-approved — then enable `ENABLE_WATI_SEND` and validate the WhatsApp E2E. Then sandbox-check and enable `ENABLE_ZOHO_READ`. `ENABLE_ZOHO_WRITE` stays off while Ashok enters leads manually (DF-9).
2. **Open the Sprint-2 customer-login gate (M13)** only after #1 is stable — login is the worst thing to ship on flaky OTP delivery. The hard part (OTP engine, Q-M-OTP) is done, so the remaining work is the login screen + Zoho-verified identity binding; then merge PR #12 and flip `ENABLE_CUSTOMER_LOGIN`/`ENABLE_OTP_LOGIN`.
3. **Sprint 3** picks up multi-platform share (M12) + creatives (M14) once WhatsApp-first is proven.
