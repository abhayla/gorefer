# GoRefer External Review — Consolidated Matrix v1

**Sources:** Gemini, Grok, Claude | **Status:** ✅ WALK COMPLETE — all items walked & APPROVED by Abhay 2026-07-06 (see Final Approval Log at end) | **Owner:** Abhay/PIFS

---

## Executive summary

Three near-non-overlapping lenses: Gemini = schema/data-model review (~16 points, mostly CONFIRMING locked decisions — independently re-derived event-sourcing, lazy creation, Zoho-as-truth, true-open-date, DPDP minimization). Grok = product/growth critique (~11 strategic findings + Zoho-worker/idempotency design). Claude = engineering/security audit (15 findings P0–P2). ~38 distinct suggestions after dedup. Recurring cross-model themes: sync "fabrication by omission" if the Zoho worker stalls (Claude+Grok); WATI ~33% delivery leak as top business risk (Grok+Claude); explicit source-labelling of imported status (Gemini+Claude). Highest-value NEW find: Claude's P0 unauthenticated PII-enumeration leak on GET /api/landing/{client_id}. No review challenged ADR-001 raw client_id, Zoho-as-source-of-truth, or no-Zerodha-API. Three suggestions CONFLICT with locked decisions: Sprint-1 referrer feedback (Gap 5), A/B-ing away capture-first (guardrail), PIFS-funded incentive (Gap 4/7).

---

## A. Security & Integrity

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 1 | Unauth PII enumeration on GET /api/landing/{client_id} returns real first_name; guessable Zerodha IDs → harvest id→name map | Claude P0 | Security/Privacy | **APPROVED (Abhay) — option (d): beacon-gated name** | Keep short link + personalization. Landing returns GENERIC (no name) on initial load; referrer name is revealed ONLY after the JS human-confirmation beacon completes and only to a request carrying a valid, fresh server-issued nonce; add rate-limiting + bot filtering. Enumeration made economically impractical (not cryptographically impossible); residual first-name-only exposure consciously accepted. NOT the signed-param option (b) — no link bloat. |
| 2 | Mandatory HMAC + replay protection on POST /api/integrations/zoho/account-status (currently static key) | Claude P0 | Security | **DEFERRED (Abhay) → backlog DF-2** | Keep the basic webhook for now, WITHOUT the wax-seal. Interim minimum when it goes live (M6): static key + Zoho-IP allowlist. Full wax-seal (HMAC+timestamp+nonce) AND the Zoho-API pull alternative moved to Deferred-Features-Backlog.md (DF-1, DF-2). Risk accepted: endpoint stays forgeable if key leaks; only live from M6, Sprint 1 M1–M4 is demo-mode with ZOHO_WRITE off so no live exposure yet. |
| 3 | POST /api/click/confirm trusts client-supplied visitor_id+client_id (forgeable) | Claude P2 | Security | **APPROVED (Abhay) — ACCEPT Sprint 1** | Bind the human-confirmation beacon to a server-issued one-time nonce; reuses the same nonce mechanism approved in #1(d). Forged beacons without a valid, unused nonce are rejected. |
| 4 | preview=true gated by "Bearer present" not valid | Claude P2 | Security | **APPROVED (Abhay) — move preview behind admin auth** | Preview mode requires a valid logged-in GoRefer admin session (Sprint 1 admin-only login), not merely a present Authorization header. Reject any request lacking a valid admin session. |

