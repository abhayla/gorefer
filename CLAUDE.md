# CLAUDE.md — GoRefer Operating Manual

> **Read this first, before writing any code.** This is the entry point for Claude Code. It is a map + rulebook, **not** a re-spec. For depth, follow the pointers into `docs/` — the spec is authoritative, this file is not.
>
> **Owner:** Abhay Kumar Maurya / PIFS (Passive Income Financial Solutions), a Zerodha Authorised Person. **Compiled:** 2026-07-04. **Program:** Zerodha only.
>
> **Sprint state:** Sprint 1 is **shipped and live in production**; the project is in **Sprint 2** (share amplification, referrer login, follow-up engine). §5 below is Sprint 1's *build order*, kept as history — it is not the current worklist. **`CURRENT-STATE.md` is the authoritative now-state**; `ROADMAP-STATUS.md` is the per-feature ledger. **§6's "do NOT build" list is a Sprint-1-era freeze — several items have since been explicitly un-frozen by the owner; check §6's notes and `CURRENT-STATE.md` before treating anything there as forbidden.**

---

## 1. What GoRefer is

GoRefer is a **Referral Management & Referral Intelligence platform**: users manage, share, and track referral links from partner businesses through one unified system, and GoRefer records the complete referral lifecycle (create → share → click → landing → redirect → lead → account/reward) as an immutable event stream. GoRefer does **not** own any referral program — it integrates with programs run by partners. **Sprint 1 enables exactly ONE program: Zerodha** (Partner Code `ZMPHZC`), but the architecture is **provider-agnostic and extensible** to future partners (Groww, insurance, mutual funds, properties, loans) via configuration, never a rebuild. **There is NO Zerodha API.** Account-opening and reward status originate **only in Zoho CRM**, which is the authoritative source of truth for referral credit and account status; GoRefer verifies only what it observes (clicks, redirects) and never fabricates downstream status.

---

## 2. How to use this repo

**The spec is authoritative.** Read the relevant doc before coding. If docs conflict or a decision is ambiguous or marked OPEN, **STOP and ask** — do not invent a resolution and build on it. Prefer to build behind a feature flag or config so a choice can be swung later.

Document map (start at `README.md` for the index):

| Location | What it holds |
|---|---|
| `docs/foundation/01-GoRefer-Foundation-Specification.md` | Vision, scope, actors, lifecycle state model (S0–S7), REQ/BR/NFR/AC. |
| `docs/foundation/03-GoRefer-Constitution.md` | The 16 non-negotiable engineering principles. Every PR is checked against it. |
| `docs/architecture/02-Architecture-Decisions-ADR.md` | ADR-001…ADR-024 — the locked, hard-to-reverse decisions (incl. ADR-021 central runtime, ADR-022 config cascade, ADR-023 multi-tenant boundary, **ADR-024 tech stack: Django + Django Ninja + HTMX + Tailwind + Postgres**). |
| `docs/architecture/04-System-Architecture.md` | Orchestrator model, sequence flows. |
| `docs/database/05-Database-Design.md` | Referral identity, journeys, events, dates. |
| `docs/api/06-API-Specification.md` | `GET /r/{client_id}`, `GET /open`, `POST /api/leads`, `POST /api/share`. |
| `docs/ui-ux/07-UI-UX-Specification.md` | Landing page, disclosure rendering. |
| `docs/integrations/08-Zoho-WATI-Integration.md` | Zoho sync + WATI delivery-status contract (adapters implement this). |
| `docs/workflow/11-Referral-Workflow-and-Edge-Cases.md` | End-to-end workflow. |
| `docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md` | **Authoritative edge-case decisions** (16 gaps, locked → ADR-015…020). |
| `implementation/10-Claude-Code-Implementation-Guide.md` | **The build guide**: tech direction, standards, tests, git, DoD, build order. |
| `docs/deploy/DEPLOY-TARGET.md` | **AUTHORITATIVE deploy target** — GoRefer production runs on the Hostinger VPS `72.61.240.224` (Linux nginx + certbot), NOT the local box `103.118.16.189`. Read before any deploy/DNS/TLS decision; if any doc disagrees, this file wins. |
| `CURRENT-STATE.md` | **Read FIRST, every session** — the verified now-state snapshot (deployed SHA, LIVE flag values, in-flight missions). Updated in the same turn as any state change; `COORDINATION.md` stays the append-only log of record. Read COORDINATION's tail by CONTENT (`tail -n 80`, confirm the last entry's date), never by a computed line offset — blank-line-skipping counters caused the 2026-07-21 stale-state incident. When docs disagree, the live system wins. |
| `ROADMAP-STATUS.md` | Per-feature ledger across sprints — **Discussed / Implemented / Deployed** for every mission (M1…M13, B1–B4, M-WATI-1, M-FUP-1). Refreshed on milestones only; for live flag/deploy state `CURRENT-STATE.md` wins. |
| `docs/sprint2/` | Sprint-2 specs + goal contracts (share amplification, Wati referral amplification, referral UX/disclosure, independent test brief, M13 login contract). |
| `COORDINATION.md` | **DA ⇆ Engineer coordination log** — the async channel between the Design Authority (Cowork planning session) and the Engineer (Claude Code). Read it before each mission; append a STATUS entry when you open a PR; log any surfaced inconsistency as a QUESTION and pause rather than guess. |
| `review/` | LLM review pack (`09`) + review bundle. |
| `_source-archive/` | Historical source-of-truth captures (context only). |

