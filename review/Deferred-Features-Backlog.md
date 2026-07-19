# GoRefer — Deferred Features & Backlog Tracker

> **Living tracker** — the single source of truth for everything consciously deferred or pending on GoRefer. Both Abhay and Claude open/update this anytime. Roadmap of shipped features lives in `../ROADMAP-STATUS.md`.
> **Last updated:** 2026-07-14. Owner: Abhay/PIFS.
> **Changelog:** 2026-07-13 — added DF-WATI-REL (Wati ~60% delivery failure; Abhay parked it, work on others first). Later same day — un-parked; root-caused (over-reach → per-user cap); drafted Send Queue design spec (`Zoho-Project/send-queue/zoho-pifs-sendqueue-design.md`); added 16-item edge-case register (§11) with 2 pre-build risk decisions (consent, delivery target); status → In progress. **2026-07-14 — Phase 1 BUILT + PROVEN on live Zoho (dry-run, zero sends): 3 modules + 18 config rows + 6 Deluge gatekeeper functions (5 run+verified via COQL — dedup/opt-out/junk/cap/welcome-fastlane/officevisitor all proven) + 4 reusable skills. Remaining: wire live Wati send + schedule + webhook + rule conversion, all gated. See `Zoho-Project/send-queue/zoho-pifs-sendqueue-build.md` + `deluge/*.dg`.**
> **Status legend:** 🟡 Open · 🔵 In progress · ✅ Done · ⛔ Won't do. **Priority:** P1 (do at next relevant go-live) · P2 (soon / blocks a near milestone) · P3 (later, on trigger) · P4 (far / scale-driven).

## Status table (quick scan)