## B. Architecture / Deployment

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 5 | Edge-scalability (04 §8) contradicts synchronous ordering (06 §4.1); runtime model still TBD | Claude P0 | Architecture | **APPROVED (Abhay) — SIMPLE CENTRAL MODEL; write as new ADR before code** | Lock one-app + one-DB (single logical brain) as the runtime model; write it as the next ADR before any code. Basis: volume ~250–1,000 clicks/day (min 250), ~6 event-rows/journey → ~0.5–3M rows/yr, ~4 inserts/sec peak — ~0.1% of a single Postgres instance's capacity; central holds even at 100×. Reliability via managed DB + backups + standby + health check (NOT edge). Edge/distributed deferred to backlog DF-3 (revisit only past ~1M clicks/month). |
| 6 | Rollups not forward-foldable (late beacon + backdated imports mutate history) | Claude P1 | Architecture/DB | **APPROVED (Abhay) — ACCEPT Sprint 1; NO provisional/final** | Mark affected day(s) dirty + recompute from raw events (no forward-only folding). CORRECTED per Abhay: do NOT use a provisional/final model. GoRefer simply MIRRORS Zoho's current mappings — whatever is mapped is already final. The ~5th–6th-of-next-month batch is a RECONCILIATION/cleanup that fills missing mappings + fixes gaps (not a provisional→final promotion). REMOVAL/un-mapping must propagate (Zerodha→Zoho→GoRefer), handled via a reversal/tombstone event so the effective view drops it + rollups recompute while the audit trail is retained. Clicks = real-time, every click. Because add/fix/remove can hit PAST periods (true open date, ADR-017), rollups must recompute on change. Removal-with-audit (reversal/tombstone: drop from current view, retain trail) CONFIRMED by Abhay. See memory: gorefer-conversion-data-finality. |
| 7 | Zoho Status Sync Worker (webhook+polled fallback, watermark, DLQ, off-platform auto-create) | Grok | Architecture/Ops | **APPROVED (Abhay) — ACCEPT-MODIFIED, build in M6** | Build the sync worker in M6: watermark (resume point) + dead-letter/problem-tray (retry failed updates without loss) + off-platform auto-create (conversion with zero clicks, ADR-016). Referrer-notification side-effects DEFERRED to Sprint 2 (depends on WATI fix). Polling fallback = the deferred Zoho API pull (DF-1); worker processes the webhook reliably for now. |
| 8 | Idempotency guard (event_id + composite fallback, zoho_sync_idempotency table, guard side-effects) | Grok | Architecture/DB | **APPROVED (Abhay) — ACCEPT M6** | Idempotency guard in M6: dedupe each Zoho update by a unique ID (Zoho event_id, or composite account+referrer+date fallback), tracked in a zoho_sync_idempotency table; check-before-apply and guard side-effects so retries/duplicate deliveries process exactly once. Distinct from the deferred wax-seal replay protection (that was security/attacker; this is normal duplicate deliveries). Pairs with #7 (no loss) → exactly-once. |
| 9 | Historical backfill script (12–24mo, true open dates) | Grok | Ops/DB | **APPROVED (Abhay) — LAZY per-referrer fetch primary; bulk deferred (DF-4)** | Abhay has mappings since 2016, so a fixed 24-month bulk is insufficient. REPLACE bulk with LAZY on-demand fetch: when a referrer/client first appears in GoRefer (first click OR first conversion), pull that referrer's full Zoho history then, dated to true open dates (fits lazy-creation ADR-016/008). Global all-time totals fill in AS referrers become active — NOT complete at launch (accepted). Full bulk backfill kept as OPTIONAL deferred one-off = backlog DF-4, only if complete all-time global dashboards are wanted at launch. |