When docs 11 and 12 both speak to an edge case, **doc 12 (resolved gaps) wins**.

---

## 2b. Development commands

Python 3.11+ in `.venv`; **PostgreSQL is the only engine** (settings fail-fast on anything else — no SQLite path exists). Env comes from the gitignored `.env` (template: `.env.example`); DB setup details are in `README.md` §"Running locally".

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_program        # idempotent: tenant + central config + partner + program
python manage.py seed_demo           # optional demo journeys/events (conversions go via the Zoho ingest path)
python manage.py bootstrap_admin     # from ADMIN_EMAIL + ADMIN_PASSWORD_HASH env (idempotent)
python manage.py runserver

# Tests — need Postgres; the runner creates/drops TEST_DB_NAME (default gorefer_test)
python -m pytest -q                                    # serial (~6 min)
python -m pytest -q -n 4                               # parallel (~2 min); xdist gives each worker its own DB
python -m pytest tests/test_redirect.py -q             # one file
python -m pytest tests/test_redirect.py::test_name -q  # one test
# NEVER run two pytest invocations concurrently on the same TEST_DB_NAME — the
# "database already exists / is being accessed" failure is a collision, not a
# regression. Concurrent run: TEST_DB_NAME=gorefer_test_mine python -m pytest -q
# A killed run can strand the test DB — drop it or pass --create-db next time.

# Lint + static gates (same set CI runs)
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run      # schema drift fails CI

# Tailwind — compiled and COMMITTED (no CDN runtime). CI fails if app.css is stale.
npm run build:css      # rerun after ANY template/CSS change; commit static/css/app.css
npm run watch:css

