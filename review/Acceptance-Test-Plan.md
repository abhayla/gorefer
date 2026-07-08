# GoRefer — Sprint 1 Acceptance Test Plan (independent-verification rubric)

> **Purpose.** The pass/fail rubric the **independent verification agent** (Phase B, a fresh agent — NOT the builder) checks GoRefer Sprint 1 against, covering **functionality AND UI**. Every item is concrete and verifiable. Produce a `review/Verification-Report.md` marking each **PASS / FAIL / N-A** with evidence (test output, commands, screenshots) and a defect list. Nothing ships to Abhay's manual test until every item is PASS (or a FAIL is explicitly waived by the DA).
>
> **Scope:** Sprint 1 = the Zerodha-only referral system, run in **demo mode** (`ENABLE_DEMO_MODE=true`, `ENABLE_WATI_SEND=false`, `ENABLE_ZOHO_WRITE=false`, `ENABLE_ADMIN_DASHBOARD=true`, `ENABLE_CUSTOMER_LOGIN=false`). No live external calls.
> **Authoritative sources:** specs `docs/01`–`docs/12`, `CLAUDE.md`, ADR-001…024, the review matrix + backlog, and the mockups in `mockups/`.

---

## 0. Setup (record exact commands + outputs)
- [ ] Fresh clone of `main`; create venv; install; copy `.env.example` → `.env` with demo values.
- [ ] `manage.py migrate` applies clean from an empty DB; `makemigrations --check` reports **no drift**.
- [ ] `seed_demo` runs; `runserver` starts; app reachable.
- [ ] Full test suite: `pytest` (or `manage.py test`) — record **N passed / M skipped / 0 failed**; `ruff` clean.
- [ ] Confirm all five flags are at their demo defaults above.

---