## C. API & Attribution

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 10 | account-status payload ambiguous (client_id vs match_client_id vs credited_referrer) | Claude P1 | API | **APPROVED (Abhay) — referrer matched by ZERODHA CLIENT ID** | Lock precise, distinct field semantics in 06/08: opener = NAME + opener Zerodha ID; match/credit the REFERRER by Zerodha client ID (= the raw client_id in the referral link, ADR-001) — NOT by mobile (conversion data has no mobile). Opener→specific click-journey link: PREFER a GoRefer journey-reference stamped on the Zoho lead + echoed back on the account update (confirm feasibility at M6); else best-effort name; else record conversion under the referrer only (off-platform zero-click OK, ADR-016). See memory: gorefer-conversion-data-finality. |
| 11 | off-platform zoho_import has no uniqueness guard → phantom duplicate journeys | Claude P1 | Database | **APPROVED (Abhay) — ACCEPT Sprint 1** | Unique upsert key for conversion records = opener's ZERODHA ACCOUNT ID (one per account, always present in the data); fallback zoho_lead_id. NOT mobile (conversion data has no mobile, per #10). Upsert-on-key (update if exists, insert if new) so one account can never become two journeys. Protects the lazy per-referrer fetch (#9) against overlapping loads; pairs with #8. |
| 12 | publish explicit Zoho-status→referrals.status map; unclear authority past Redirected; rewarded unreachable | Claude P1 | Architecture/API | **APPROVED (Abhay) — ACCEPT Sprint 1** | (a) Publish explicit Zoho-status → GoRefer-stage map in 06/08; past "Redirected", Zoho is the SOLE authority — GoRefer mirrors, never advances a stage on its own. (b) "Rewarded" stage reachable ONLY if Zoho supplies a reward signal to mirror; DEFAULT = stop at account_opened, reward amounts live only in Zerodha Console (GoRefer never computes rewards). Enforces never-fabricate. |
| 13 | POST /api/leads 24h dedup on (mobile, client_id) swallows 2nd referrer | Claude P1 | API | **APPROVED (Abhay) — ACCEPT-MODIFIED Sprint 1** | Keep the 24h lead dedup (no duplicate active leads), but record a "referrer-B attempt" event so a second referrer of the same prospect is logged, not silently swallowed. Final credit still follows Zoho single-winner attribution. Gives an audit trail for referral-overlap disputes without double-counting. (Lead-side mobile is available here — this is GoRefer's own capture form, unlike the conversion side #10/#11.) |

## D. Compliance & Privacy

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 14 | Compliance gate (ADR-014) declared pipeline-enforced but nothing enforces it | Claude P2 | Compliance | **APPROVED (Abhay) — ACCEPT-MODIFIED** | Make it genuinely enforced: (1) disclosure/risk block auto-injection baked into the render/asset path so nothing can render without it (enforced by construction); (2) add a HARD blocking pre-publish gate — publish/generate refuses unless the compliance review is marked done. Wire now (small in Sprint 1: admin-only, asset generator off) so "enforced" is literally true when public surfaces grow. |
| 15 | Landing shows Ashok personal 73888 82020 vs Gap 13 WATI business 70806 42020 | Claude P2 | Compliance/Ops | **APPROVED (Abhay) — number is CONFIG via 3-tier hierarchy (not hardcoded)** | "Which number to use" is a CONFIG value resolved through the cascade (row A1): CENTRAL default = WATI business 70806 42020; overridable at GLOBAL(admin) and (later) USER level. Remove Ashok's personal 73888 82020 as any hardcoded value from customer-facing surfaces. Confirms Gap 13. |
| 16 | events immutability vs DPDP anonymization collide on metadata JSONB | Claude P2 | Privacy/DB | **APPROVED (Abhay) — ACCEPT Sprint 1** | Keep PII OUT of the immutable event log: personal data (name/phone/email) lives in a separate, erasable person record; events reference the person by ID only. A CI/code rule blocks any PII from being written into event metadata. Satisfies BOTH immutability (honest history) and DPDP erasure (anonymize the person record without touching the log). |
| 17 | hashed IP not real privacy (IPv4 brute-forces) | Claude P2 | Privacy | **APPROVED (Abhay) — store RAW IP + city, keep it simple** | Abhay wants BOTH the raw IP and the city, stored plainly — no hashing (hashing IPv4 was false privacy anyway). Raw IP is treated as PII: it lives in the ERASABLE person/journey record (NOT the immutable event log, per #16), and is covered by the DPDP rules already set — 12-month purge of unconverted-prospect PII, erasure-on-request, admin-only access. REVERSES ADR-020's "derive city then hash/drop raw IP" → now "store raw IP + city as PII." |
| 18 | source label on every status change | Gemini G3 | Database | **APPROVED (Abhay) — ACCEPT (confirms locked)** | Stamp a source/origin tag on every status change (which system/event caused it + when, e.g. "Zoho sync, 2026-07-06, zoho_lead_id 12345"). Audit backbone for never-fabricate — every status must be traceable to an origin. Pairs with #6 (removal-with-audit) and #12 (explicit status map). |

## E. Ops / Observability

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 19 | Sync-freshness observability (anti fabrication-by-omission); last_successful_zoho_sync_at + staleness alert | Claude C12 + Grok GK15 | Ops | **APPROVED (Abhay) — ACCEPT Sprint 1** | Store last_successful_zoho_sync_at (+ WATI health); show a sync-health indicator on the dashboard ("Zoho synced 4 min ago ✓ / 2 days ago ⚠"); alert when staleness exceeds a threshold. Guards against silent stale data (looks-current-but-isn't). Pairs with #7 (sync worker) and #18 (source labels). |
| 20 | WATI ~33% delivery leak = top business risk; fix before journey timelines | Grok GK2 + Claude C12 | Ops/Product | ACCEPT-MODIFIED (elevate) | already locked as prerequisite (Gap 12); gate spend. |

## F. Product & Growth (Grok)

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 21 | Fragile core assumption — trackable link alone won't sustain sharing | Grok GK1 | Product | DEFER (monitor) | NEW; Sprint 1 admin-only by design; feed Sprint 2. |
| 22 | Referrer feedback loops in Sprint 1 | Grok | Product | CONFLICTS → DEFER Sprint 2 | Gap 5 = none Sprint 1; ADR-009/011; depends on WATI fix. |
| 23 | A/B capture-first vs direct redirect | Grok GK3 | Product | ACCEPT-MODIFIED (instrument) / partial CONFLICT | capture-first locked; measure friction, don't drop. |
| 24 | Pilot/measurement framework (4–6wk, 100–200 customers) | Grok GK8 | Product | ACCEPT (pre-launch) | NEW, cheap, high value. |
| 25 | Ashok human bottleneck (~15 leads/wk) | Grok GK5 | Ops/Product | DEFER Sprint 2 | NEW scaling gap. |
| 26 | Incentive-concentration; PIFS micro-incentive Plan B | Grok GK6 | Product | DEFER; Plan-B money CONFLICTS | risk valid; PIFS-funded top-up violates Gap 4/7; recognition only. |
| 27 | No referrer differentiation vs forwarding Zerodha link | Grok GK7 | Product | DEFER Sprint 2 | |
| 28 | Fraud/abuse economic model missing | Grok GK9 | Security/Product | DEFER Sprint 2 — NEW gap | bot filter != incentive abuse. |
| 29 | Future-partner expansion realism (content/compliance won't port) | Grok GK10 | Product | DEFER/acknowledge | |
| 30 | GoRefer monetization path undefined | Grok GK11 | Product | DEFER (out of scope) | |

## G. Schema Confirmations (Gemini)

| # | Suggestion | Source | Category | Disposition | Reason |
|---|---|---|---|---|---|
| 31 | 3-tier click confidence | Gemini G10 | Database | ACCEPT-MODIFIED | keep binary gate. |
| 32 | dedicated share_events table (channel) | Gemini G11 | Database | ACCEPT | implements ADR-010. |
| 33 | admin_users + admin_sessions | Gemini G14 | Security/DB | ACCEPT-MODIFIED | keep simple for single admin. |
| 34 | rollup tables via workers | Gemini G12 | Database | ACCEPT with #6 caveat | |
| 35 | Confirmations of locked design (immutability, lazy creation, native-id identity, gr_vid cookie, multi-date incl true open date, capture-first leads, mandatory consent, lead_disposition mirror, IP minimization, 12mo purge, config-driven programs) | Gemini G1–G16 | Database/Config | ACCEPT (validation, no change) | |

---

## H. Abhay-introduced decisions (during review walk)

| # | Decision | Disposition | Detail |
|---|---|---|---|
| A1 | 3-tier configuration cascade | **APPROVED (Abhay)** | All configurable values resolve through: CENTRAL (platform default) → GLOBAL (admin/PIFS instance-wide) → USER (per-user). Precedence: user → global → central (most specific wins, fall back to central). Applies to WhatsApp number (#15), disclosure/incentive text, branding, program settings, etc. Sprint 1: CENTRAL + GLOBAL(admin) tiers live; USER tier designed-in but DORMANT behind ENABLE_CUSTOMER_LOGIN (Sprint 2+). COMPLIANCE LOCK (APPROVED by Abhay): SEBI/NSE disclosure + risk warning locked at central, NOT weakenable/removable by global or user overrides (ties #14). Config over code. See memory: gorefer-config-hierarchy. |
| A2 | GoRefer as multi-tenant SaaS for other partners (APs / distributors) | **STRATEGIC — Sprint 2+; design tenant boundary NOW** | Vision: other Authorised Persons / distributors use GoRefer to manage their own referral networks (SaaS) — likely GoRefer's real business. NOT built in Sprint 1 (single-tenant = PIFS only). Cheap now-decision: bake a tenant/org_id boundary into the data model from day one (every row scoped to a tenant) so multi-tenancy is a later feature-flip, not a rebuild; the config cascade's global tier becomes per-tenant-admin. When enabled: hard cross-tenant data isolation, per-tenant compliance (each AP's own NSE AP reg + disclosures, compliance-lock per tenant), pricing/monetization (answers #30). First validation tenant already in-family = Madhu's AngelOne + MF (ARN-314013) business. Keep feature OFF in Sprint 1. See memory: gorefer-config-hierarchy. |

---

## NEW gaps not in the 16

The following are net-new findings beyond the 16 already-resolved gaps: #1 (unauth PII enumeration), #2 (Zoho webhook auth), #5 (deployment/runtime ADR), #10 (account-status payload semantics), #11 (off-platform uniqueness guard), #12 (Zoho-status→referrals.status map), #13 (leads dedup swallows 2nd referrer), #6 (non-foldable rollups), #3 (forgeable click-confirm beacon), #16 (immutability vs DPDP on metadata), #17 (hashed-IP not real privacy), #14 (unenforced compliance gate), #19 (sync-freshness observability), #8 (idempotency guard), #9 (historical backfill), #24 (pilot/measurement framework), #28 (fraud/abuse economic model), #25 (Ashok human bottleneck), #26 (incentive concentration).

---

**Advisor recommendation:** P0 blockers = #1 (PII leak), #2 (Zoho webhook auth), #5 (deployment ADR). Sections C/D/E = P1 hardening during M1–M6. Section F strategic = Sprint 2 conversations; #22 and #26(money) would reopen locked decisions. STATUS: preliminary — awaiting Abhay's approval before any doc changes.

---

## Final Approval Log — walk complete (2026-07-06)

Full item-by-item walk completed with Abhay. **All items approved.**

- **#1–#19 + A1 + A2:** individually walked and approved; each row's disposition above reflects the final decision, INCLUDING corrections made live during the walk — notably: #1 beacon-gated name (short link kept), #2 → deferred (basic webhook now; wax-seal + Zoho-API-pull to backlog), #5 simple central model, #6 NO provisional/final (mirror Zoho, removal-with-audit), #9 lazy per-referrer fetch (bulk deferred), #10 referrer matched by ZERODHA ID, #17 store raw IP + city as PII.
- **Bundle Group 1 (#31, #32, #33, #34, #35):** APPROVED as written — build detail / keep-simple / validation of locked design.
- **Bundle Group 2 (#20, #24):** APPROVED — #20 WATI delivery fix is a hard prerequisite (gates WhatsApp spend); #24 run a measured pre-launch pilot (~4–6 wks, 100–200 customers).
- **Bundle Group 3 (#21, #22, #23, #25, #26, #27, #28, #29, #30):** DEFERRED to Sprint 2 / strategic as written. Two locked-decision conflicts explicitly parked: **#22** (referrer feedback in Sprint 1 — none, per Gap 5) and **#26** (PIFS-funded cash incentive — rejected; recognition-only if ever revisited). #30 (monetization) folded into A2 (multi-tenant SaaS).

**New backlog items created during the walk** (Deferred-Features-Backlog.md): DF-1 Zoho API pull, DF-2 wax-seal webhook auth, DF-3 edge/distributed model, DF-4 full bulk backfill.
**New Abhay-introduced decisions:** A1 (3-tier config cascade central→global(admin)→user + compliance lock), A2 (multi-tenant SaaS — design tenant boundary now, build Sprint 2+; Madhu's AngelOne = tenant #2).

**NEXT:** apply all approved decisions into the formal spec docs (ADRs 02, DB 05, API 06, UI 07, integration 08, gaps 12) in one reviewed batch. No spec-doc edits made yet — the matrix + backlog + memory are the live decision log.