# Operator / background (prod worker only when Q_ASYNC=true; default runs tasks inline)
python manage.py golive_smoke --referrer EKU497 --mobile 9876543210 [--json]   # full capture loop, honors live flags
python manage.py set_landing_mode page|direct
python manage.py recompute_rollups
python manage.py setup_schedules && python manage.py qcluster   # registers followup_sweep + followup_inbound_poll
python manage.py createcachetable    # once per deploy — DB cache backs the rate limiter
python manage.py seed_followup_cadence   # idempotent: the 3h→21h FollowupRule cadence + per-step copy
```

CI (`.github/workflows/ci.yml`, Postgres 16 service): contract-doc drift gate → Tailwind freshness → ruff → `manage.py check` → migration drift → migrate → pytest.

## 2c. Code map

- `gorefer/` — project package. `settings.py` (loads `.env` **before** importing flags; Postgres fail-fast; canonical byte-exact compliance strings `AP_DISCLOSURE_BLOCK`/`MARKET_RISK_WARNING`). `flags.py` is the **single source of every env-level feature flag**, frozen from env at import — code imports `flags` and reads attributes, never `os.environ`, for a flag. `urls.py`: home, `/open`, `/d/{slug}`, `/r/[{channel}/]{client_id}[/continue]`, `/api/` mount, flag-gated `/share/{channel}/{client_id}` (`ENABLE_SHARE_INTENT`), `/admin-panel/` + `/django-admin/`, and the `apps.accounts` login/self-serve routes (`ENABLE_CUSTOMER_LOGIN`). `context_processors.py` auto-injects the compliance block into every page.
- `api/` — Django Ninja routers, aggregated by `api/router.py` and mounted at `/api/` (click, leads, share, analytics, wati + zoho webhooks, health).
- `apps/tenants/` — Tenant/Domain registry + `TenantResolutionMiddleware`; single-schema isolation via tenant-scoped managers + composite unique constraints.
- `apps/config/` — ADR-022 config cascade: `cascade.resolve(key)` walks user → tenant-global → central → default; **compliance-locked keys resolve from central only** (lower tiers can't weaken a claim). Also integration-flag persistence and the Preferences screen backend.
  - **Flag truth is two-layered — read this before ever judging a flag's state.** `flags.py` holds the **env default**; the *effective* value of the integration flags (`ENABLE_WATI_SEND`, `ENABLE_ZOHO_WRITE`, `ENABLE_ZOHO_READ`) is whatever `apps/config/integration_flags.py:resolve_flag(key)` returns — a DB override beats env. **Prod `.env` says `false` for all three while the live overrides are ON.** Never conclude "the integration is off" from `.env` or `flags.py`; resolve it (verify-live command in `CURRENT-STATE.md`). Per-tenant behaviour keys (`followups_enabled`, `followup_quiet_start_hour`/`_end_hour`, `followup_min_gap_minutes`, `followup_referrer_nudge_on`, `followup_poll_watch_mobiles`) live only in the cascade — they are **not** in `flags.py`.
- `apps/referrals/` — core domain: `redirect_service.py` (lazy referrer/journey creation + 302), `lead_service.py` (save lead first, then redirect), `landing_mode.py`, `validators.py` (client_id format check), views, and the seed/smoke management commands.
- `apps/events/` — immutable event stream (PII excluded by design), `bots.py` (preview/bot UA filter — a bot never creates a journey), `analytics.py` + `rollups.py` (dirty-day daily/monthly recompute).
- `apps/integrations/` — the adapter boundary. `wati/` (adapter, `notify.py`, terminal-status polling, webhook, queue tasks) and `zoho/` (adapter, client, `ingest.py` — **the only code path that writes account status**, `statusmap.py`, `waxseal.py` HMAC, webhook, `read.py` enrichment). Live vs log-only adapters swap by flag, so demo mode works with everything off. **Any change here must update `Wati-GoRefer/` / `Zoho-GoRefer/` contract docs — CI-enforced (§6b).**
- `apps/otp/` — pluggable OTP delivery port (behind `ENABLE_OTP_LOGIN`); codes stored hashed + peppered, never plaintext. When the flag is OFF the DemoOtpAdapter logs instead of sending.
- `apps/accounts/` — **M13 referrer login (Sprint 2, LIVE)**, mounted at the root behind `ENABLE_CUSTOMER_LOGIN`: `/login/` (`oauth.py` Google OAuth primary, `apps/otp` WhatsApp-OTP fallback), Path-B ownership verification (`/login/verify-ownership`), `/my/referrals` self view (`selfview.py`), and the admin Verifications queue. Models: `ReferrerAccount`, `VerificationRequest`. `onfile.py` enforces that an OTP only ever goes to a channel already on file — never to a user-supplied number.
- `apps/followups/` — **M-FUP-1 WhatsApp follow-up engine (Sprint 2, LIVE)**. Models `FollowupRule` / `FollowupWindow` / `ScheduledFollowup`, all tenant-scoped. `services.py` is the gate: 24h-session-window check, opt-out, converted-suppression, IST quiet hours, and the anti-burst `compute_defer` min-gap. `tasks.py` runs the two scheduled jobs — `poll_inbound_windows` (opens windows by polling Wati `getMessages`, because the inbound webhook is chatbot-suppressed) and `fire_due_followups` (the sweep that actually sends). `api.py` is the staff-scoped CRUD router. Send copy is read **at fire time**, so re-seeding the cadence changes pending sends.
- `apps/dashboard/` — M7 admin dashboard + M9 referral profile served at `/admin-panel/`.
- `apps/common/` — `phone.py` (the one canonical phone normalization), `ratelimit.py` (DB-cache-backed so counters are shared across gunicorn workers), `netaddr.py` (trusted-proxy-hops X-Forwarded-For resolution for webhook IP allowlists).
- `tests/` — single flat pytest-django suite (`pytest.ini` → `gorefer.settings`); the three guardrail tests live in `tests/test_guardrails.py`, third-party-origin ban in `tests/test_no_third_party_origin.py`.
- `templates/` + `static/` — server-rendered pages; HTMX vendored at `static/js/htmx.min.js`, Inter self-hosted; **public pages load no third-party origin at all** (test-enforced).

---

## 3. Your role

You are the software **ENGINEER**, not the architect. Implement **exactly** what the spec says. **Never invent features, and never change the architecture.** Architectural decisions belong to the Design Authority. If you find an inconsistency, an OPEN decision, or a source conflict, **report it** (surface options + a recommendation) — do not guess and build on a silent pick. **Report via `COORDINATION.md`**: append a STATUS entry when you open a mission PR, and log any surfaced inconsistency/ambiguity there as a QUESTION (then pause on that point). The Design Authority answers there; Abhay relays between the two sessions.

---

## 4. Non-negotiable guardrails (the hard rules)

**Tech stack (LOCKED — ADR-024)**
- Build on **Django + Django Ninja + HTMX + Tailwind + PostgreSQL**, with **single-schema `tenant_id` discriminator isolation** for the ADR-023 multi-tenant boundary (NOT schema-per-tenant; resolves Q-M1-1). Server-rendered Django templates with **reusable HTMX partial components** — **NO React/SPA in Sprint 1**. **Django ORM + Django migrations** (not SQLAlchemy/Alembic). Background via `transaction.on_commit()` + a light DB-backed queue (django-q/django-rq); Celery/Redis only when scheduled workflows demand it. The `/r/{client_id}` redirect is a sync Django view (validate → 302, click write on-commit). Basis: [`review/Framework-Decision-Synthesis.md`](./review/Framework-Decision-Synthesis.md); record: ADR-024 in `docs/architecture/02` and tech direction in `implementation/10` §1.

**Referral link & redirect**
- Referral link identifier = the **RAW Zerodha `client_id` in the path**: `gorefer.in/r/{client_id}` (e.g. `gorefer.in/r/RJ4521`). **NO token, NO token→id mapping DB** (ADR-001). The `client_id` is already public (it appears in Zerodha's own `r=` links).
- Partner code `ZMPHZC` is **injected SERVER-SIDE** into the redirect and **never appears in the shared URL**. The destination is assembled server-side from the program's URL template: `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`.
- **Partner-direct link** `gorefer.in/open` → redirect to `https://signup.zerodha.com/?c=ZMPHZC` (**no `r=`**). Its journey is stored with **`referrer = NONE`, `source = partner_direct`** — never a fake/synthetic referrer (ADR-015). The Referral Explorer filters referral vs partner-direct as separate populations.