## A. Redirect + link (M2)  — specs 06, ADR-001/005/008/015/021
- [ ] **A1** `GET /r/{client_id}` with a valid id resolves (renders the landing per M3 — see §B; the 302 lives on the continue action).
- [ ] **A2** Raw `client_id` in the path; **no token, no mapping lookup**. Case-insensitive (`/r/rj4521` == `/r/RJ4521`).
- [ ] **A3** Format validation rejects empty / oversized / illegal-char ids gracefully (→ invalid-referral page, not a 500).
- [ ] **A4** **Lazy creation:** nothing stored until first click; first click creates referrer identity + referral + a `click` event (tenant-scoped).
- [ ] **A5** The "Continue to Zerodha" action 302s to a **server-side-assembled** `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}` — `c=ZMPHZC` injected server-side; raw URL/partner code **never** in any page body.
- [ ] **A6** `GET /open` (partner-direct) 302s to `…?c=ZMPHZC` with **no `r=`**; its referral has `referrer=NONE, source=partner_direct` (never a synthetic referrer).
- [ ] **A7** Click write is non-blocking (`transaction.on_commit`) and **idempotent** (repeat clicks don't duplicate the identity/referral).
- [ ] **A8** `gr_vid` first-party cookie set on first click.

## B. Landing + capture + two buttons (M3) — specs 07, ADR-002, decisions #1/#3/#15
- [ ] **B1** `/r/{client_id}` renders the **PIFS-branded, mobile-first landing** (200), logs `landing_viewed`. **Does NOT resemble/clone Zerodha's page.**
- [ ] **B2** Initial HTML shows a **generic greeting — no referrer name**. Name is revealed only after the beacon returns it via a **valid, fresh, single-use nonce** (rate-limited, bot-filtered; forged/expired/used/absent → 401). (In Sprint 1 the name is `null` unless a `Customer`/Zoho source exists — generic greeting is correct.)
- [ ] **B3** Capture form (name/email/mobile) with **client-side mobile format validation** (+91, 10 digits, starts 6–9; valid/error states).
- [ ] **B4** **"Continue to Zerodha"** saves the lead **FIRST** to GoRefer (`Prospect`+`Lead`+`lead_captured`) then 302s to the Zerodha URL. In demo, the Zoho write is **logged not sent**, and the request still succeeds.
- [ ] **B5** **"Share on WhatsApp"** opens a `wa.me` link to the **config-driven WATI business number `917080642020`** (NOT Ashok's personal number) with a referring-language prefill **including the referral id**; emits `share_clicked`.
- [ ] **B6** **Referral ID echo** ("Referral ID: {client_id}") visible.
- [ ] **B7** **Consent checkbox + Privacy Policy link** present.
- [ ] **B8** **Compliance block** (AP disclosure + market-risk warning + the single `REFERRAL_INCENTIVE_CLAIM`) is present on **every** landing state.

## C. Analytics / journey (M4) — decisions #6/#18/#19, ADR-004/017/018/019
- [ ] **C1** **Journey timeline** assembles a referral's events in order, each with a **source tag + timestamp**.
- [ ] **C2** **Funnel** counts (click → confirmed-human → landing_viewed → redirect_completed → lead_captured → account_opened) computed from the **immutable event stream**; **bots excluded**.
- [ ] **C3** **Unique-visitor counts are labelled "approximate"** (cookie-keyed, bot-filtered).
- [ ] **C4** **Rollups** (daily + monthly) recompute the **affected day/month on a late/backdated event** (dirty-days); verified idempotent/backdated-safe.
- [ ] **C5** Events are **append-only** (no update/delete path; never hard-deleted).
- [ ] **C6** **Sync-freshness** model/endpoint exists; shows Zoho/WATI health.

## D. WATI notifications (M5) — spec 08, Gap 12, decision #20
- [ ] **D1** Adapter behind the doc-08 contract; **`ENABLE_WATI_SEND=false` → logs the intended call**, whole flow works offline.
- [ ] **D2** **Delivery verified by TERMINAL message status, not HTTP 200** (send test asserts terminal status).
- [ ] **D3** On `lead_captured`, three notifications fire: **office/Ashok**, **prospect (warm UTILITY)**, **referrer (only if phone known, else skipped-with-reason — never guessed)**.
- [ ] **D4** **Deduped** (no double-send) and **opt-in-aware**.
- [ ] **D5** Terminal delivery status recorded; funnel can start at "delivered" (Gap 12 leak visible).
- [ ] **D6** **No stale-lead nudge** exists (REQ-F01 deferred) — assert absence.

## E. Zoho conversion / status (M6) — decisions #6/#7/#8/#9/#10/#11/#12/#18, ADR-013/016/017
- [ ] **E1** Adapter behind the doc-08 contract; **`ENABLE_ZOHO_WRITE=false` → logs intended calls**; demo conversions flow **through the webhook ingest path** (never an internal write).
- [ ] **E2** **Referrer credited by Zerodha CLIENT ID** (not mobile); **opener upsert key = Zerodha ACCOUNT ID** (fallback `zoho_lead_id`) — one account never becomes two.
- [ ] **E3** **Off-platform zero-click** conversion auto-creates a referral (`source=zoho_import`).
- [ ] **E4** **No provisional/final** — mirrors Zoho as-mapped. Explicit **Zoho-status→stage map**; `account_opened` default terminal; **reward only if Zoho signals** (no amounts computed/stored).
- [ ] **E5** **True account-opening date** stored distinct from import date; conversion analytics run off the true date.
- [ ] **E6** **Removal propagates**: removing a mapping → `conversion_removed` reversal/tombstone → dropped from counts + **rollups recompute** + audit retained.
- [ ] **E7** **Sync worker:** watermark (resume) + dead-letter (retry, no loss) + **idempotency** (exactly-once) — replaying the same update does not double-count.
- [ ] **E8** Webhook auth = static key + Zoho-IP allowlist (interim); a request with no/wrong key or wrong IP is rejected.
- [ ] **E9** **Lazy per-referrer history** fetch on first appearance (no bulk).

## F. Admin dashboard / explorer / journey (M7) — spec 07, mockups
- [ ] **F1** **Admin login** gates the dashboard/explorer/detail; unauthenticated access is redirected/denied; customer login stays off.
- [ ] **F2** **Dashboard** renders KPI cards + funnel (from rollups) + **sync-freshness indicator** + **top-referrer leaderboard** (by Zerodha client id). Unique counts labelled approximate; `account_opened` shows the Zoho-sourced demo conversion(s).
- [ ] **F3** **Referral explorer**: search + filters (source: referral_link/partner_direct/zoho_import; status) work; partner-direct + off-platform rows appear as distinct populations; rows link to journey detail.
- [ ] **F4** **Journey detail**: event timeline (source tags + timestamps) + conversion panel (status, **true open date**, **credited referrer by Zerodha id**, opener by account id; no mobile shown).
- [ ] **F5** **No "Coming Soon" / dead UI** anywhere (only flag-on features render).

## G. Config cascade + compliance lock — A1/ADR-022/ADR-014
- [ ] **G1** Values resolve **central → global(admin) → user**; a global(admin) override changes the value; user tier is dormant behind the flag.
- [ ] **G2** **Compliance content (disclosure + risk warning) is LOCKED at central** — a global/user override **cannot remove or weaken it** (test the lock).
- [ ] **G3** The WhatsApp number + incentive claim are config-driven (changing config changes the rendered value; no hardcoded literals).

## H. Multi-tenancy (single-schema tenant_id) — ADR-023/024, Q-M1-1
- [ ] **H1** Every tenant-scoped row carries `tenant_id`; **no django-tenants schema routing** active.
- [ ] **H2** Tenant isolation: a query scoped to tenant A cannot read tenant B's rows (add a 2nd tenant fixture and prove the boundary).
- [ ] **H3** Composite unique constraints include `tenant_id`.

## I. Privacy / DPDP / PII — #16/#17, ADR-020
- [ ] **I1** **No PII in the immutable event log** — name/phone/email/raw-IP never appear in `Event` rows or metadata (CI rule + spot check).
- [ ] **I2** **Raw IP + city stored on a separate erasable record** (not hashed; not in events).
- [ ] **I3** Consent captured; Privacy Policy linked; retention/erasure path exists (manual OK for Sprint 1).

## J. Guardrail tests (must be ACTIVE and green)
- [ ] **J1 (#1)** The redirect service performs **no** POST/submit and opens **no socket** to Zerodha (static + behavioural).
- [ ] **J2 (#2)** Account/conversion status can be set **only** from the Zoho ingest path, **never** by an internal write (static + behavioural).
- [ ] **J3 (#3)** **No** raw Zerodha URL or partner code (`ZMPHZC`, `signup.zerodha.com`) in any client-facing **body** (present only in the 302 `Location`).

## K. Adversarial / break-it (independent agent devises + runs)
- [ ] **K1** Bad/oversized/illegal `client_id` → graceful invalid page, no 500, no journey.
- [ ] **K2** Forged / expired / reused nonce on the name-reveal → 401, no name leaked. Attempt id-enumeration → yields no names.
- [ ] **K3** Bot/preview UAs (WhatsApp, facebookexternalhit, Googlebot, no-UA) → **no journey created, not counted as human**, still 302 harmlessly.
- [ ] **K4** Replay the same Zoho update twice → counted once (idempotency). Forged webhook (bad key/IP) → rejected.
- [ ] **K5** Missing/blank required config → safe failure (no crash, no silent wrong default); secrets never logged.
- [ ] **K6** Flags toggled on/off behave correctly (e.g. `ENABLE_ADMIN_DASHBOARD=false` hides the admin entry with no dead link).

## L. UI acceptance (render EVERY page in a real browser; screenshot mobile ~390px + desktop) — vs `mockups/` + doc-07
For each page: matches the mockup's layout/branding, mobile-first, no Zerodha resemblance, compliance block where required, no broken/dead elements, readable on a phone width.
- [ ] **L1** Landing (`/r/{id}`) — generic greeting, form, two buttons, referral-id echo, consent, disclosure. (mobile + desktop)
- [ ] **L2** Thank-you / confirmation page.
- [ ] **L3** Invalid / expired referral page.
- [ ] **L4** Admin login.
- [ ] **L5** Admin dashboard — KPIs, funnel, sync-freshness top bar, leaderboard.
- [ ] **L6** Referral explorer — filters + table + badges.
- [ ] **L7** Journey detail — timeline + conversion panel.
- [ ] **L8** Compliance disclosure + market-risk warning visible on all customer-facing pages; the single incentive claim renders from config.

## M. Cross-cutting / DoD
- [ ] **M1** CI green (all guardrail tests active as applicable); `ruff` clean; migrations clean, forward-only.
- [ ] **M2** **Provider-agnostic naming** — no `Zerodha*`-named file/table/route/model/event.
- [ ] **M3** **No secrets inline**; `.env.example` lists every flag + secret name (no values).
- [ ] **M4** Phone normalized one canonical way everywhere (`91XXXXXXXXXX`).
- [ ] **M5** `main` is deployable; demo mode works end-to-end with `WATI_SEND`/`ZOHO_WRITE` off.

---

## Verification Report format (`review/Verification-Report.md`)
For each item above: **ID · PASS/FAIL/N-A · evidence** (command + output snippet, or screenshot filename) · notes. Then: a **defect list** (each with severity + repro), a **UI screenshot index**, and a final line: **"READY FOR DA SIGN-OFF: yes/no."** The builder fixes every FAIL; the independent agent re-runs until all PASS; then the DA gives the final GO for Abhay's manual test.
