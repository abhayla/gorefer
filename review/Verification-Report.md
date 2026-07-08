# GoRefer — Sprint 1 Independent Verification Report

> **Agent:** Independent verification (Phase B) — did NOT build GoRefer.
> **Verified against:** `review/Acceptance-Test-Plan.md` (ATP), specs `docs/01`–`docs/12`, `CLAUDE.md`, ADR-001…024, `mockups/`.
> **Current state:** Round 2 (re-verify on **PostgreSQL**) — branch `m8-phase-a-fixes` (PR #9) @ `383e81d`, 2026-07-07. Supersedes Round 1.
> **Round 1:** branch `m8-phase-a-hardening` @ `9712029`, 2026-07-06, on SQLite (kept below as the audit trail).
> **Mode:** demo (`ENABLE_DEMO_MODE=true`, `ENABLE_WATI_SEND=false`, `ENABLE_ZOHO_WRITE=false`, `ENABLE_ADMIN_DASHBOARD=true`, `ENABLE_CUSTOMER_LOGIN=false`).
> **Method:** fresh setup from an empty DB; full test suite + ruff; my own adversarial break-it tests (curl/shell) for §K; every page opened in a real Chrome browser at mobile (~390px) and desktop (1280px). COORDINATION.md builder claims treated as context and independently re-verified. **No app code modified** (only this report added; one data-only admin-password reset for the UI login).

---

# ═══ ROUND 2 — RE-VERIFICATION ON POSTGRES (PR #9) ═══

> **What changed:** the builder shipped PR #9 fixing the five Round-1 findings (DEF-1, DEF-2, DEF-3, OBS-1, A-min) and made **PostgreSQL the default DB**. This round re-runs the whole verification on Postgres and confirms each fix against the ATP.

## R2 environment / setup (fresh, on PostgreSQL)

| Step | Command | Result |
|---|---|---|
| Postgres | PostgreSQL 16 listening on 5432; `gorefer` role (`createdb`) owns `gorefer_dev` | OK |
| Fresh DB | `DROP DATABASE gorefer_dev; CREATE DATABASE gorefer_dev OWNER gorefer;` → 0 public tables | empty start confirmed |
| Engine default | `DB_ENGINE` unset → settings default = **`postgres`**; runtime `connection.vendor = postgresql`, NAME `gorefer_dev` | **DEF-2 default confirmed** |
| npm deps + CSS | `npm install` (0 vuln) · `npm run build:css` → `app.css` 34 KB | OK |
| Drift | `makemigrations --check --dry-run` | **No changes detected** |
| Migrate | `manage.py migrate` (empty Postgres) | all apps apply clean |
| Seed/admin | `seed_program` → `seed_demo` (4 referrers + partner-direct + 2 Zoho conversions + 3 rollups) → `bootstrap_admin` | OK, idempotent |
| Runserver | `runserver 127.0.0.1:8912` | reachable (HTTP 200), boots clean |
| **Suite (Postgres)** | `DB_ENGINE=postgres pytest -q` | **126 passed / 0 failed** (85 s); engine confirmed `postgresql` |
| Lint | `ruff check .` | **All checks passed** |

## R2 — the five fixes, per ATP

| Fix | ATP | Round-2 verdict | Evidence (Postgres) |
|---|---|---|---|
| **DEF-1** | §K5 | **FIXED / PASS** | Inactive `ProgramRedirectRule` → `/r/RJ4521/continue` and `/open` return **HTTP 503** branded "Temporarily unavailable" (disclosure present, **0 traceback**), not a 500. Confirmed under `DJANGO_DEBUG=false` too (503, no uncaught exception to WSGI). Views now catch `PartnerUnavailable = (ReferralProgram.DoesNotExist, ProgramRedirectRule.DoesNotExist)` → `partner_unavailable.html` (new template). `/r/{id}` landing correctly still 200s (it doesn't need the redirect rule). |
| **DEF-2** | §0 | **FIXED / PASS** | `DB_ENGINE` defaults to `postgres` (settings + `.env.example`); boots cleanly on Postgres from an empty DB; the old sqlite bare-filename bug is also fixed (settings now resolves a bare name to `BASE_DIR/<name>.sqlite3`). |
| **DEF-3** | §F5 | **FIXED / PASS** | Homepage hero now reads "Share a referral link, track the full journey, and let PIFS help your referrals open their Zerodha account — all in one place." — present tense; the "arrive in the next slices" / "coming" copy is gone (grep + live screenshot). |
| **OBS-1** | §F2 | **FIXED / PASS** | KPI `total_clicks` and funnel `clicked` now read the **same rollup column** and the view calls `refresh_and_freshness()` first. Live dashboard: **Total clicks 25 == funnel Clicked 25**, with a **"counts as of 07 Jul, 9:06 AM"** freshness note. Programmatic check: both = 18 at that snapshot, MATCH True. |
| **A-min** | §A3 | **FIXED / PASS** | Validator regex reconciled to spec `^[A-Za-z0-9]{4,16}$`. Boundary sweep: len 1/2/3 → **400**, len 4 → 200, len 16 → 200, len 17/20 → **400**. `/r/AB` renders the branded invalid page (screenshot), not a raw error. |

## R2 — full suite + adversarial + UI re-run on Postgres

- **Suite:** 126 passed / 0 failed on Postgres (Round 1 was 118 on SQLite; PR #9 added 8 tests incl. new §K5-503 / A-min / OBS-1 coverage). ruff clean.
- **§K adversarial (my own, on Postgres):** K1 illegal/oversized ids → 400/404 (no 500); K2 forged nonce→401, valid→200, beacon→202, replay→401; K3 bot UAs (WhatsApp/facebookexternalhit/Googlebot/empty) → 200 harmless, **0 identities created**; K4 webhook no-key→401, valid→applied, replay→duplicate; K5 → **now 503** (see DEF-1); K6 unchanged. All PASS.
- **Guardrails on Postgres:** J1/J2/J3 green (tests) + J3 spot-check (no `ZMPHZC`/`signup.zerodha.com` in `/`, `/r/{id}`, `/open` bodies). A5 302 `c=ZMPHZC&r=RJ4521`; A6 `c=ZMPHZC` no `r=`; A8 `gr_vid` cookie; B4 lead 201. All PASS.
- **§L UI (real browser, Postgres, mobile ~390 + desktop 1280):**
  - **L1 Landing** — PIFS-branded, generic "Someone" greeting, form, consent+privacy, Referral ID RJ4521 echo, two buttons, incentive claim, disclosure + risk warning; mobile single-column card. PASS.
  - **L3 Invalid** (`/r/AB`, now sub-min-length) — branded "This referral link isn't valid" + fallback CTA + disclosure. PASS (also visually confirms A-min).
  - **L4 Login** — PIFS-branded, "single-admin console… customer self-service login is not enabled yet". Session-expiry redirect to `login/?next=` confirms F1 gating. PASS.
  - **L5 Dashboard** — KPI (Total clicks 25) + funnel (Clicked 25) match; **"counts as of"** note; sync-freshness bar; unique APPROX; accounts FROM ZOHO; leaderboard by client id. PASS + OBS-1 visually confirmed.
  - **L6 Explorer** — filters + Referral link / **Off-platform** (GW5500 0-click account_opened) / **Partner-direct** (— NONE —) badges as distinct populations; my 4–16-char test ids appear, 17+ ones absent (A-min). PASS.
  - **L7 Journey** — source-tagged timeline + conversion panel: account_opened, **true open 10 May 2026** vs **synced 07 Jul 2026**, credited referrer RJ4521 (client id), opener PGACC1 (account id, no mobile). PASS.
  - **Homepage (DEF-3)** — present-tense copy, no "coming"; disclosure footer. PASS.
  - **L2** thank-you — still **N-A by design** (locked spec: no separate confirm page).

## R2 verdict

All five Round-1 findings are **fixed and independently re-verified on PostgreSQL**; the full suite (126) + ruff are green on Postgres; every §K adversarial probe and every §L UI surface re-checked with no regression. No new defects found. The Round-1 body below is retained unchanged as the audit trail (its DEF-1/2/3, OBS-1, A-min are now all resolved above; §L2 remains N-A by design).

**READY FOR DA SIGN-OFF: yes.**

---

# ═══ ROUND 1 — original verification (SQLite, `m8-phase-a-hardening`) — AUDIT TRAIL ═══

---

## Environment / setup evidence

| Step | Command | Result |
|---|---|---|
| npm deps | `npm install` | 74 packages, 0 vulnerabilities — OK |
| Tailwind build | `npm run build:css` | `static/css/app.css` 34 KB (compiled, purged, minified) — OK |
| Migration drift | `manage.py makemigrations --check --dry-run` | **No changes detected** (clean, both empty-DB and post-migrate) |
| Migrate | `manage.py migrate` | All apps apply clean from empty DB — OK (see setup note DF below) |
| Seed program | `manage.py seed_program` | tenant + central config + partner (ZMPHZC) + program (Zerodha) + redirect rule — OK |
| Seed demo | `manage.py seed_demo` | 4 referrers + partner-direct + 2 Zoho-sourced conversions + 3 rollup periods — OK |
| Bootstrap admin | `manage.py bootstrap_admin` (ADMIN_EMAIL + ADMIN_PASSWORD_HASH set) | admin created, idempotent — OK |
| Test suite | `pytest -q` | **118 passed, 0 failed** in 54s |
| Lint | `ruff check .` | **All checks passed** |
| Runserver | `manage.py runserver 127.0.0.1:8912` | app reachable (HTTP 200) — OK |

**Setup note (minor — SETUP-1, see defects):** `.env.example` ships `DB_ENGINE=sqlite` + `DB_NAME=gorefer`. On this Windows host, SQLite cannot open a bare extension-less relative filename (`unable to open database file`) — even a direct `sqlite3.connect('gorefer')` fails. Using an absolute path / a `*.sqlite3` filename (the setting's own built-in default) boots fine. Following `.env.example` verbatim does not boot on Windows. The README's documented order (`seed_program` before `seed_demo`) is correct; running `seed_demo` first prints a friendly `Run seed_program first.` guard (no crash).

---

## Per-ATP-item results

### 0. Setup
| ID | Verdict | Evidence |
|---|---|---|
| Fresh install / .env | **PASS*** | deps install, CSS builds; `.env` copied from `.env.example`. *SETUP-1: `DB_NAME=gorefer` sqlite default fails on Windows (workaround: absolute/`.sqlite3` path). |
| migrate clean + no drift | **PASS** | `migrate` OK from empty DB; `makemigrations --check` → No changes detected. |
| seed_demo + runserver | **PASS** | seeds OK (after `seed_program`); server reachable. |
| Full suite + ruff | **PASS** | 118 passed / 0 failed; ruff clean. |
| Flags at demo defaults | **PASS** | `flags.ENABLE_WATI_SEND=False`, `ENABLE_ZOHO_WRITE=False`, `ENABLE_DEMO_MODE=True`, `ENABLE_ADMIN_DASHBOARD=True`, `ENABLE_CUSTOMER_LOGIN=False`. |

### A. Redirect + link (M2)
| ID | Verdict | Evidence |
|---|---|---|
| A1 | **PASS** | `GET /r/RJ4521` → 200, renders landing (302 lives on `/continue`). |
| A2 | **PASS** | Raw client_id in path, no token/mapping. `/r/rj4521` == `/r/RJ4521` → both 200; validator uppercases (case-stable identity key). |
| A3 | **PASS** | `/r/AB@#$` `/r/<21 chars>` `/r/RJ4521<script>` → 400 branded invalid page (has disclosure, no traceback); no 500. **Note A-min:** validator regex is `^[A-Za-z0-9]{1,20}$` (min 1, max 20), but spec 06-API §4.1 states `{4,16}`. 1–3-char and 17–20-char ids are accepted here though the spec would reject them. Graceful in both cases; divergence noted. |
| A4 | **PASS** | Lazy: nothing stored pre-click; first click creates identity + referral + click event (tenant-scoped). 3 repeat clicks on `IDEMP99` → 1 identity, 1 referral. |
| A5 | **PASS** | `/r/RJ4521/continue` → 302 `Location: https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521`; `c=ZMPHZC` server-injected; absent from body (see J3). |
| A6 | **PASS** | `/open` → 302 `…/api/lead/?c=ZMPHZC` (no `r=`); referral row `source=partner_direct`, `referral_identity=NULL` (never synthetic). Explorer shows a `— NONE —` / **Partner-direct** row. |
| A7 | **PASS** | Click write on `transaction.on_commit` (redirect path) / synchronous only for landing render; repeat clicks idempotent (A4). |
| A8 | **PASS** | `Set-Cookie: gr_vid=…; HttpOnly; Max-Age=31536000; SameSite=Lax` on first click. |

### B. Landing + capture + two buttons (M3)
| ID | Verdict | Evidence |
|---|---|---|
| B1 | **PASS** | `/r/RJ4521` → 200; PIFS-branded (green/gold, "Passive Income Financial Solutions · Authorised Person · NSE AP · Zerodha partner"); NOT a Zerodha clone. Logs click + landing_viewed. |
| B2 | **PASS** | Initial HTML greeting = generic "**Someone** has invited you" (no referrer name). Name-reveal `/api/click/referrer/{id}?nonce=` requires valid+fresh+single-use nonce: forged→401, absent→401, valid→200 with `first_name: null` (never fabricated in Sprint 1). |
| B3 | **PASS** | Form name/email/mobile; `landing.js` validates `^[6-9]\d{9}$` with valid/error visual states, +91 prefix. |
| B4 | **PASS** | `POST /api/leads/` → 201 (`lead_id`, `status:new`, `continue_url`); lead saved FIRST; Zoho write logged-not-sent in demo; request still succeeds. |
| B5 | **PASS** | WhatsApp button = `https://wa.me/917080642020?text=…Referral ID: RJ4521` — WATI **business** number (config `wati_business_number`, NOT Ashok's personal 73888…); referring-language prefill includes referral id; click emits `POST /api/share`. |
| B6 | **PASS** | "Referral ID: RJ4521" echo line visible near buttons (screenshot). |
| B7 | **PASS** | Consent checkbox + "Privacy Policy" link present; `consent:false` → 422 "consent is required". |
| B8 | **PASS** | Disclosure block (`SEBI INZ000031633 | PIFS | NSE AP AP2516003693`) + market-risk warning + single `REFERRAL_INCENTIVE_CLAIM` present on landing AND invalid page. |

### C. Analytics / journey (M4)
| ID | Verdict | Evidence |
|---|---|---|
| C1 | **PASS** | Journey detail timeline ordered, each node source-tagged (click/beacon/form/redirect/zoho) + timestamp (screenshot L7). `test_journey_timeline_is_ordered_with_source_tags`. |
| C2 | **PASS** | Funnel (click→…→account_opened) from immutable events; bots excluded. `test_funnel_counts_from_events_account_opened_source_only`, `test_funnel_excludes_bots`. |
| C3 | **PASS** | Dashboard "Unique visitors 22 **APPROX** · bot-filtered, cookie-keyed". `test_funnel_api_labels_unique_as_approximate`. |
| C4 | **PASS** | Dirty-day rollups recompute on late/backdated events; idempotent. `test_events_mark_days_dirty_and_rollups_recompute`, `test_rollup_recompute_is_idempotent`. |
| C5 | **PASS** | Events append-only: no `.delete()`/hard-delete path in `apps/events/models.py`; corrections are new events (e.g. `conversion_removed`). |
| C6 | **PASS** | SyncHealth model + dashboard top bar "Zoho: synced N min ago ✓ · WATI: no sends yet". `test_sync_health_shows_no_sync_in_demo`, `test_sync_freshness_populated_on_success`. |

### D. WATI notifications (M5)
| ID | Verdict | Evidence |
|---|---|---|
| D1 | **PASS** | `ENABLE_WATI_SEND=false` → `LogOnlyWatiAdapter` logs intended call, simulates delivered terminal status; flow works offline. |
| D2 | **PASS** | Delivery verified by TERMINAL status (`delivered`/`read`/`failed`), not HTTP 200 (`status.py`, `tasks.py`). |
| D3 | **PASS** | On lead_captured, three notifications: office→**delivered**, prospect→**delivered**, referrer→**skipped** ("referrer phone unknown", never guessed). |
| D4 | **PASS** | Deduped via `idempotency_key = role:template:journey`; opt-in-aware (`_is_opted_out` hook, warm UTILITY first message). |
| D5 | **PASS** | Terminal delivery status recorded on Notification rows; funnel can start at delivered. |
| D6 | **PASS** | No stale-lead nudge feature exists in `apps/`/`api/` (REQ-F01 correctly deferred). |

### E. Zoho conversion / status (M6)
| ID | Verdict | Evidence |
|---|---|---|
| E1 | **PASS** | `ENABLE_ZOHO_WRITE=false` → `LogOnlyZohoAdapter` logs intended calls; demo conversions flow through `/api/zoho/status-webhook` → `ingest_conversion` (never an internal write). |
| E2 | **PASS** | Referrer credited by client id (`referrer_client_id`); opener upsert key = account id (fallback `zoho_lead_id`). `test_conversion_credits_referrer_by_client_id`. Journey panel shows "Credited referrer RJ4521 / Opener account ZACC999". |
| E3 | **PASS** | Off-platform zero-click conversion auto-creates referral `source=zoho_import`; Explorer shows GW5500 **Off-platform** row, 0 clicks, account_opened. `test_offplatform_zero_click_conversion_autocreates`. |
| E4 | **PASS** | No provisional/final; explicit `statusmap`; `account_opened` default terminal; reward only if Zoho signals; no amounts. `test_reward_only_when_zoho_signals`. |
| E5 | **PASS** | True `account_opened_at` (15 May 2026) stored distinct from `synced_at` (06 Jul 2026); analytics run off true date (journey panel L7). |
| E6 | **PASS** | Reversal webhook: active conversions 3→2, emits `conversion_removed` event, ZACC999 `is_reversed=True` (audit retained, not deleted), rollups dirtied. `test_reversal_tombstones_and_emits_removed`. |
| E7 | **PASS** | Watermark + dead-letter + idempotency models present; replay of same `event_id` → `{"status":"duplicate","applied":false}`. `test_replay_is_idempotent`. |
| E8 | **PASS** | Static key + IP allowlist. No-key→401, wrong-key→401, valid→applied. Blank `ZOHO_WEBHOOK_KEY` → fail-closed 401 (`test_k5_zoho_webhook_rejects_when_no_key_configured`). |
| E9 | **PASS** | Per-referrer history fetch is lazy (`LogOnlyZohoAdapter.fetch_referrer_history` per-referrer, no bulk). |

### F. Admin dashboard / explorer / journey (M7)
| ID | Verdict | Evidence |
|---|---|---|
| F1 | **PASS** | `/admin-panel/` unauth → 302 `login/?next=…`; `/explorer/` same; login page 200; customer login off. Authenticated login succeeds. |
| F2 | **PASS** | Dashboard: KPI cards + funnel (from rollups) + sync-freshness top bar + top-referrer leaderboard (by client id, masked names); unique labelled APPROX; accounts_opened "FROM ZOHO" (screenshot L5). |
| F3 | **PASS** | Explorer: search + source dropdown + status filter; referral_link / partner-direct / off-platform (zoho_import) render as distinct badges; rows link to journey detail (screenshot L6). |
| F4 | **PASS** | Journey detail: source-tagged timeline + conversion panel (status, true open date, credited referrer by client id, opener by account id; **no mobile shown**) (screenshot L7). |
| F5 | **PASS*** | No dead UI / "Coming Soon" in admin; only flag-on features render. *See UI-1: stale marketing copy on `/` homepage. |

### G. Config cascade + compliance lock
| ID | Verdict | Evidence |
|---|---|---|
| G1 | **PASS** | central→global(admin)→user; global override of `wati_business_number` changes value; user tier dormant (`ENABLE_CUSTOMER_LOGIN=False`). `test_g1_global_override_beats_central`. |
| G2 | **PASS** | `COMPLIANCE_LOCKED_KEYS = {referral_incentive_claim, ap_disclosure_block, nse_ap_no}` bypass user/global; a global override to "WEAKENED" does not win (lock held). `test_g2_compliance_locked_at_central`. |
| G3 | **PASS** | WhatsApp number + incentive claim config-driven; changing config changes rendered value; `wa.me/917080642020` + "300 reward points + 10% brokerage share" render from config/flags. `test_g3_incentive_and_whatsapp_number_config_driven`. |

### H. Multi-tenancy (single-schema tenant_id)
| ID | Verdict | Evidence |
|---|---|---|
| H1 | **PASS** | `django_tenants` NOT in INSTALLED_APPS; custom `TenantResolutionMiddleware` (discriminator); every tenant-scoped model carries `tenant_id` (`TenantScopedModel`). No schema routing active. |
| H2 | **PASS** | 2-tenant fixture: tenant A query never reads tenant B's Partner rows. `test_h2_tenant_isolation_across_two_tenants`. |
| H3 | **PASS** | Composite unique `uq_program_tenant_partner_name` includes `tenant`. `test_h3_composite_unique_includes_tenant`. |

### I. Privacy / DPDP / PII
| ID | Verdict | Evidence |
|---|---|---|
| I1 | **PASS** | No PII in Event rows/metadata (scanned all events for name/mobile/email/IP → NONE); Event has no `raw_ip`/`name`/`mobile`/`email` field; PII by reference (`person_ref_id`). |
| I2 | **PASS** | Raw IP on separate `VisitorPII` (18 rows, not hashed, has `erased_at`); not on events. |
| I3 | **PASS** | Consent captured; Privacy Policy linked; erasure path (`VisitorPII` clear + `erased_at`, manual). `test_i3_visitor_pii_is_erasable`. |

### J. Guardrail tests
| ID | Verdict | Evidence |
|---|---|---|
| J1 | **PASS** | Redirect service does no POST/submit + opens no socket. `test_redirect_service_never_posts_to_zerodha`, `test_redirect_service_imports_no_http_client`, `test_redirect_makes_no_network_connection`. |
| J2 | **PASS** | Conversion/account status set only in Zoho ingest path; static + behavioural. `test_conversion_status_only_written_by_zoho_ingest_path`, `test_lead_capture_never_sets_account_opened`. |
| J3 | **PASS** | No `ZMPHZC` / `signup.zerodha.com` in any client-facing body (`/`, `/r/{id}`, `/open`, invalid page); present only in 302 Location. `test_no_partner_code_in_client_facing_response_bodies`. |

### K. Adversarial / break-it (my own tests)
| ID | Verdict | Evidence |
|---|---|---|
| K1 | **PASS** | `''→404`, illegal `AB@#$`/`RJ4521<script>`/21-char → 400 branded invalid (no 500, no journey); `../etc/passwd`→404; SQLi string harmless. |
| K2 | **PASS** | Forged/absent nonce → 401; valid → 200 name `null`; beacon confirm valid→202 then replay(consumed)→401; expired nonce→401. Id-enumeration yields no names. |
| K3 | **PASS** | WhatsApp / facebookexternalhit / Googlebot / TelegramBot / Twitterbot / empty-UA → 200 harmless, **0 identities created** (`BOTTEST1` count = 0). |
| K4 | **PASS** | Replay same `event_id`→duplicate/applied:false; forged webhook (no/wrong key)→401. |
| K5 | **FAIL** | See defect DEF-1: missing redirect-rule config → uncaught `ProgramRedirectRule.DoesNotExist` → HTTP 500 (traceback in DEBUG; generic 500 / uncaught-to-WSGI in prod), not the spec's branded 503 PARTNER_UNAVAILABLE. Blank webhook key / blank admin hash DO fail-closed correctly (K5 partial). Secrets not logged. |
| K6 | **PASS** | `ENABLE_ADMIN_DASHBOARD=false` → `/admin-panel/*` 404, home link hidden (no dead link). |

### L. UI acceptance (real browser, mobile + desktop)
| ID | Verdict | Evidence (screenshot) |
|---|---|---|
| L1 | **PASS** | Landing `/r/RJ4521` — generic greeting, form, two buttons, Referral ID echo, consent+privacy, disclosure. PIFS-branded, mobile-first single-column, not a Zerodha clone. (SS-landing-desktop, SS-landing-desktop-lower, SS-landing-mobile) |
| L2 | **N-A** | No separate thank-you page **by design**: doc-07 §9 + doc-12 Gap 6 lock "no separate confirm page" — the Referral-ID echo is the inline confirmation, and Continue redirects straight to Zerodha. `mockups/thankyou-mockup.html` exists but the locked spec supersedes it. Not shipped, correctly. |
| L3 | **PASS** | Invalid `/r/BAD@ID` — branded "This referral link isn't valid", fallback CTA "Open a Zerodha account with PIFS", disclosure + risk warning, no raw error. (SS-invalid-desktop) |
| L4 | **PASS** | Admin login — PIFS-branded, "single-admin console for Sprint 1. Customer self-service login is not enabled yet", no signup link. (SS-login-desktop) |
| L5 | **PASS** | Dashboard — KPI cards, funnel (from rollups), sync-freshness top bar, leaderboard; unique APPROX; accounts FROM ZOHO. (SS-dashboard-desktop) |
| L6 | **PASS** | Explorer — filters + table; referral_link / off-platform / partner-direct badges as distinct populations; rows link to detail. (SS-explorer-desktop) |
| L7 | **PASS** | Journey detail — source-tagged timeline + conversion panel (status, true open date 15 May vs synced 06 Jul, credited referrer by client id, opener by account id, no mobile). (SS-journey-desktop) |
| L8 | **PASS** | Disclosure + market-risk warning on all customer-facing pages (landing, invalid, homepage footer, login footer); incentive claim renders from config. |

### M. Cross-cutting / DoD
| ID | Verdict | Evidence |
|---|---|---|
| M1 | **PASS** | 118 tests pass incl. all 3 guardrails; ruff clean; migrations clean + forward-only; `makemigrations --check` no drift. |
| M2 | **PASS** | No `class/def Zerodha*`, no Zerodha-named files/tables/routes/models/events (only comments/labels use the word). `test_m2_no_zerodha_named_symbols_in_code` + my broader grep. |
| M3 | **PASS** | `.env.example` lists all 6 flags + every secret NAME; no secret values committed. |
| M4 | **PASS** | Phone normalized to `91XXXXXXXXXX` everywhere (`919876500011` stored; `apps/common/phone.py`). `test_phone.py` (7 tests). |
| M5 | **PASS** | `main`/branch deployable; demo end-to-end works with WATI/ZOHO off (LogOnly adapters). |

---

## Defect list

### DEF-1 — Missing redirect-rule config raises uncaught 500 instead of branded 503 (Medium)
- **ATP:** K5 (also spec 06-API §4.1 which specifies `503 PARTNER_UNAVAILABLE` branded HTML).
- **Severity:** Medium (config-integrity dependent — only triggers if the program has no active `ProgramRedirectRule`, which a correct `seed_program` prevents; but it is an ungraceful failure that leaks a traceback in DEBUG and 500s in prod).
- **Repro:**
  1. `ProgramRedirectRule.objects.update(is_active=False)` (simulate missing/misconfigured destination).
  2. `GET /r/RJ4521/continue`.
  3. **Observed:** HTTP 500; in DEBUG a full Django traceback page titled `DoesNotExist at /r/RJ4521/continue`; under `DJANGO_DEBUG=false` the `ProgramRedirectRule.DoesNotExist` propagates uncaught to WSGI (generic 500).
  4. **Expected (06-API §4.1):** branded 503 `PARTNER_UNAVAILABLE` HTML with retry guidance.
- **Root cause:** `apps/referrals/views.py::referral_continue` (and `referral_redirect` → `handle_landing_view` → `_active_program`) catch only `InvalidClientId`; `assemble_destination` / `_active_program` raise `ProgramRedirectRule.DoesNotExist` / `ReferralProgram.DoesNotExist` with no handler.
- **Fix direction:** wrap the config-resolution in the views (or add a middleware/handler) to render a branded 503 on `ProgramRedirectRule.DoesNotExist` / `ReferralProgram.DoesNotExist`.

### DEF-2 — `.env.example` sqlite default does not boot on Windows (Low / setup)
- **ATP:** §0 Setup ("`.env.example` → `.env` with demo values" then migrate).
- **Severity:** Low (setup friction; workaround is a one-line `.env` change).
- **Repro:** copy `.env.example` → `.env` unchanged (`DB_ENGINE=sqlite`, `DB_NAME=gorefer`); `manage.py migrate` → `django.db.utils.OperationalError: unable to open database file`. A bare `sqlite3.connect('gorefer')` reproduces it directly — Windows cannot open the extension-less relative filename in this working dir.
- **Fix direction:** ship `DB_NAME=gorefer_dev.sqlite3` (or an absolute path) in `.env.example` for the sqlite default, or have settings append `.sqlite3` / resolve to an absolute path when `DB_ENGINE=sqlite`.

### DEF-3 — Homepage marketing copy is stale ("arrive in the next slices") (Low / cosmetic-compliance)
- **ATP:** F5 / Constitution §4 (no "Coming Soon"-style copy for shipped features).
- **Severity:** Low (marketing homepage only; no dead links/buttons).
- **Repro:** `GET /` → body reads *"Sprint 1 foundation is live. Referral links and the branded landing page arrive in the next slices."* — but referral links and the branded landing page are already shipped. The copy describes shipped capability as forthcoming, which brushes against the no-"Coming Soon" principle.
- **Fix direction:** update `templates/home.html` hero copy to reflect the shipped Sprint-1 state.

### OBS-1 — Dashboard KPI "Total clicks" can diverge from funnel "Clicked" when rollups are stale (Info, not a defect)
- Observed KPI card "Total clicks 13" vs funnel "Clicked 31" on the same dashboard while all 34 raw click events were same-day. KPI/funnel read rollup tables (`DailyMetric`) while the leaderboard counts raw events; during heavy live testing between rollup recomputes the rollup lags the event stream. In normal operation the rollup worker (`recompute_rollups` / dirty-days) keeps them consistent, and `seed_demo` data renders consistently. Flagged for awareness; recommend the DA confirm the rollup-refresh cadence on the KPI card so an operator never sees a stale headline number next to a fresher funnel.

### Minor spec divergence (noted, not filed as a blocking defect)
- **A-min:** client_id validator regex is `^[A-Za-z0-9]{1,20}$` (min 1, max 20) vs spec 06-API §4.1 `^[A-Za-z0-9]{4,16}$`. Effect: 1–3-char and 17–20-char ids are accepted (still lazily created, still only credit that id, `c=ZMPHZC` always credits PIFS) rather than rejected to the invalid page. Graceful either way; DA should confirm the intended bound.

---

## UI screenshot index
(Captured in-browser; the `save_to_disk` screenshot variant timed out repeatedly on this host — the landing page fires beacon `fetch`es on load — so images were verified in-session rather than written to disk. Referenced by logical name.)

| Name | Page | Viewport |
|---|---|---|
| SS-landing-desktop | `/r/RJ4521` landing (hero, generic greeting, benefits, form start) | 1280 |
| SS-landing-desktop-lower | `/r/RJ4521` (consent, Referral ID echo, two buttons, incentive, disclosure) | 1280 |
| SS-landing-mobile | `/r/RJ4521` mobile single-column card | ~390 |
| SS-invalid-desktop | `/r/BAD@ID` branded invalid-referral page | 1280 |
| SS-login-desktop | `/admin-panel/login/` admin sign-in | 1280 |
| SS-dashboard-desktop | `/admin-panel/` KPIs + funnel + sync bar + leaderboard | 1280 |
| SS-explorer-desktop | `/admin-panel/explorer/` filters + table + source badges | 1280 |
| SS-journey-desktop | `/admin-panel/journey/1/` timeline + conversion panel | 1280 |

---

## Summary

- **PASS:** all of §A (A1–A8), §B (B1–B8), §C (C1–C6), §D (D1–D6), §E (E1–E9), §F (F1–F5*), §G (G1–G3), §H (H1–H3), §I (I1–I3), §J (J1–J3), §K1–K4, §K6, §L1/L3–L8, §M1–M5.
- **N-A:** §L2 (thank-you page intentionally not built — locked spec, "no separate confirm page").
- **FAIL:** §K5 (DEF-1 — missing-config path 500s instead of a branded 503).
- **Defects:** DEF-1 (Medium), DEF-2 (Low setup), DEF-3 (Low cosmetic-compliance); OBS-1 + A-min noted for DA confirmation.

The build is functionally strong: all three guardrails are active and green, Zoho-only conversion truth holds end-to-end (single-winner by client id, opener by account id, true open date, reversal tombstone), the redirect never touches Zerodha, bot filtering + nonce-gated name-reveal + PII separation all behave adversarially, tenant isolation holds, and every UI surface is PIFS-branded, mobile-first, compliance-locked, and free of dead UI (bar the homepage copy). The one true functional FAIL is a non-happy-path safe-failure gap (DEF-1); the rest are low-severity setup/cosmetic items.

**READY FOR DA SIGN-OFF: no** (one FAIL — DEF-1 — plus DEF-2/DEF-3 to clear; all are small, well-scoped fixes for the builder to address, after which a re-run should go green.)