**Source of truth — Zoho only, never fabricate**
- **Zoho is the SINGLE authoritative source of truth** for referral credit + account-opening/reward status. GoRefer **never infers, overrides, or fabricates** conversion/referrer/reward data (ADR-013, ADR-016, Constitution §8).
- **Single-winner attribution**: one account = exactly one credited referrer, exactly as Zoho holds it. **No last-redirect / last-click fallback.** If Zoho shows no referrer, GoRefer credits **no one**. Referrer is credited/matched by the **Zerodha client ID** (the raw `client_id` in the link, ADR-001); conversion data carries **no mobile**. The opener→journey link is best-effort via a GoRefer journey-reference stamped on the Zoho lead (Round-2 amendment #10).
- **Off-platform conversions** (account opened with a referrer but no GoRefer click) are **ingested from Zoho** and still shown; a converted journey can exist with **zero clicks**. Referrer identity is created lazily on **first click OR first Zoho-imported conversion**.
- **NO Zerodha API, ever.** Account/reward status comes only from Zoho. **Reward AMOUNTS live only in the Zerodha Console** — GoRefer never computes or stores rewards, and there is **no PIFS-funded top-up**.
- Store the **TRUE Zoho account-opening date** as a first-class field, distinct from the sync/import date; **all conversion analytics run off the true opening date** so imports land in their real period with no fake day-1 spike (ADR-017).

**Never auto-submit Zerodha**
- Zerodha's signup/lead form is **reCAPTCHA-gated and lead-capture-only** (ends at a "thanks" screen; does not proceed into PAN/KYC). **NEVER auto-submit, headless-submit, or bot-submit it.** The ONLY compliant path is redirecting a **real human browser**; a human (Ashok) completes KYC on a call.

**Landing page (branded, config-driven)**
- The landing page is **per-partner CONFIG (not hardcoded)**, clearly **PIFS-branded**, and must **NOT resemble/clone Zerodha's page** (misrepresentation risk).
- Two buttons: **(1) "Continue to Zerodha"** → a short name/email/phone form that **saves the lead FIRST** (GoRefer + Zoho), then redirects to `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`. (Auto-filling Zerodha's own fields is an **OPEN POC, NOT a dependency** — do not block on it.) **(2) "Share referral details on WhatsApp"** → a `wa.me` deep link to the **WATI BUSINESS number `+91 70806 42020`** (NOT Ashok's personal `73888 82020`) with a referring-language pre-fill that **includes the referral id**.
- Show a small **"Referral ID: X"** echo line for self-serve visual confirmation (no separate confirm page).

**Lazy journey creation**
- Nothing is stored until the **first click**. On first click, create the referrer (if new) + journey + click event — after **format-validating the id only** (reject empty/oversized/illegal chars). **NO ownership verification** (there is no Zerodha API to check against) (ADR-008, Gap 3).

**Visitor identity (best-effort)**
- First-party cookie **`visitor_id`** set on first click (same cookie = same journey). A **JS-confirmation beacon** marks a **"confirmed human click"**. Filter **bot/preview user-agents** (WhatsApp, `facebookexternalhit`, Telegrambot, Slackbot, Twitterbot, LinkedInBot, Googlebot, prefetchers) — logged but excluded from counts; a bot preview never creates a journey or a redirect. **Unique-visitor counts are approximate and must be labelled as such.** Promote to a **mobile-keyed identity on form submit** and merge cookie-journeys sharing that mobile (lead-side only). **Conversions are keyed by the opener's Zerodha account ID, and the referrer by Zerodha client ID — NOT mobile** (Round-2 amendments #10/#11) (ADR-018, ADR-019).

**Compliance (hard gate)**
- The **SEBI/NSE AP disclosure block + market-risk warning + reward wording** are **per-partner CONFIG, AUTO-INJECTED into every page and baked into every generated asset** — they **cannot be omitted**. NSE AP reg. no. `AP2516003693`.
- The **"10% brokerage" wording lives in ONE editable config field** (`REFERRAL_INCENTIVE_CLAIM`, e.g. `"10% brokerage share + 300 reward points"`).
- Run the **`zerodha-ap-social-media-compliance` review before publishing anything public.** **Never impersonate or clone Zerodha** (ADR-014, Gap 15).

**Privacy / DPDP**
- **Consent + Privacy Policy link on the form**; **purpose limitation** (referral / account-opening only); **anonymize/purge UNCONVERTED prospect PII after 12 months**; **store the raw IP + city as PII in a separate erasable record (no hashing)** (Round-2 amendment #17; reverses earlier hash/drop); **PII kept OUT of the immutable event log** (Round-2 amendment #16); **manual erasure on request** in Sprint 1 (ADR-020).

**Auth & configuration**
- **Admin-only in Sprint 1**; bootstrap the admin from **ENV VARS** (`ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` / one-time token), idempotent, hashed — never a seeded plaintext credential. Customer login stays behind `ENABLE_CUSTOMER_LOGIN=false`.
- **Feature flags gate all disabled features.** **NEVER show "Coming Soon", placeholder menus, disabled buttons, or dead UI** (Constitution §4).
- **Configuration over code** for adding future partners — no `Zerodha*`-named file/table/route/event; model a `ReferralProgram` with a partner code + destination-URL template (Zerodha = row #1).

---

## 5. Sprint 1 build order (seven vertical slices) — HISTORY, all shipped

> Kept for the reasoning behind the layering. **All seven are deployed and live**; this is not the current worklist — see `ROADMAP-STATUS.md` and `CURRENT-STATE.md`.

Each slice left `main` deployable (see `implementation/10` §11).

1. **M1 — Repo / skeleton**: structure, config + feature-flag module, env bootstrap (incl. admin), migrations harness, CI green, README. Seed the single `ReferralProgram` (Zerodha, `ZMPHZC`).
2. **M2 — Raw `client_id` redirect + lazy journey + click event**: format-validate the id; lazy create-or-find referrer + journey on first click; fast/edge redirect `/r/{client_id}` → log Click → 302 with `c=ZMPHZC` injected server-side. **Redirect only — never submit.**
3. **M3 — Branded landing page**: PIFS-branded, mobile-first capture form; two buttons (Continue to Zerodha / Share on WhatsApp); disclosure block + risk warning present; must not resemble Zerodha.
4. **M4 — Analytics / journey**: ReferralJourney + funnel events (link created, opened, landing viewed, redirect completed); read-only aggregation, no fabricated conversions.
5. **M5 — WATI hooks**: WATI adapter behind the doc-08 contract; three notifications (Ashok / new person / referrer-if-phone-known); deduped, opt-in-aware; terminal-status verification. Behind `ENABLE_WATI_SEND=false` until templates are Meta-approved.
6. **M6 — Zoho lead + status sync**: Zoho adapter; create Lead on submit (save lead FIRST); resolve referrer from `client_id`; read account/reward status back. Behind `ENABLE_ZOHO_WRITE=false`. **Status only from Zoho.**
7. **M7 — Admin dashboard / referral explorer**: search customers, view leads + statuses, funnel analytics, top-referrer view. Renders in demo mode with seeded data.

M1–M4 need no external system (work offline in demo mode); M5/M6 integrate behind flags in parallel with template approval; M7 makes the slice observable.

---

## 6. Explicitly NOT built (do NOT build)

The architecture supports these, but **do not implement** them — they stay off behind feature flags, never shown as dead UI. **Two former entries have been UN-FROZEN by the owner and are now live; they are recorded here so a future session doesn't try to rip them out as out-of-scope:**

- ~~**Customer login / "My Referrals" self-service dashboard**~~ — **UN-FROZEN and LIVE** (M13, 2026-07-21). `ENABLE_CUSTOMER_LOGIN` + `ENABLE_OTP_LOGIN` are **ON in prod**. Code in `apps/accounts/`; contract `docs/sprint2/S2-05-M13-Referrer-Login-Goal-Contract.md`.
- ~~**WATI stale-lead auto-nudge (REQ-F01)**~~ — **UN-FROZEN and LIVE** (M-FUP-1, 2026-07-24, owner-authorized Sprint-2 mission + prod deploy). Code in `apps/followups/`; `followups_enabled=True` for PIFS. Still scoped to the **24h WhatsApp session window** (session messages, not marketing templates) with quiet hours + anti-burst min-gap; **Zoho remains the owner of lead status** — the nudge engine never writes or infers it.
- **Reward computation / calculations / payment integrations** (rewards live only in Zerodha Console).
- **Multi-partner UI** (architecture is provider-agnostic; UI exposes only Zerodha).
- **Public self-service registration**, **mobile app**, **poster/PDF asset generator** (the dead `ENABLE_ASSET_GENERATOR` flag was removed in Phase 0 — doc 16 D-5; add a flag back when the feature is actually built), **multi-language**.

---

## 6b. Integration contract docs — change code and doc TOGETHER (CI-enforced)

GoRefer's side of each vendor boundary is documented next to the code, in a folder whose contents a GoRefer code change can invalidate:

| If you change… | You must also update… |
|---|---|
| `apps/integrations/wati/**` | `Wati-GoRefer/**` — chiefly `Wati-Integration-Contract.md` (send shape, terminal-status rule, allowlist gate, reconcile matching) and `Wati-GoRefer-Templates.md` (role→template map) |
| `apps/integrations/zoho/**` | `Zoho-GoRefer/**` — chiefly `Zoho-Integration-Contract.md` (webhook + HMAC seal, status→stage map, upsert, flag gating) |

**This is enforced in CI** by `scripts/check_contract_docs.py` (a diff against the merge base). Adapter code changing with no matching doc change **fails the build**, with a message naming the doc to update.

**Escape hatch:** for a change that genuinely cannot affect the external contract (a typo, a pure internal refactor), put **`[skip-contract-doc]`** in the commit message. Use it deliberately — it is recorded in history and reviewable. Reaching for it routinely means the gate is telling you something true.

**Why:** a stale contract doc is worse than no doc — it sounds confident and the next person (or the next session) trusts it. The two live bugs behind the Wati reconcile matching both came from reality drifting away from what we believed. Filing rule: *vendor changed it, or it's reusable vendor know-how* → the platform folder (`Wati-Project` / `Zoho-Project`); *a GoRefer code change can invalidate it* → here, next to the code. **Adapter code itself does NOT move** — swappability comes from the adapter interface (LiveWatiAdapter / LogOnlyWatiAdapter already swap by config), not from folder location.

## 6c. WhatsApp templates — the HTML map is the SINGLE SOURCE OF TRUTH (owner rule, 2026-07-26)

The published conversation-map artifact **"PIFS WhatsApp — the conversation, card by card"**
([artifact 18a28208](https://claude.ai/code/artifact/18a28208-60ae-456d-a534-f745a87acb5d)) is the
**SSOT for every WhatsApp template and every conversation scenario.** Code, config, and the Wati
dashboard are downstream of it — if they disagree, the HTML is what we intend and the difference is
a defect to be reconciled, not a fact to be accepted.

**Mandatory ordering for ANY template change — no exceptions:**

1. **Update the HTML map FIRST** — add/edit the card with the new copy, category, variables, buttons,
   and a state tag. Nothing is submitted from an unrecorded draft.
2. **THEN submit to Meta** (via Wati) for approval.
3. **When Meta approves (or rejects), update the HTML map AGAIN** — flip the state tag, record the
   final approved name/version, and delete superseded drafts from both the map and the dashboard.

A template that exists at Meta but not on the map, or a map card whose state contradicts Meta, is a
**bug**. Reconcile in the same turn you notice it.

**Also true of scenarios, not just templates:** every conversation path (keyword, chatbot flow,
journey nudge, report, OTP) belongs on the map. "It works but isn't on the map" is not done.

**Category (UTILITY vs MARKETING) is an ENGINEERING constraint, not a copy preference.** MARKETING
templates hit Meta's per-user cap `131049` — the dominant cause of our ~43% delivery rate — cost ~7×,
and cannot be rescued by retrying. Meta re-categorizes a UTILITY submission to MARKETING **silently
and approves it**, so `ok:true` proves nothing: **always read back the `category` field after
submitting.** Before authoring or re-cutting any template, read
`docs/integrations/Meta-Template-Categorization-Policy.md` — it holds the actual two-part test, Meta's
worked examples, and the authoring checklist. Precedent: three consecutive submissions (v4/v5/v6 of
the §6.1 referrer nudge) were flipped to MARKETING because each trimmed adjectives around the
**referral link** — a cross-sell asset, and the disqualifier the policy names outright. v7 removed the
link and held UTILITY first try. Repeated mis-categorization is detectable and penalized by Meta, so
never churn resubmissions — read the policy first.

**Template names are config, and config drifts.** Never assume a configured template name exists —
resolve it and check it against the live Wati inventory. Precedent: on 2026-07-26 prod's
`otp_whatsapp_template` was `gorefer_login_otp`, a name that had **never existed** at Meta, so every
WhatsApp login OTP was rejected (HTTP 400) and silently degraded to the `manual` channel while
`ENABLE_OTP_LOGIN` read ON. The adapter's correct hardcoded default was bypassed because the bad
config value was truthy. The coverage matrix in
`docs/integrations/WhatsApp-Template-Coverage-Matrix.md` exists to make that class of drift visible.

## 6d. Message behaviour is CONFIGURATION, not code (owner rule, 2026-07-26)

> *"All such message settings should be configurable."* — owner, 2026-07-26

Anything that governs **what a message says, where a link points, or when a message is suppressed**
must be changeable through the ADR-022 config cascade (and surfaced on the Preferences screen where
an operator would reasonably look for it) — **never** a hard-coded literal requiring a deploy.

Concretely, this rule was stated while deciding four things, and each is now config-driven:
- the **partner-direct destination** for `/open` (default `https://signup.zerodha.com/?c=ZMPHZC`,
  switchable to `/api/lead/?c=…` or any other URL);
- the **crawler preview-card** title/description served to link-preview bots;
- the **converted-suppression** switch ("account already open → never nudge"), which must apply
  independently of `stop_on_reply`;
- template **names** per role/language (already cascade-resolved — keep it that way).

This is the same reasoning as `REFERRAL_INCENTIVE_CLAIM` living in one editable field: the owner
must be able to change customer-facing behaviour without an engineer. When adding a new message
surface, add its knob at the same time — a literal that "will probably never change" is exactly the
one that changes on a Saturday.

## 6e. Behavior literals must register a config key (rail E-6 — doc 16, ADR-044)

Any NEW literal that governs **what a message says, where a link points, when something is
suppressed, how long/often something runs, or what a page shows** must, in the SAME PR, either
become a cascade-resolved config key (with its old value as the default — zero behavior change)
or be explicitly justified as structural. This generalizes §6d from messages to every behavior
(doc 16 §3.2, owner-ratified 2026-07-27). The hard stops are the CI rails (`tests/
test_architecture_rails.py`, `scripts/check_architecture.py`); this section is the
authoring-time rule that keeps the rails from firing.

## 7. Definition of Done + expectations

Reference `implementation/10-Claude-Code-Implementation-Guide.md` (§3 standards, §6 tests, §7 git, §8 migrations, §9 DoD, §10 demo mode). A mission is **done** only when all hold:

- Implemented to spec (docs 01–09); **no architecture drift**; inconsistencies surfaced, not silently resolved.
- **Feature flags** correct; nothing half-built reachable in production; no "Coming Soon".
- Unit + integration tests **plus the three guardrail tests** pass; CI green:
  1. the redirect service **never** POSTs/submits to Zerodha (redirect only — never auto-submit reCAPTCHA);
  2. account-status can be set **only** from a Zoho-sourced import path, **never** fabricated by an internal write;
  3. **no** raw Zerodha URL or partner code appears in any client-facing response.
- Migrations included (forward-only, ordered); schema boots clean; demo/seed data is a separate script.
- **No secrets inline** — config/env only; `.env.example` updated. Phone normalized one canonical way (strip spaces/`+`/`()`/`-`, prefix `91`).
- **Compliance surfaces** (disclosure block, risk warning, single swappable 10% claim) present on every user-facing asset touched.
- **Demo mode still works end-to-end** with `ENABLE_WATI_SEND` / `ENABLE_ZOHO_WRITE` off (adapters log intended calls instead of sending).
- WATI send tests assert on **terminal delivery status**, not HTTP 200.
- PR opened per mission with a summary, deferrals, and any surfaced inconsistency; README/docs updated for anything an operator must run.

---

*Grounding: `docs/foundation/01`, `docs/foundation/03`, `docs/architecture/02` (ADR-001…020), `docs/workflow/12`, `implementation/10`. The spec is authoritative; when in doubt, STOP and ask — one decision at a time.*
