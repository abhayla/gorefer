# GoRefer — Independent Production-Readiness Review (FINAL)

**Reviewer:** Claude (Fable 5), independent session · **Date:** 2026-07-18
**Scope:** entire implementation vs the authoritative docs (01 spec, 03 Constitution ×16, 02 ADR-001..024+, 12 resolved gaps), architecture & code quality, the three hard guardrails, security/privacy, the 416-test suite, and go-live readiness for the Zerodha use case.
**Method:** read-only. Every application module was read (redirect/landing/lead/ingest/write/WATI/webhooks/flags/cascade/tenancy/auth/dashboard/profile/OTP/analytics/seed/smoke), a spec-requirements checklist was extracted from the docs and checked against code, and every test file was assessed for assertion quality. Nothing was changed: no code, no config, no flags, no DB writes, no sends. One attempted read-only SSH inspection of the prod VPS (to verify env hygiene) was blocked by session permissions — those items are marked **UNVERIFIED** below.

**Production state at review time** (from COORDINATION.md tail + git log): deployed SHA `8002ceb` at gorefer.in (Hostinger VPS 72.61.240.224). `ENABLE_ZOHO_READ`, `ENABLE_ZOHO_WRITE`, `ENABLE_WATI_SEND` are **all ON** (Abhay's deliberate go-live state). The WATI recipient allowlist is **closed** (`WATI_ALLOW_ALL_RECIPIENTS=false`, one test number `917972672473`) — opening it is explicitly recorded as Abhay's pending final call. The live loop is proven end-to-end on prod (real Zoho lead `475281000041592002`, WhatsApp DELIVERED).

---

## Executive summary

The build is **substantially faithful to the spec and unusually well-engineered**. The three hard guardrails genuinely hold (verified statically *and* behaviourally, not just via the tests). The 416-test suite is real — zero skipped/no-op tests, contract-focused, boundaries mocked at the right layer. The event log is PII-free, Zoho ingest is the sole conversion writer, the partner code never reaches a client-facing body, and the fail-closed patterns (WATI allowlist, webhook keys, wax-seal, admin bootstrap, refuse-to-construct-without-creds adapters) are consistently right.

It is **not ready for open public traffic yet**. The material gaps: the conversion-truth webhook's auth is effectively one static key (spoofable IP allowlist, HMAC seal dormant); there is no rate limiting or lockout anywhere; insecure `DEBUG`/`SECRET_KEY` *defaults* are protected only by unverified prod env hygiene; live WATI deliveries that aren't terminal at first read are stranded at `accepted` forever (no reconcile pass); and journey creation has a concurrency hole. Additionally the dormant OTP feature is broken against the live WATI adapter and logs plaintext OTP codes in demo mode — it must not be flipped on as-is.

---

## Findings by severity

### BLOCKER

**None for the current supervised posture** (single tenant, allowlist closed, conversions via the proven Zoho path). Three items below (H1, H2, H3) become Blockers the day the WATI allowlist opens / the link is promoted to broad public traffic, if still unfixed.

---

### HIGH

**H1 — Prod runtime hygiene UNVERIFIED, with insecure-by-default settings underneath**
`gorefer/settings.py:35-36`: `DEBUG` defaults to **true** and `SECRET_KEY` falls back to a known string; `.env.example:6` ships `DJANGO_DEBUG=true`. Separately, the project's own P5 deploy checklist (docs/deploy/DEPLOY-TARGET.md) marks `Q_ASYNC=true` + a running `qcluster` worker as REQUIRED — without the worker, the Zoho retry/backfill sweep, rollup recompute, and nonce purge **exist but never execute**, silently. None of the three could be verified from this session (SSH inspection was permission-blocked).
*Failure scenarios:* a redeploy that loses `DJANGO_DEBUG` serves full tracebacks (settings, queries, PII) on gorefer.in with no alarm; a missing qcluster means a lead stranded by a Zoho blip never reaches the CRM — the exact silent loss the retry layer was built to prevent.
*Fix:* one 5-minute check on the VPS: `DJANGO_DEBUG=false`, strong `DJANGO_SECRET_KEY`, `Q_ASYNC=true`, `systemctl`-active qcluster. Then make it structural: invert the `DEBUG` default and add a boot guard that refuses `DEBUG=false` + default `SECRET_KEY` (the settings file already has this fail-fast pattern for Postgres at settings.py:151-159).

**H2 — Conversion-truth webhook auth is effectively a single static key; IP allowlist is spoofable**
`apps/integrations/zoho/webhook.py:31-43` (and `wati/webhook.py:41-45`) take the **first** `X-Forwarded-For` entry as the caller IP. That entry is attacker-controlled (nginx `proxy_add_x_forwarded_for` *appends*), so `X-Forwarded-For: <zoho-ip>` bypasses `_ip_allowed`. With `ENABLE_ZOHO_WEBHOOK_HMAC` OFF (`gorefer/flags.py:97`, prod default), auth on `/api/zoho/status-webhook` — the **sole writer of conversions and referrer credit** — is the static `X-Zoho-Webhook-Key` alone. Note also `_ip_allowed` treats an *empty* allowlist as allow-any (`webhook.py:39-43`) with only a comment saying "dev only". The wax-seal implementation itself (`waxseal.py`) is excellent — HMAC over raw bytes + timestamp + one-time DB-arbitrated nonce, fail-closed, constant-time, exhaustively tested — but dormant (DF-2).
*Failure scenario:* anyone who ever sees the static key can fabricate `account_opened` conversions and credit arbitrary referrers; guardrail #2's code discipline is only as strong as this endpoint's auth.
*Fix:* (a) resolve client IP from `REMOTE_ADDR` (nginx is the direct peer) or the last-untrusted-hop with a trusted-proxy count — never `xff[0]`; (b) refuse allow-any-IP when `DEBUG=false`; (c) schedule the Zoho-side Deluge signer and flip the seal ON — DF-2 was originally P0, and no reward-bearing trust should rest on the webhook until it is closed.

**H3 — No rate limiting or lockout anywhere; one docstring falsely claims it**
The API spec requires login lockout + IP throttles (§2.3, §6.1), lead capture at 10/min/IP (§5.3), and a rate-limited name-reveal (R1). The only rate limiter in the repo is inside the dormant OTP app (`apps/otp/service.py:203`). `DashboardLoginView` (`apps/dashboard/views.py:31`) is a stock `LoginView` — unlimited password guesses. `POST /api/leads/` (`api/leads.py:40`) is unthrottled; with `ENABLE_ZOHO_WRITE` ON, a spam run writes junk leads straight into Zoho CRM and mints Notification rows. Every `GET /r/{id}` creates a `ClickNonce` (`redirect_service.py:165`) with **no purge job** (`setup_schedules.py` purges only Zoho webhook nonces) — unbounded table growth under crawling. Worst, `api/click.py:7` *documents* the name-reveal endpoint as "Rate-limited … at the edge of this view" — the limiter does not exist. A comment claiming an absent security control is itself a defect.
*Fix:* django-ratelimit (or nginx `limit_req`) on login, `/api/leads/`, `/api/click/*`, `/api/share/`; add a `ClickNonce` purge next to the existing sweeps; fix the click.py claim.

**H4 — Live WATI deliveries can be stranded at `accepted` forever: the promised reconcile pass does not exist**
`LiveWatiAdapter.get_message_status` honestly returns non-terminal `accepted` when Wati has no terminal row yet (`adapter.py:203-208`, correct), and `send_notification` then leaves the row at ACCEPTED with the comment "a later reconcile pass moves it terminal" (`wati/tasks.py:65-76`). **No such pass is scheduled** — `setup_schedules.py:16-25` registers rollups, Zoho backfill, and nonce purge only — and there is no WATI delivery-status webhook (the only WATI webhook is the inbound assisted-capture lead path). Since terminal status is read *immediately* after send, any delivery that takes longer than that instant stays `accepted` permanently.
*Failure scenario:* the funnel that doc-08/Gap-12 promises "starts at delivered — the ~33% WATI leak becomes visible, not hidden" silently under-reports terminal outcomes; failed sends (the very leak being hunted) are recorded as accepted.
*Fix:* schedule a bounded reconcile sweep (re-poll `get_message_status` for rows at `accepted` older than N minutes, finalize or expire), mirroring the existing Zoho backfill pattern.

**H5 — WATI is "ON" in prod but the closed allowlist means no real recipient receives anything, and the UI shows green**
`adapter.py:142-151`: with `WATI_ALLOW_ALL_RECIPIENTS=false`, every send outside `WATI_TEST_RECIPIENTS` is refused (recorded `skipped`, correct and fail-closed). COORDINATION confirms prod is in exactly this state while `ENABLE_WATI_SEND` is ON. A real prospect submits the form, the flow reports success, and their welcome + the office alert are silently blocked; the dashboard's flag-driven indicator (`dashboard/views.py:37-53` — deliberately not activity-based, per Abhay 2026-07-18) shows green throughout.
*This is a deliberate, user-owned staging state, not a bug* — but as a product matter the WhatsApp leg of "go-live" is not live, and nothing on the admin screen says so.
*Fix (recommendation, decision stays Abhay's):* make "open the allowlist" an explicit dated runbook step with a smoke test; surface allowlist state (open/closed + count) next to the WATI flag on Settings so green-but-blocked is visible; consider moving the switch into the admin UI with the same confirm-gate as the risky flags, since today it is an env-only, all-or-nothing flip.

---

### MEDIUM

**M1 — No uniqueness constraint on `Referral`: concurrent first clicks can twin a journey**
`apps/referrals/models.py:237-243` has indexes but no `UniqueConstraint(tenant, referral_identity, source)`; `_lazy_get_or_create_referral` (`redirect_service.py:77-83`) is check-then-insert and races. Partner-direct (`redirect_service.py:89-95`, `referral_identity=NULL`) needs a partial unique. Downstream `.order_by("id").first()` (`views.py:211`, `ingest.py:79`) papers over twins, splitting events/leads/conversions across them. A WhatsApp blast is precisely the concurrent-first-click shape this system serves. (`ReferralIdentity` has a proper key — only journeys can twin.)
*Fix:* partial unique constraints (Postgres supports them; the codebase already leans on that) + `IntegrityError`→refetch in the service. No concurrency test exists in the suite — add one.

**M2 — "Tenant-scoped model managers" claimed by the architecture do not exist; scoping is per-call-site discipline with real misses**
`gorefer/settings.py:15-16` (and ADR-024/Q-M1-1) claim isolation via "tenant-scoped model managers"; `TenantScopedModel` (`apps/common/models.py:46-64`) is just a nullable FK. Concrete misses already present: `confirm_click` promotes events with **no tenant filter** (`api/click.py:54-56`); nonce lookup is global (`events/nonces.py:36`); `dashboard/profile.py` scopes Event/Lead/VisitorPII queries only through pre-filtered id-lists and skips the tenant filter when `tenant is None` (`profile.py:223-227, 264-271, 313-327`); `queries._referrer_name` calls `filter(tenant=None)` (matches literally-NULL rows) where `profile._referrer_name` guards correctly — two helpers, two behaviours. Harmless with one tenant; a data-leak lattice the day sub-broker #2 onboards — which the preferences/flags code is explicitly being built toward. The suite has no request-level cross-tenant authorization test.
*Fix:* a default tenant-aware manager with an explicit escape hatch, or amend ADR-024's wording and add a lint/test for unscoped tenant-model queries; unify `_referrer_name`.

**M3 — No PII purge/erasure tooling; notification rows carry PII outside any erasure path**
ADR-020/Gap 15: anonymize/purge unconverted prospect PII after 12 months (manual erasure acceptable in Sprint 1). Today: no purge command, no sweep (only webhook nonces are purged), and no erasure command — "manual" means hand-editing django-admin. Prospect name + mobile are also copied into `Notification.template_params`/`recipient_mobile` (`wati/notify.py:139-167`), so erasing Prospect/Lead/VisitorPII leaves a PII residue in Notification rows; `Lead.zoho_last_error` can embed payload fragments too. Live PII has been accumulating since 2026-07-09 — the 12-month clock is running.
*Fix:* one `erase_prospect --mobile` command spanning Prospect+Lead+VisitorPII+Notification, plus a scheduled 12-month unconverted sweep.

**M4 — OTP is broken against the live WATI adapter and would fail 100% if ever flipped on** *(gated today: `ENABLE_OTP_LOGIN=false`)*
`apps/otp/adapters.py:60-71`: the OTP adapter passes `params={"code":…, "otp":…}` but `LiveWatiAdapter.send_template` only reads `params["template_params"]` (`adapter.py:153`) — **the OTP code is never placed in a template variable** (Wati rejects as "blank text", the same defect class fixed for notify in `1cf63f3` but never applied here). It then calls `get_message_status` without `recipient_mobile` while the live ack has no message id → always non-terminal → every live WhatsApp OTP reports FAILED and cascades. Works in demo only because the log-only adapter fakes both halves.
*Fix before any `ENABLE_OTP_LOGIN` flip:* build ordered `template_params`, pass `recipient_mobile`/`template` into status reconciliation. Also note Q-M-OTP-2 (Zoho `client_id→Mobile` recipient lookup) is still a stub returning `""` (`otp/recipient.py:57-74`).

**M5 — Plaintext OTP codes reach application logs in the supported OTP-on/WATI-off state** *(gated today)*
The OTP module's invariant is "the code is never logged" (hashed+peppered storage, `otp/hashing.py` is solid). But with `ENABLE_OTP_LOGIN=true` + `ENABLE_WATI_SEND=false` — an explicitly supported combination (`otp/channels.py:40-44`) — sends route to `LogOnlyWatiAdapter.send_template`, which logs `params=%s` (`adapter.py:62`) including `{"code": …, "otp": …}`.
*Fix:* redact params in the log-only adapter (log keys only), and/or never place the raw code in a generically-logged dict.

**M6 — WATI terminal-status reconciliation can attribute another message's status to this template**
`adapter.py:221-233`: matching takes the first `broadcastMessage` row whose `templateName` is empty/None even when a later row is the true match — the "skip unless nothing else matches" comment is not implemented (`break` on first plausible row). Two templates to one number close together (office alert + prospect welcome to a shared household number; retries) can each read the other's delivered/failed status.
*Fix:* exact `templateName` match only; otherwise return honest `accepted` (the adapter's own discipline elsewhere).

**M7 — Log-only adapter simulates DELIVERED — fabrication-by-simulation of the one signal never to fabricate**
`LogOnlyWatiAdapter.get_message_status` returns `STATUS_DELIVERED` unconditionally (`adapter.py:69-72`). Adapter selection is per-send via `resolve_flag`, whose fail-safe silently falls back to the env default on any resolution error (`integration_flags.py:115-132`). With flags ON via admin override rows, a transient DB hiccup at selection time degrades one send to log-only — recorded **delivered**, indistinguishable from a real delivery.
*Fix:* stamp the adapter used on the Notification and record demo terminal statuses as `simulated_delivered`, excluded from delivery metrics.

**M8 — Guardrail #2's CI test has a 3-module blast radius**
`tests/test_guardrails.py:85-107` scans only `lead_service`/`redirect_service`/`views` with brittle exact-string tokens (`status = 'account_opened'` single-quoted slips through). Grep-verified: `zoho/ingest.py` **is** today the sole writer of `conversion_status`/`credited_referrer`/`account_opened_at` — the invariant holds — but a future writer module passes CI. The repo already has the right pattern (`test_hardening.py` rglobs `apps/` for Zerodha-named symbols).
*Fix:* rglob sweep of `apps/**/*.py` excluding `zoho/ingest.py`, quoting/spacing-tolerant.

**M9 — Zoho access token is re-minted on every API call; no caching**
`zoho/client.py:106-108`: `_auth_headers` calls `access_token()` per request — every Zoho call is two HTTP round trips, and Zoho throttles refresh-token→access-token grants per time window. Profile-page enrichment (multiple reads per view) plus write traffic can hit the throttle, surfacing as spurious sync failures.
*Fix:* cache the access token in-process until near expiry (`expires_in` is returned); refresh on 401.

**M10 — KPI `conversion_rate` can exceed 100%**
`dashboard/queries.py:56,69`: `accounts / leads` mixes populations — `accounts_opened` counts by TRUE Zoho open date (correct per ADR-017) and includes off-platform zero-click/zero-lead conversions (a real, even demo-seeded case), while `leads` counts captured forms by event date. Off-platform conversions push the ratio past 100% and `conversion_frac > 1.0` breaks the KPI ring rendering.
*Fix:* clamp the fraction and label the rate, or compute accounts-with-captured-leads separately from raw Zoho account count.

**M11 — Un-adjudicated spec drifts (report → DA to accept or fix; per CLAUDE.md these should not remain silent)**
None of these has a recorded decision in COORDINATION.md:
1. **R13 `REFERRER_B_ATTEMPT`** — same-mobile lead under a different referrer within 24h must emit an event; not implemented anywhere. Second-referrer attempts are invisible.
2. **API §5.3 24h lead dedup** — implemented as *forever* dedup on (referral, prospect) (`lead_service.py:54-58`); a legitimately re-referred prospect months later can't create a fresh lead on the same journey.
3. **ADR-018/Gap 11 mobile-keyed journey merge** on form submit — not implemented (prospects share a row by mobile; journeys are never merged).
4. **API §4.4 confidence bands** (`human_high/likely/suspicious`) reduced to `is_bot`/`is_confirmed_human` booleans (`events/models.py:39-40`). Arguably better; still a contract change.
5. **API §3.1 admin JWT** → Django session auth. The right call for server-rendered pages — but §2.3/§6.1's lockout+throttles were dropped with it (see H3).
6. **Visitor cookie TTL** — spec 60 days, code 1 year (`views.py:36`).
7. **Invalid client_id** — spec branded 200, code branded 400 (`views.py:157`). Defensible; record it.
8. **Bot hits "logged but excluded"** — bot previews are app-log lines only (`redirect_service.py:150`), never `is_bot=True` Event rows; no queryable bot audit and the schema field is dead weight.
9. **DA DECISION 1 (2026-07-17): per-partner `office_number` cascade** — `preferences_service.py` still persists only flat `SUPPORT_HELPLINE_PHONE`/`WATI_BUSINESS_NUMBER` with no partner dimension; DECISION 2 (template-name config) *was* implemented. Appears unimplemented — confirm with DA.

---

### LOW

- **L1 — `queries._referrer_name(tenant=None, …)`** resolves no names (matches literal NULL tenant) in the tenant-agnostic path while `profile._referrer_name` guards correctly (`dashboard/queries.py:144` vs `profile.py:177-181`) — latent (views always pass PIFS), inconsistent helpers. Unify.
- **L2 — Nonce visitor binding skippable** when either side is empty (`events/nonces.py:41`); `confirm_click` then promotes events for a caller-supplied `visitor_id` (`api/click.py:52-56`). Needs a known UUID to abuse — low; make binding strict when the nonce has a visitor.
- **L3 — `reveal_referrer` ignores the nonce↔client_id binding** and returns `has_referrer=True` unconditionally (`api/click.py:70-87`). Harmless while the name is always `None`; a footgun when M6 fills it in.
- **L4 — `/api/share` is unauthenticated attribution** — arbitrary `client_id`+`channel` POSTs inflate `share_clicked` for any referrer, and the referral resolution picks `.first()` or silently records with `referral=None` (`api/share.py:49`). Analytics pollution only; note counts as unauthenticated.
- **L5 — `assemble_destination` strips `r=` by string surgery** (`redirect_service.py:62`) — breaks silently on a future template with different param order. Parse/rebuild the query string.
- **L6 — Middleware docstring claims per-process caching that doesn't exist** (`tenants/middleware.py:9`); resolution adds two queries to the hot redirect path (`resolve.py:21-27`). Cache or fix the docstring.
- **L7 — `statusmap` reward branch is unreachable** — no key in `ZOHO_STATUS_TO_STAGE` maps to `"rewarded"`, so `STAGE_TO_EVENT`'s reward entry is dead code contradicting the docstring (`zoho/statusmap.py:13-31`). (Reward events do fire via `reward_status` in ingest — the *map* is the inconsistency.)
- **L8 — `add_partnership` sequence collision** — `next_seq = 10*(count+2)` regresses after deactivation/soft-delete and can duplicate an active row's `disclosure_sequence`, making regulator order nondeterministic (`preferences_service.py:421-423`). Use `max(seq)+10`.
- **L9 — Disclosure template rendering can 500 the compliance page** — `_block_for` catches `KeyError/IndexError` but not `ValueError` (bad format spec like `{nse_ap_no:d}`), and its `-> str` annotation is wrong (returns a tuple) (`disclosure_service.py:53-70`).
- **L10 — People-tab status vs Conversion side-panel can disagree** — `referred_people` renders Zoho Leads snapshot status un-reconciled against the authoritative `Conversion` mirror (`profile.py:358-384`): two truths on one screen. Label the snapshot or reconcile. (No status *write* — guardrail #2 intact.)
- **L11 — Event-log PII protection is test-side only** — `PII_KEYS` (`events/models.py:23`) is asserted in tests; nothing at runtime rejects a PII key in `Event.metadata`. A `save()`-time assert would make the promise structural.
- **L12 — Opt-out test proves a duck-typed hook, not a persisted field** — `_is_opted_out` reads a `whatsapp_opt_out` attribute no migration defines (`notify.py:190-193`); prospect opt-out effectively cannot trigger today, and the suppression test sets the attr in memory.
- **L13 — Repo hygiene** — four `gorefer_*.sqlite3` files in the root of a "Postgres-only, no SQLite" (M10) codebase. Delete.
- **L14 — Dead/misleading code** — `api/click.py:86` `_ = timezone.now()`; `backfill_unsynced` filters `SYNC_FAILED AND attempts < MAX`, unsatisfiable by construction (`zoho/tasks.py:113-114,138-140`).

### NIT

- `referral_redirect` renders a landing page in `page` mode — name predates M3 (`views.py:146`).
- `test_zoho_read_live_http.py` implies live HTTP; everything is faked. Rename.
- `Q_ASYNC` env is inverted-boolean into `sync` (`settings.py:85`) — correct, easy to misread.
- `Lead.status` includes `account_opened`; a stray internal writer would be hard to spot — include `Lead.status` in the M8 guardrail sweep.
- OTP cooldown re-scans the table the rate-limit just scanned; superseded codes still burn the hourly cap — likely intended, worth documenting for operators (`otp/service.py:203-227`).

---

## The three hard guardrails — verdict

| Guardrail | Verdict | Evidence |
|---|---|---|
| (a) Redirect never POSTs/submits to Zerodha | **HOLDS — strongly verified** | `redirect_service.py` imports no HTTP client; static source scan (`test_guardrails.py:17-38`) plus a behavioural socket-kill test (`:41-60`) that fails on *any* outbound connection during landing + continue-302. Effectively evasion-proof. |
| (b) Account status only from Zoho ingest | **HOLDS today — CI check under-scoped, endpoint auth is the weak link** | Grep-verified across the whole tree: `zoho/ingest.py` is the sole assignment-writer of `conversion_status`/`credited_referrer`/`account_opened_at`; the webhook is its sole caller; the write leg and READ enrichment never touch status. But the CI test scans only 3 modules (M8), and the guardrail is only as strong as the webhook's auth (H2). |
| (c) No ZMPHZC / raw Zerodha URL client-facing | **HOLDS — well verified** | Body scans across 6 surfaces + redundant assertions in 8 other test files; template grep clean; the code appears only in settings/seed/302-Location. Headers-other-than-Location and API error bodies unscanned (low risk). |

## Test suite (416 tests) — verdict

Genuinely strong, not tautological. No skipped/xfail/conditionally-passing tests. Wax-seal attacks, upsert idempotency (incl. the silent-twin regression), terminal-status discipline, fail-closed allowlist, auth-before-schema ordering, and byte-exact disclosures are tested at the right boundaries. Weakest areas: **no concurrency tests** (all idempotency sequential — directly relevant to M1), PII *lifecycle* untested (M3), the interim static-key webhook mode much thinner than the dormant seal, no request-level cross-tenant authz test, and `test_flags.py`/`test_smoke.py` are constant-assertions (acceptable spec-locks).

## Architecture & code quality

Ports/adapters are clean (constructor-injected transports; live adapters refuse to construct without creds; log-only twins share the exact contract). The ADR-022 cascade with compliance-locked central keys is faithful; the env-floor/admin-override flag resolver is thoughtfully reasoned and conservative. Provider-agnosticism is real (no Zerodha-named symbols, CI-enforced; partner/program/rule as data). Comment density is high and mostly load-bearing — but several docstrings promise absent things (H3's rate-limit claim, L6's cache claim, M2's managers claim, H4's reconcile pass): in a codebase this disciplined, **stale claims are the main documentation risk**.

---

## Production-readiness verdict (Zerodha go-live)

Judged as two states, since the WATI allowlist decision is explicitly Abhay's pending call:

**1. Today's supervised state (allowlist closed, flags ON, Ashok-assisted): SHIP-WITH-CAVEATS.**
The core pipe — redirect, landing, capture-first lead, Zoho upsert, webhook ingest — is sound, guardrail-verified, and proven live end-to-end. Keep operating. Caveats: complete the H1 prod-env verification immediately (it is a 5-minute check standing between "fine" and "tracebacks on gorefer.in"), and treat the webhook as untrusted for anything reward-bearing until H2 closes.

**2. Open-allowlist public go-live (real WhatsApp sends, promoted link): DO-NOT-SHIP-YET.**
Not because the foundation is wrong — it's good — but because the specific failure modes of public scale are exactly the open items: unthrottled endpoints feeding a live CRM (H3), a conversion-truth webhook one leaked header value away from forgeable credit (H2), delivery statuses that strand at `accepted` so the funnel can't be trusted at volume (H4), and first-click races under blast traffic twinning journeys (M1). Close the top-fixes list, run one allowlist-open smoke (send → terminal DELIVERED → funnel row), then ship.

**Do not flip `ENABLE_OTP_LOGIN`** in its current form under any circumstances (M4/M5): live WhatsApp OTP fails structurally and demo mode logs plaintext codes.

## Top fixes, in order

1. **Verify prod runtime, then harden the defaults (H1)** — confirm `DJANGO_DEBUG=false`, strong `SECRET_KEY`, `Q_ASYNC=true` + qcluster active on 72.61.240.224; add the boot guard so this can never regress silently. Cheapest catastrophic-risk elimination available.
2. **Webhook hardening (H2)** — fix `X-Forwarded-For` handling on both webhooks, refuse empty-allowlist-in-prod, deploy the Zoho Deluge signer and flip `ENABLE_ZOHO_WEBHOOK_HMAC`. Precondition for trusting conversions/rewards.
3. **Rate limiting + nonce purge (H3)** — login lockout, `/api/leads/`, `/api/click/*`, `/api/share/`, `/r/` nonce minting; schedule a `ClickNonce` purge. Precondition for opening to public traffic.
4. **Make WATI delivery truth real (H4 + M6 + M7)** — scheduled reconcile of `accepted` rows, exact-template status matching, label simulated deliveries. Precondition for believing the funnel after the allowlist opens.
5. **`Referral` uniqueness constraints + a concurrency test (M1)** — a WhatsApp blast is the exact shape this system exists to serve.

Near-term backlog behind those: PII erasure/purge tooling with the 12-month clock running (M3), guardrail-#2 test sweep (M8), Zoho token caching (M9), KPI clamp (M10), OTP fixes before any login work (M4/M5), and DA adjudication of the nine drift items (M11).

*— End of review. This report file is the only artifact created; no code, config, flags, or data were changed. Prod-env items marked UNVERIFIED were not confirmable from this session (SSH inspection permission-blocked).*