| ID | Item | Status | Prio | Trigger to revisit |
|---|---|---|---|---|
| DF-1 | Zoho API "pull"/polling for status (vs webhook) | 🟡 Open | P3 | Webhook proves unreliable / Zoho hardening |
| DF-2 | HMAC "wax-seal" on Zoho status webhook | ✅ Done (2026-07-16, Eng#2) | P1* | **BUILT** behind `ENABLE_ZOHO_WEBHOOK_HMAC` (default off). HMAC(payload+ts+nonce) + IP allowlist + one-time nonce; static key is not a fallback when on. **Remaining human step:** deploy the Zoho-side Deluge signer (contract in `docs/deploy/DEPLOY-TARGET.md`), then flip the flag. |
| DF-3 | Edge / distributed runtime | 🟡 Open | P4 | Sustained load ≈ 1M clicks/month (~100× today) |
| DF-4 | Full historical backfill (since 2016) | 🟡 Open | P3 | Want complete all-time global dashboards from day one |
| DF-5 | Per-partner configurable page fields/layout | 🟡 Open | P3 | Onboarding a 2nd tenant |
| DF-6 | Mobile OTP on the capture form (now format-only) | 🟡 Open | P3 | Junk/mistyped leads become a problem |
| DF-7 | Schema-per-tenant physical isolation | 🟡 Open | P3 | A regulated/enterprise tenant needs hard isolation |
| DF-8 | Physical monthly partitioning of `events` | 🟡 Open | P4 | Tens of millions of rows / vacuum degrades |
| DF-9 | Pluggable per-user "Lead Destination" adapter | 🟡 Open | P2 | 2nd tenant with a different sink. **PIFS-specific rationale SUPERSEDED 2026-07-15: `ENABLE_ZOHO_WRITE` now goes ON (Model 2 upsert-by-mobile).** The generic pluggable-sink feature stays deferred. |
| DF-10 | Runtime theming / theme-switcher | 🟡 Open | P3 | Tenants wanting their own branding |
| DF-11 | Self-click tagging on the Referral Profile | 🟡 Open | P3 | Self-referral inflation concern / after customer view ships |
| DF-PII-PURGE | Automated 12-month unconverted-PII purge job (scheduled) | 🟡 Open | P2 | Surfaced by 2026-07-16 completeness audit. Erasable structure (`VisitorPII` + `erased_at`, PII out of events) + **manual** erasure are DONE and spec-correct for Sprint 1 (ADR-020). Missing only the **scheduled** purge — today the "after 12 months" clause relies on a human. Add a django-q scheduled command. Not a spec violation now; Sprint-2 hygiene. |
| DF-OTP-SMS | Real SMS OTP provider behind the stub (Q-M-OTP-1) | 🟡 Open | P3 | Referrers without WhatsApp become common; provider chosen |
| DF-TESTDB-ISOLATION | Serialize / isolate the shared Postgres test DB | ✅ Done (2026-07-16, Eng#2) | P2 | **FIXED** via pytest-xdist: `-n 4` gives each worker its own DB (`gorefer_test_gwN`) — no shared-DB deadlock. Suite 6m21s → 2m03s. CI left serial (unchanged behaviour); README documents the parallel run + the "two concurrent invocations collide" caveat. |
| Q-M-OTP-2 | Zoho `client_id → on-file channel` READ wiring (for login OTP Path A) | 🟡 Open | P2 | When opening the M13 customer-login gate |
| DF-WATI-REL | Fix Wati's ~60% WhatsApp delivery failure | 🔵 In progress — **queue LIVE 2026-07-16** | P1 | Send Queue went **fully live 2026-07-16** (dry_run off, allow_all on). First live day: 12:00 referrer batch 12/12 sent + 12:00 contacts 122/122 sent, zero send-failures, no dry-run. **Measuring toward ≥90% terminal delivery** (P1 exit) — old baseline 48.9% (14 Jul) / 52.8% (15 Jul); quality-rating recovery is multi-day. Gates `ENABLE_WATI_SEND` flip. Design: [`Zoho-Project/send-queue/zoho-pifs-sendqueue-design.md`](../../Zoho-Project/send-queue/zoho-pifs-sendqueue-design.md); audit: [`Zoho-Project/zoho-pifs-workflow-send-map.md`](../../Zoho-Project/zoho-pifs-workflow-send-map.md). |

**Open go-live preconditions (not build items, but tracked):** (1) Fix Wati's ~60% delivery reliability; (2) Meta-approve the Wati templates (incl. `gorefer_login_otp`, currently HOLD); (3) set `WATI_WEBHOOK_KEY` on prod to run the WhatsApp assisted-capture E2E. These gate flipping `ENABLE_WATI_SEND` / `ENABLE_ZOHO_READ` and the login work.

**➡ Full ordered go-live roadmap** (all phases 1–5, tasks, states, and the dependency chain from here to "Zerodha fully functional on GoRefer"): [`Zerodha-GoRefer-GoLive-Roadmap.md`](./Zerodha-GoRefer-GoLive-Roadmap.md).

---

## Detailed entries

### DF-1 — Zoho API "pull" for status sync (polling)
- **What:** GoRefer periodically calls the Zoho API (OAuth login) to fetch account-opening/reward status, instead of relying on Zoho pushing a webhook. Removes the forgeable inbound endpoint entirely; reads straight from source of truth.
- **Why deferred (Abhay, July 2026):** keeping the existing webhook ("hook") for now; not reworking the sync mechanism yet.
- **Revisit when:** hardening the Zoho integration (M6+), or if the webhook proves unreliable / instant-vs-delayed tradeoff needs revisiting. Folds into matrix item #7 (Zoho sync worker → polling-first).

### DF-2 — Wax-seal (HMAC + timestamp + nonce replay protection) on the Zoho status webhook
- **What:** Upgrade the Zoho→GoRefer "account opened" message from a single static key to an HMAC signature over payload+timestamp+one-time-nonce, verified by GoRefer (rejects forged, stale/replayed, or reused messages). Needs a small Zoho-side (Deluge) signing function.
- **Why deferred (Abhay, July 2026):** keeping the basic webhook without the wax-seal for the time being.
- **Interim minimum while deferred:** keep the static shared key AND restrict the endpoint to Zoho's server IPs (allowlist) as cheap hygiene — not the full wax-seal, just a basic lock. (Endpoint is only live from M6; ZOHO_WRITE is off, so no live exposure yet.)
- **Revisit when:** before the Zoho status webhook goes live in production (M6), or immediately if a real referrer-reward payout depends on it. Originally a P0 (sole writer of conversions/credited_referrer; a leaked static key = fabricated conversions).

### DF-3 — Edge / distributed runtime model
- **What:** Run GoRefer across many small servers near users ("the edge") for lower redirect latency and very high throughput, instead of the single central app+DB.
- **Why deferred (Abhay, July 2026):** decided in favour of the SIMPLE CENTRAL model (one app + one DB). At current volume (~250–1,000 clicks/day) a single Postgres runs at ~0.1% capacity; edge would be over-engineering and complicate event ordering.
- **Revisit when:** sustained load approaches ~1,000,000 clicks/month, or global redirect latency becomes a measured problem. Until then, get reliability from a managed DB + backups + standby + health check.

### DF-4 — Full bulk historical backfill (all-time, since 2016)
- **What:** a one-off script to bulk-load ALL historical account-openings/mappings (back to 2016) from Zoho, dated to true open dates, so all-time GLOBAL dashboards are complete from day one.
- **Why deferred (Abhay, July 2026):** primary mechanism is now LAZY per-referrer fetch — each referrer's history loads when they first become active in GoRefer. Bulk is only needed for complete all-time GLOBAL aggregates at launch, which Abhay is fine to let fill in over time.
- **Revisit when:** you want complete all-time global dashboards from day one, or for a periodic full reconciliation sweep.

### DF-5 — Per-partner configurable page fields/layout (landing + dashboard)
- **What:** let each partner/tenant configure which fields, details, and branding appear on their landing page and admin dashboard (field-level UI config, beyond the value-level config cascade).
- **Why deferred (Abhay, July 2026):** Sprint 1 is single-tenant PIFS with a fixed field set; per-partner UI-field configurability is a later-phase (multi-tenant) capability.
- **Revisit when:** onboarding a second tenant, or when partners need distinct landing/dashboard fields.

### DF-6 — Mobile number OTP verification on the capture form
- **What:** verify the prospect's mobile via OTP (SMS/WhatsApp) on the GoRefer capture form — anti-typo, reduces junk leads.
- **Why deferred (Abhay, July 2026):** Sprint 1 does client-side FORMAT validation only (Indian +91, 10 digits). OTP adds a flow + cost + friction — later phase.
- **Revisit when:** mistyped/junk leads become a problem, or higher lead quality is needed.

### DF-7 — Schema-per-tenant (or per-tenant DB) physical isolation
- **What:** move a tenant from the single-schema `tenant_id` discriminator model to Postgres schema-per-tenant or a dedicated per-tenant database, for hard physical isolation.
- **Why deferred (Abhay/DA, July 2026 — resolves Q-M1-1):** Sprint 1+ uses single-schema tenant_id discriminator (ADR-023; simpler, better platform-wide analytics, sufficient isolation at this scale).
- **Revisit when:** a regulated tenant demands physical isolation, or compliance requires it. Migrating one tenant to its own schema/DB later is possible without a rebuild.

### DF-8 — Physical monthly partitioning of the `events` table
- **What:** Postgres declarative partitioning (by month) on the immutable `events` table for query/maintenance efficiency at scale, and cold-archival of old partitions (rollups kept forever).
- **Why deferred (DA, M4, July 2026):** at Sprint-1 volume it's unnecessary. M4 already gives the correctness that matters — append-only events + daily/monthly rollups with dirty-day recompute.
- **Revisit when:** the `events` table hits tens of millions of rows or query/vacuum times degrade.

### DF-9 — Pluggable per-user "Lead Destination" adapter (centrally configured)
- **What:** each user/tenant configures where a captured lead is written — none/manual, Zoho CRM, Google Sheet, webhook, CSV, or other — from central config (no code change). A registry of outbound "lead sink" adapters behind a common interface.
- **Why deferred (Abhay, 2026-07-07) — SUPERSEDED 2026-07-15:** the original call was that PIFS writes to NO destination (Ashok enters leads manually) so `ENABLE_ZOHO_WRITE` stays off. **Abhay reversed this on 2026-07-15:** `ENABLE_ZOHO_WRITE` goes **ON** for PIFS using **Model 2 — idempotent upsert keyed on normalized mobile** (never blind-creates), so GoRefer now stamps the journey-id onto the Zoho lead directly. Ashok's manual entries are protected by a **Zoho Mobile-dedup rule** (prod flip gated on it). See COORDINATION.md "DECISION CHANGE — ENABLE_ZOHO_WRITE goes ON, Model 2" (2026-07-15).
- **Consequence (now):** GoRefer→Zoho write is ON → journey-id is hard-stamped on the lead (exact stitching, no longer match-only). The earlier "match-based only" limitation no longer applies for PIFS.
- **Still deferred (the generic feature):** the *pluggable multi-sink* adapter (none/manual, Google Sheet, webhook, CSV, …) remains open — only the PIFS Zoho-write path is being built now. **Revisit** the generic registry when onboarding a 2nd tenant whose destination differs. Relates to DF-1, DF-5.

### DF-10 — Runtime theming / theme-switcher
- **What:** allow the UI look (colors, accent, surface) to be switched at runtime via a theme layer. Feasible because the UI is Tailwind + CSS variables — define theme tokens as CSS custom properties, swap a `data-theme` attribute; per-tenant/per-user selectable from config.
- **Why deferred (Abhay, 2026-07-07):** first ship all screens in ONE finalized visual language (Variant C · Cobalt). Theming is a later-stage capability.
- **Revisit when:** onboarding tenants who want own branding. The chosen skin is already built with CSS-variable tokens, so theming later is a config layer, not a rewrite.

### DF-11 — Self-click tagging on the Referral Profile
- **What:** on the Referral Profile Clicks tab, if a click's mobile later matches the referrer's own Zoho mobile, tag it "self-click" and exclude from conversion counts.
- **Why deferred (DA, M9, 2026-07-08):** raised in the User Referral Screen mission as later polish, not built in M9. Needs a reliable click→mobile link and the referrer's own mobile from Zoho READ.
- **Revisit when:** self-referral inflation becomes a concern, or after the customer/referrer view ships. Relates to ADR-018, M9, DF-6.

### DF-OTP-SMS — SMS OTP provider (fallback channel for referrer login)
- **What:** choose + wire a real SMS provider (MSG91 / Twilio / Gupshup / Kaleyra / …) behind the existing `SmsOtpAdapter` interface so `sms` becomes a live OTP channel, selectable per-tenant on the Preferences screen (Q-M-OTP / ADR-035).
- **Why deferred (Engineer, Q-M-OTP, 2026-07-12):** Q-M-OTP built the SMS adapter as interface + log-only stub. WhatsApp-via-Wati is the decided PRIMARY (auth template ≈ ₹0.115/msg, < half the cheapest SMS OTP), with `manual` as fallback — so no SMS provider is needed to ship the OTP layer.
- **Revisit when:** referrers without WhatsApp become common, or a provider is chosen. Surfaced as Q-M-OTP-1. Relates to ADR-035, DF-6.

### DF-TESTDB-ISOLATION — test-harness hygiene (shared Postgres test DB)
- **What:** the test suite shares one Postgres test DB with no per-worker isolation, so *concurrent* pytest invocations deadlock on `otp_challenges` (spurious failures); serial runs are 262/262 green. Fix: document "one pytest run at a time" now, and wire `--reuse-db` / isolated per-worker test DBs.
- **Why deferred (DA, 2026-07-12):** CI (`ci.yml`) already runs serial, so prod risk = nil; the real risk is a human reviewer running parallel and misreading a lock collision as a regression. Not a standalone urgent mission.
- **Revisit when:** the next branch touch or a small CI-hardening task.

### Q-M-OTP-2 — Zoho `client_id → on-file channel` READ wiring (login OTP Path A)
- **What:** wire the Zoho READ so the OTP service can resolve a referrer's on-file WhatsApp/mobile from their Zerodha `client_id` (Path A: OTP to the channel already on file). Currently `recipient._from_zoho` is a stub returning "" until wired (gated `ENABLE_ZOHO_READ`).
- **Why deferred (Q-M-OTP, 2026-07-12):** Q-M-OTP shipped the OTP engine with the resolver as a stub; live Zoho READ is a Sprint-2 login-gate dependency, not part of the engine.
- **Revisit when:** opening the M13 customer-login gate. Confirm the M9 read method; live example QPJ023 → 9335138774 exists. Relates to ADR-035, M9, DF-1.

### DF-WATI-REL — Fix Wati's ~60% WhatsApp delivery failure
- **What:** systematically diagnose and fix why roughly 60% of GoRefer/PIFS WhatsApp sends via Wati don't deliver. Known/suspected causes: Meta quality-rating throttling ("restricted for higher quality messaging"), MARKETING per-user 24h caps (error 131049), template category/approval issues, token rotation, and Zoho→Wati field-mapping bugs (the "91" recipient-collapse — one instance fixed 2026-07-12/13). Likely fixes: move transactional sends to UTILITY/AUTHENTICATION templates, clean opt-in/quality, and possibly evaluate an alternate WhatsApp path (different BSP / Meta Cloud API direct) if Wati itself is the ceiling.
- **Why deferred (Abhay, 2026-07-13):** originally parked — but **un-parked same day** after Abhay chose to take it on. Root cause diagnosed (see below); design spec drafted.
- **Root cause (found 2026-07-13):** not primarily dead numbers — it's **over-reach**. Many uncoordinated Zoho rules across Contacts/Referrers/OfficeVisitors send to the same mobile (5–7 msgs/day possible); the only frequency gate is per-record; all Zerodha templates are MARKETING → trips Meta's ~2/user/24h cap (131049) → quality-rating erosion → cascading failure. Plus opt-out leaks on the two OfficeVisitors rules and junk `1111111111` (×111).
- **Fix (drafted):** a central **WhatsApp Send Queue** gatekeeper — rules write send-intents instead of sending; one scheduled Zoho function dedups by mobile, honours opt-out, caps per-person, picks one winner by priority, sends + verifies terminal status. Phase 2 adds 24h-session-aware sending (WATI inbound webhook) for engaged users. **Full spec:** [`Zoho-Project/send-queue/zoho-pifs-sendqueue-design.md`](../../Zoho-Project/send-queue/zoho-pifs-sendqueue-design.md). Live audit + counts: [`Zoho-Project/zoho-pifs-workflow-send-map.md`](../../Zoho-Project/zoho-pifs-workflow-send-map.md). Edge-case register added (spec §11, 16 items). **All 7 decisions LOCKED 2026-07-13.** Merge Contacts+Referrers parked to a separate architecture track.
- **BUILD STATUS (2026-07-14) — Phase 1 data + engine BUILT + PROVEN on live Zoho (dry-run, zero sends):**
  - **Modules/config DONE** (verified via MCP): `WA_Send_Queue` (16 custom fields), `WA_Contact_State` (10; Mobile UNIQUE = person key), `WA_Queue_Config` (3 + **18 config rows** incl. `dry_run=true` master guard, `allow_all_recipients=false`, `test_recipients=["917972672473"]`, staggered bucket times, 30-day window). 2 modules + config-as-rows (deviation from spec §3, Abhay-approved). Status picklist named `Queue_Status`.
  - **6 Deluge functions authored + deployed**; 5 arg-less ones **RAN + verified via COQL** — every invariant proven live: dedup, mobile-normalization, junk-suppression, **opt-out suppression (the OfficeVisitors-leak fix)**, welcome cap-exemption, cross-bucket coordination, officevisitor state-upsert. **Every note → DRYRUN_WOULD_SEND, ZERO real sends.** 6th (inbound webhook handler) authored+saved. Source of truth: `Zoho-Project/deluge/*.dg`. Build script + gotchas: `Zoho-Project/send-queue/zoho-pifs-sendqueue-build.md`.
  - **4 reusable skills built:** `audit-whatsapp-sends`, `check-whatsapp-delivery-health`, `run-whatsapp-send-queue`, `manage-zoho-functions`.
  - **REMAINING (all gated behind ⛔ pause-before-live-rule-edit):** wire real Wati send into the LIVE SEND BLOCKs; schedule the buckets + triggers; wire the Wati inbound webhook; Phase-0 hygiene (flag 111 junk `1111111111` as `Incorrect_Mobile`); then convert the live Zerodha sending rules to write notes (only step touching real customer messaging — needs explicit go-ahead). Everything stays `dry_run=true` until then.
  - **Key constraints learned:** Zoho has NO API/MCP to author Deluge/rules (UI-only); the browser-tool freezes on programmatic interaction with the function editor (human pastes+runs, Engineer verifies via MCP/COQL); GLOBAL.env Zoho token is `modules.ALL` scope only — function-execute needs `ZohoCRM.functions.execute` (OAUTH_SCOPE_MISMATCH otherwise).
- **Blocks (while open):** flipping `ENABLE_WATI_SEND` (the 3 lead-time notifications + assisted-capture confirmations), the referrer login OTP-over-WhatsApp (M13 / Q-M-OTP), and any Wati nudge (WM-A/C). These stay gated until the queue proves one-per-person + terminal-status delivery **with real sends** (dry-run one-per-person already proven).
- **Revisit when:** wire the live Wati send + schedule the functions + convert the rules (with go-ahead). Relates to [[wati-setup-reference]], the ~285-msg "91"-sink incident, and the `wati-referral-send-monitor` scheduled task (which watches for regressions).
