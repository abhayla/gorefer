# GoRefer — M9 Independent Verification Report (Phase-B)

> **Scope.** PR #10 (`mission-9-referral-profile`) — Zoho-READ enrichment + User Referral Screen ("Referral Profile") + whole-app Variant C re-skin. Verified by an **independent verifier** (not the engineer), against `CLAUDE.md`, `COORDINATION.md` (M9 mission, DESIGN LOCKED, M9 REVIEW = ACCEPTED + 2 copy decisions), `review/Acceptance-Test-Plan.md`, and `mockups/*.html` (the approved Variant C visual truth).
>
> **Commit verified:** `ea10dce` (HEAD of `mission-9-referral-profile`, == `origin/mission-9-referral-profile`).
> **Date:** 2026-07-08. **DB:** authoritative **PostgreSQL 16** on a dedicated **`gorefer_test`** database (role `gorefer`, `127.0.0.1:5432`; NOT `gorefer_dev`). **Mode:** demo (`ENABLE_DEMO_MODE=true`, all WATI/Zoho send/read flags off).
>
> **Secrets:** Postgres superuser creds (from `GLOBAL.env`) used only to `CREATE DATABASE gorefer_test`; the app connects as the `gorefer` role via the gitignored `.env`. No credential value is printed in this report or committed anywhere.

---

## Verdict (top line)

**READY TO MERGE — NO.** One **Medium** UI defect blocks a clean merge: **DEF-M9-1 — the Referral Profile top-band KPI rings (Clicks / Leads / Accounts) render empty** because `referrer_profile.html` never loads `rings.js`. The underlying data is correct and the fix is one line, but the headline aggregates on the flagship M9 screen are visually broken, so it should be fixed + re-shot before merge.

Everything else passes: authoritative Postgres run **151 passed / 0 failed / 0 skipped**; Variant C fidelity across all 9 screens at mobile 390 + desktop 1280; Referral Profile behaviour (per-link Zerodha-only card, both tabs, bot exclusion, 404s, search); guardrails #2 and #3; compliance verbatim on customer pages. The **two copy decisions** are split: **Decision 2 (null-referrer row) = PASS**; **Decision 1 (thank-you helpline number) = PENDING** — correctly deferrable per the mission ("tiny config follow-up; don't fail the whole run for them"), and it does **not** count toward the NO above.

---

## 1. Authoritative Postgres run — PASS

Dedicated `gorefer_test` DB (owned by role `gorefer`, which has `CREATEDB` so the pytest runner creates `test_gorefer_test`). `.env` pointed at `DB_ENGINE=postgres` / `DB_NAME=gorefer_test` for the run, then restored to `gorefer_dev`.

| Step | Result |
|---|---|
| `manage.py check` | `System check identified no issues (0 silenced).` |
| `manage.py migrate` | Applies clean from an empty DB (tenants, config, referrals, events, integrations, django_q, sessions — incl. the partial-unique conversion constraints, Postgres-native). |
| `makemigrations --check --dry-run` | `No changes detected` (exit 0) — **no migration drift**. |
| `seed_program` | tenant + central config + partner (ZMPHZC) + program (Zerodha) + redirect rule. |
| `seed_demo` | `4 referrers + partner-direct; 2 Zoho-sourced conversion(s); 3 rollup period(s).` |
| `bootstrap_admin` | `Bootstrap admin 'admin@pifs.in' created.` (hash-only) |
| **`pytest` (Postgres)** | **`151 passed in 71.74s`** — 151 collected, **151 passed, 0 failed, 0 skipped**. |
| `pytest` (SQLite parity) | `151 passed` — identical count, no engine-specific divergence. |
| `ruff check .` | `All checks passed!` |

**Note on count:** the M9 STATUS log says "152 pass"; the suite currently **collects 151** and all 151 pass (verified `--collect-only`: 151 tests collected). The off-by-one is immaterial — **0 failures** on both engines. No conditional/DB-gated skips exist (`conftest.py` only sets the default engine; no `skipif`).

All three guardrail tests are present and green in the suite:
`test_redirect_service_never_posts_to_zerodha`, `test_redirect_makes_no_network_connection` (#1); `test_conversion_status_only_written_by_zoho_ingest_path`, `test_lead_capture_never_sets_account_opened`, `test_zoho_read_never_writes_conversion` (#2); `test_no_partner_code_in_client_facing_response_bodies` (#3).

---

## 2. Screenshot pass (mobile 390 + desktop 1280) — PASS (1 defect noted)

Rendered every screen in a real Chromium (headless, via CDP — the Claude browser extension was not connected in this environment, so headless Chrome + DevTools Protocol was used to drive authenticated pages with the admin session cookie). 20 PNGs in `review/screenshots-m9/`.

| Screen | Route | Mobile 390 | Desktop 1280 | Variant C fidelity vs mockup |
|---|---|:--:|:--:|---|
| Home | `/` | ✓ | ✓ | Cobalt logo tile, hero "Refer smarter. Track everything.", present-tense copy (DEF-3), cobalt "Admin sign in" pill, compliance footer. |
| Landing | `/r/RJ4521` | ✓ | ✓ | Generic "Someone" greeting (cobalt accent), rounded-2xl cards, cobalt Continue pill + cobalt-outline Share pill, benefits w/ cobalt checks, **Referral ID: RJ4521** echo, consent + Privacy Policy, "10% brokerage share + 300 reward points" (reordered claim), **full SEBI disclosure + risk warning**. |
| Invalid | `/r/AB` | ✓ | ✓ | Branded "This referral link isn't valid.", amber icon, fallback CTA, full disclosure. Confirms A-min (`AB`, 2 chars, now rejected). |
| Partner-unavailable | `/open` w/ rule inactive → 503 | ✓ | ✓ | Branded "This is temporarily unavailable.", full disclosure, **no traceback** (DEF-1 confirmed on Postgres). |
| Admin login | `/admin-panel/login/` | ✓ | ✓ | Cobalt "P" tile, "Sign in to continue", cobalt Sign in pill, "single-admin console… not enabled yet" (no dead UI), compliance footer. |
| Dashboard | `/admin-panel/` | ✓ | ✓ | Pill nav (active=cobalt), sync-freshness top bar, **KPI SVG rings render** (Total Clicks 24, Unique 18 APPROX, Accounts 2 FROM ZOHO, Leads→Accounts 100% green ring), cobalt funnel w/ "counts as of…" (OBS-1), leaderboard w/ null-referrer rows, masked mobile. |
| Explorer | `/admin-panel/explorer/` | ✓ | ✓ | Sortable table, chip source badges (**Off-platform / Partner-direct / Referral link** as distinct populations), status badges, search + filters, referrer names + "— name not on file —". |
| Journey | `/admin-panel/journey/1/` | ✓ | ✓ | Source-tagged timeline (click/beacon/form/redirect/zoho), conversion panel: **true open date 15 Jun 2026 ≠ synced 08 Jul 2026** (ADR-017), credited referrer RJ4521, opener account ZA9001 (no mobile), "mirrored from Zoho — never fabricated". |
| **Referral Profile** | `/admin-panel/referrer/RJ4521/` | ✓* | ✓* | Top band, Zoho chips, per-link Zerodha card (**no Loan card**), both tabs, bot-dimmed row. **\*DEF-M9-1: the 3 top-band KPI rings render EMPTY** (see §5). |

Screenshot index (all in `review/screenshots-m9/`): `home-{mobile,desktop}`, `landing-*`, `invalid-*`, `partner-unavailable-*`, `login-*`, `dashboard-*`, `explorer-*`, `journey-*`, `referral-profile-*`, `referrer-search-*`.

No page renders a Zerodha clone; all use the compiled `app.css` (no CDN — `cdn.tailwindcss`/`unpkg` count = 0 on every page); profile JS/CSS served 200.

---

## 3. Referral Profile behaviour — PASS

Route `/admin-panel/referrer/RJ4521/` (demo, `ENABLE_ZOHO_READ` off → fixtures).

- **Top band** — "Rajesh Joshi", RJ4521 chip, **Active Investor** chip; Zoho enrichment chips (Pune MH · Salaried—IT · Active—opened 2019-03-12 · Reward Eligible) with "Profile fields from Zoho CRM (matched by Client Id)" note. Four headline aggregates present in the DOM (`data-display` clicks=12, leads=1, accounts=1, visitors rendered) — **but see DEF-M9-1: three render as empty rings.**
- **Per-link card** — one **Zerodha** card (code ZMPHZC, `gorefer.in/r/RJ4521`, 12 clicks / 1 leads / 1 accounts). **The illustrative "Loan" card is NOT shipped** (grep count = 0). Structure supports N partners.
- **Clicks tab** — per-click rows with **Date · Partner · Channel · City · Region · Country · IP · Device · OS/Browser · Traffic · Outcome**; geo/device from GoRefer's own Event + VisitorPII (IP) + UA (Android/Chrome/WhatsApp/iOS-Safari, real cities Pune/Mumbai/Nashik). **Bot/preview row dimmed + "Bot — excluded"** (1 Googlebot row). Headline clicks + per-link clicks + unique visitors all computed with `is_bot=False` (bots logged, excluded from totals). Filter chips (All/human/bot/Mobile/Desktop/WhatsApp) + city/IP search + sortable headers via `referral_profile.js` (served 200).
- **Referred People tab** — "Referred People · 3" with Name/Profession/Account Status/Opened/Reward (Zoho READ fixtures).
- **Search entry** — `/admin-panel/referrers/` renders (200); exact `?q=RJ4521` **302-redirects to the profile**; by-name lists matches; empty query friendly.
- **404s** — unknown id `ZZ9999` → 404; malformed `AB` (sub-min) → 404; malformed `A@#` → 404.

Tests backing this (all green): `test_profile_renders_top_band_and_zoho_enrichment`, `…missing_zoho_value_shows_not_on_file`, `…unknown_client_id_404`, `…invalid_client_id_404`, `…clicks_tab_has_enriched_rows`, `…headline_clicks_exclude_bots`, `…ip_from_visitor_pii`, `…referred_people_from_zoho`, `…only_real_enabled_partner_cards`, `…columns_are_config_driven`, `test_referrer_search_*`, `test_zoho_read_*`.

---

## 4. Guardrails + compliance — PASS

- **Guardrail #2 (status only from Zoho; viewing a profile creates no Conversion).** Empirical: conversion-bearing referrals = **2 before** viewing profiles and **2 after** repeated views of RJ4521 + a fresh unknown id (which 404s, no lazy creation). With `ENABLE_ZOHO_READ` off the adapter returns fixtures and writes nothing. Backed by `test_zoho_read_never_writes_conversion` + the two ingest-only guardrail tests. **PASS.**
- **Guardrail #3 (no partner code / raw Zerodha URL on customer pages).** Body scan: `/` → ZMPHZC 0, zerodha URL 0; `/r/RJ4521` → 0, 0; dashboard → 0, 0; explorer → 0, 0. `/open` is a **302** whose `Location` is `https://signup.zerodha.com/api/lead/?c=ZMPHZC` (no `r=`, per ADR-015) — the partner code appears **only in the redirect Location**, which is allowed (that *is* the redirect). The Referral Profile per-link card **does** show `ZMPHZC` — correctly allowed, it is an **admin** screen (mission + #3 test scope is `/`, `/r/{id}`, `/open`, dashboard, explorer). **PASS.**
- **Guardrail #1 (redirect never submits / opens no socket).** Green in the suite (behavioural socket-block + no-http-import tests). **PASS.**
- **Compliance.** Landing (`/r/RJ4521`), invalid, and partner-unavailable carry the **full disclosure block** (`Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693`) + the market-risk warning, un-removable via `compliance_disclosure.html`; the incentive claim renders from the single `REFERRAL_INCENTIVE_CLAIM` config. Ashok's personal number `73888…` does **not** leak onto the customer landing (count 0). **PASS** (see OBS-2/OBS-3 for two low-severity wording/scope notes).

---

## 5. Defects & Observations

### DEF-M9-1 — Referral Profile top-band KPI rings render EMPTY (Medium) — **BLOCKS clean merge**
- **Where:** `templates/dashboard/referrer_profile.html` (the M9 Referral Profile screen, new in M9).
- **Symptom:** the three top-band conversion rings — **Clicks / Leads / Accounts** — render as blank rounded boxes at both mobile 390 and desktop 1280. Only the 4th tile (plain-HTML "Visitors") shows a value. (Evidence: `referral-profile-desktop.png`, `referral-profile-mobile.png`.)
- **Root cause:** the rings are `<div data-ring …>` placeholders drawn by **`static/js/rings.js`**. `dashboard.html` includes `rings.js` (and its rings render fine — see `dashboard-desktop.png`), but `referrer_profile.html` includes only `referral_profile.js` and **never loads `rings.js`**. `dashboard/base.html` does not load it globally. So the profile's `data-ring` divs have no drawing code.
- **Data is correct:** the DOM carries `data-display="12"` (Clicks), `"1"` (Leads), `"1"` (Accounts); the same numbers also render as text in the per-link Zerodha card. Only the SVG draw is missing — which is why the passing tests (they assert on data/DOM attributes, not rendered SVG) did not catch it.
- **Fix (one line):** add `<script src="{% static 'js/rings.js' %}"></script>` to `referrer_profile.html` (alongside the existing `referral_profile.js` include), then rebuild is not needed (JS only) — re-screenshot to confirm.
- **Severity rationale:** Medium, not High — no data is wrong, the values are visible elsewhere on the page, and it's a trivial fix; but it visibly breaks the flagship M9 screen's headline aggregates, so it should not merge as-is.

### OBS-1 (copy Decision 1) — Thank-you helpline number NOT wired — **PENDING** (not a blocker)
- The DA's Decision 1 (2026-07-08) asks the **thank-you page** to show Ashok's helpline **`+91 73888 82020`** (config `SUPPORT_HELPLINE_PHONE`), while Share-on-WhatsApp stays on WATI `+91 70806 42020`.
- **State:** there is **no thank-you page** in the app (only `mockups/thankyou-mockup.html`); the "Continue to Zerodha" flow does a direct 302 to Zerodha with no intermediate page. There is **no `SUPPORT_HELPLINE_PHONE` config key** (only `OFFICE_ALERT_NUMBER=917388882020`, used for the WATI Ashok alert, and `WATI_BUSINESS_NUMBER=917080642020` for the share).
- **The WhatsApp half IS correct:** the landing "Share referral details on WhatsApp" routes to the config-driven WATI number `917080642020` (`WATI_BUSINESS_NUMBER`, resolved via config into `landing.html`) — verified live.
- **Disposition: PENDING**, per the mission ("if these aren't wired yet, mark them PENDING — a tiny config follow-up the engineer applies — don't fail the whole run for them"). The engineer should add a `SUPPORT_HELPLINE_PHONE` config + wire a thank-you page (or the DA should confirm no thank-you page is in M9 scope). **Does not count toward the merge-NO** — DEF-M9-1 alone does.

### OBS-2 (copy Decision 2) — Null-referrer row present — **PASS**
- The Explorer shows "**— name not on file —**" rows (count 3: GW5500 off-platform, MK9033, SG2210 referral-link), and the dashboard leaderboard shows the same null-referrer state. Seeded via MK9033/SG2210/GW5500. No action needed (matches the DA decision).

### OBS-3 — Market-risk / disclosure wording is not byte-verbatim to the spec (Low — pre-existing, carried through the re-skin)
- **Spec & mockup:** "Investments in **securities market** are subject to market risks**,** read all the related documents carefully before investing."
- **App renders:** "Investments in **the** securities market are subject to market risks**;** read all the related documents carefully before investing." (extra "the"; ";" for ",").
- Compliance copy is required **verbatim**; the app diverges from both the spec and the approved mockup on every page. This predates M9 (the re-skin preserved it) and was marked PASS in the prior Phase-B report (B8/L8), so the DA has effectively accepted it — flagging for an explicit call. **Low.**

### OBS-4 — Homepage footer omits the full SEBI disclosure block (Low — pre-existing, DA-accepted)
- `/` renders the NSE AP reg no + market-risk warning but **not** the full `SEBI Registration no.: INZ000031633 | … | NSE AP …` block (the landing/invalid/partner-unavailable pages do). doc-07 §3 lists the "AP disclosure block" for the homepage footer. Prior Phase-B report accepted the shorter marketing-page footer (L8 PASS). Flagging for consistency; **Low**, not introduced by M9.

---

## 6. Cross-cutting

- `main`/branch deployable; demo mode runs end-to-end offline with WATI/Zoho flags off. No source files modified by this verification (only `review/screenshots-m9/` added; `.env` restored to `gorefer_dev`).
- Provider-agnostic naming holds (`test_m2_no_zerodha_named_symbols_in_code` green). No secrets in committed files; `.env` gitignored; superuser creds never printed/committed.
- Compiled `app.css` served, no CDN anywhere; multi-line `{# #}` guard + PII-in-events + no-CDN guards all green in the suite.

---

## Final line

**READY TO MERGE — NO.** Blocking item: **DEF-M9-1** (Referral Profile top-band KPI rings render empty; one-line fix: load `rings.js` in `referrer_profile.html`, then re-screenshot). After that fix re-verifies, this flips to **YES**. Copy **Decision 1 (thank-you helpline)** is **PENDING** — a separate small config follow-up, explicitly not a blocker per the mission; **Decision 2 (null-referrer row)** is done. OBS-3/OBS-4 (disclosure wording / homepage footer) are pre-existing, DA-accepted, Low — for an explicit DA call, not blockers.

---

# ADDENDUM — Scoped Re-verify (fix batch) — 2026-07-08

> **Trigger.** DA entry "Fix batch accepted · final SCOPED re-verify then merge" (COORDINATION.md, 2026-07-08). The engineer's fix batch (commit **`38390fb`**, "M9 fix batch: rings.js on profile + helpline config + compliance verbatim") addresses the blocker + two fold-ins from the report above. Per the DA, this is a **scoped** re-pass (4 items), **not** a full rerun — and explicitly **do not trust the builder's self-confirm on the rings** (the exact bug that slipped a non-visual check).
>
> **Commit re-verified:** `38390fb` (HEAD of `mission-9-referral-profile`, == `origin/mission-9-referral-profile`). Independent verifier, fresh pass. Live checks on Postgres `gorefer_test`; suites on Postgres **and** SQLite.

## Scoped items

| # | DA re-verify item | Result | Evidence |
|---|---|:--:|---|
| 1 | **Referral Profile top-band KPI rings actually PAINT** (SVG visible, not empty boxes) at 390 + 1280 — the one must-see item. | **PASS** | Re-shot the profile at both widths. All **three** rings now render as painted SVG: **Clicks = 14** (full cobalt ring), **Leads = 1** (amber arc), **Accounts = 1** (green arc); 4th tile "Visitors 13*" plain-HTML as designed. Root cause fixed: `referrer_profile.html` now loads `<script src="…/rings.js">` (line 133) before `referral_profile.js`. Screenshots: `review/screenshots-m9-reverify/referral-profile-{mobile,desktop}.png`. |
| 2 | **Landing:** `tel:` helpline `+91 73888 82020` renders **AND** WhatsApp share target still WATI `917080642020` (no `wa.me/917388882020` anywhere). | **PASS** | Live `/r/RJ4521`: helpline renders as `<a href="tel:+917388882020">call +91 73888 82020</a>` ("Prefer a call? Free, fully-assisted account opening — call +91 73888 82020"), config-driven via `SUPPORT_HELPLINE_PHONE`. Share button target = `watiNumber: "917080642020"`. **`wa.me/917388882020` count = 0** (and 0 for any `wa.me…7388882020` form) — Ashok's number is never the share target, only a `tel:` line. Screenshot: `landing-desktop.png`. |
| 3 | **Compliance:** `test_compliance_strings_byte_exact_on_customer_pages` green + homepage footer now carries the full SEBI disclosure block. | **PASS** | `test_compliance_strings_byte_exact_on_customer_pages` → **1 passed**. Independent byte-exact grep on `/`, `/r/RJ4521`, `/r/AB`, `/admin-panel/login/`, and the 503 partner-unavailable page: canonical **disclosure** (`…Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693`) present on all; canonical **risk warning** (`Investments in securities market are subject to market risks, read all the related documents carefully before investing.` — no "the", comma) present on all; the **old drifted wording ("Investments in the securities market") is gone everywhere (count 0)**. Homepage now carries the full SEBI block (`Zerodha Broking Ltd.` + `INZ000031633` + `Private Limited` + `AP2516003693`) — OBS-4 fixed. |
| 4 | **Full pytest green** (154); Postgres optional. | **PASS** | **154 passed / 0 failed / 0 skipped** on **Postgres** (`gorefer_test`, 154 collected) **and** on **SQLite** (parity). The 3 new fix-batch tests pass (`rings_js` load, `compliance_strings_byte_exact`, helpline-distinct-from-share). `makemigrations --check` → no drift. `ruff check .` → **All checks passed!** |

## Disposition of the prior findings

- **DEF-M9-1 (was the Medium blocker) → RESOLVED.** Rings paint, visually confirmed at 390 + 1280 (not a self-confirm — screenshotted by the independent verifier). New test `test_profile_loads_rings_js_so_kpi_rings_paint` locks it.
- **OBS-1 (copy Decision 1 helpline) → RESOLVED.** Premise corrected by the DA (no thank-you page exists; capture → 302 to Zerodha per M3). Helpline now surfaced on the **landing** page as a config-driven `tel:` line; WhatsApp share unchanged (WATI). DA locked "keep Ashok's number as a `tel:` line; `wa.me` share target must stay WATI" — implemented exactly.
- **OBS-2 (copy Decision 2 null-referrer row) → still PASS.**
- **OBS-3 (disclosure/risk wording not byte-verbatim) → RESOLVED.** Canonical single-source `AP_DISCLOSURE_BLOCK` + `MARKET_RISK_WARNING` constants; byte-exact on every customer page; drift gone.
- **OBS-4 (homepage omitted full SEBI block) → RESOLVED.** Full SEBI disclosure block now on the homepage footer.

No source files were modified by this re-verify; `.env` restored to `gorefer_dev`; server + headless Chrome stopped. Added evidence only: `review/screenshots-m9-reverify/`.

## Final line (scoped re-verify)

**READY TO MERGE — YES.** All four scoped re-verify items pass: the Referral Profile KPI rings now paint (visually confirmed at 390 + 1280 by the independent verifier, not a self-check); the landing shows the `tel:` helpline `+91 73888 82020` while the WhatsApp share stays on the WATI number `917080642020` (Ashok's number never the `wa.me` target); compliance strings are byte-exact on every customer page with the full SEBI block now on the homepage; full pytest **154 passed / 0 failed** on Postgres and SQLite, ruff clean, no migration drift. The prior blocker (DEF-M9-1) and both fold-ins (OBS-1/OBS-3/OBS-4) are resolved. **PR #10 is clear to merge; M9 done.**

---

# ADDENDUM 2 — Fresh INDEPENDENT scoped re-verify (DA "final SCOPED re-verify") — 2026-07-08

> **Trigger.** DA entry "Fix batch accepted · 1 confirmation · final SCOPED re-verify then merge" (COORDINATION.md, 2026-07-08), which explicitly says: *"Do NOT trust the builder's self-confirm on the rings — that's the exact bug that just slipped a non-visual check."* This addendum is a **fresh independent pass by the verifier session** that re-ran the four DA items itself and, for item 1, **regenerated the profile screenshots from a live running app and visually inspected the rendered SVG** rather than relying on any prior screenshot or the builder's word.
>
> **Commit re-verified:** `38390fb` (HEAD of `mission-9-referral-profile`; `git rev-parse HEAD == origin/mission-9-referral-profile == 38390fb`). **DB:** Postgres 16 (`gorefer_dev`, `DB_ENGINE=postgres`, role `gorefer`, `127.0.0.1:5432`) — same app connection from the gitignored `.env`; no credential printed/committed. **Mode:** demo (all WATI/Zoho send/read flags off → fixtures). **Method for item 1:** live `manage.py runserver` on `127.0.0.1:8009`; an admin session minted via `SessionStore` (staff user `admin@pifs.in`); headless Chrome 149 driven over the DevTools Protocol with that session cookie; screenshots captured **after** page JS executed.

## Scoped items — independent results

| # | DA re-verify item | Result | Independent evidence (this pass) |
|---|---|:--:|---|
| 1 | **Referral Profile top-band KPI rings actually PAINT** (SVG visible, not empty boxes) at 390 + 1280 — the one must-see item; do not trust a self-confirm. | **PASS** | I re-shot `/admin-panel/referrer/RJ4521/` myself at **1280** and **390** and looked at both PNGs: all **three** rings render as painted SVG arcs — **Clicks = 19** (full cobalt ring), **Leads = 1** (amber arc), **Accounts = 1** (green arc); the 4th tile "Visitors 16\*" is plain-HTML by design. No empty boxes at either width. Corroborated programmatically via CDP `Runtime.evaluate`: `document.querySelectorAll('[data-ring] svg').length` = **3** and `[data-ring] svg circle` = **6** (2 circles/ring = track + progress arc, exactly what `rings.js` draws) — proof the script executed, not merely that its `<script>` tag is present. Root cause confirmed fixed in-file: `templates/dashboard/referrer_profile.html:133` loads `<script src="{% static 'js/rings.js' %}">`. New screenshots: `review/screenshots-m9-reverify/reverify-profile-{desktop,mobile}.png`. |
| 2 | **Landing:** `tel:` helpline `+91 73888 82020` renders **AND** WhatsApp share target still WATI `917080642020` (no `wa.me/917388882020` anywhere). | **PASS** | Live `/r/RJ4521` served HTML: helpline renders as `tel:+917388882020` ("Prefer a call? Free, fully-assisted account opening — call +91 73888 82020"), visually confirmed on `reverify-landing-desktop.png`. Share button config value `watiNumber: "917080642020"`. Independent grep of the served body: `wa.me/917388882020` (and `wa.me/…7388882020`) count = **0** — Ashok's number appears only as a `tel:` line, never as the `wa.me` share target. |
| 3 | **Compliance:** `test_compliance_strings_byte_exact_on_customer_pages` green + homepage footer now carries the full SEBI disclosure block. | **PASS** | I ran the test directly → **1 passed**. Independent grep on the live homepage `/`: `Zerodha Broking Ltd.` = 1, `INZ000031633` = 1, `Passive Income Financial Solutions Private Limited` = 1, `AP2516003693` = 1 → the **full SEBI block is now on the homepage footer** (OBS-4 resolved). Canonical risk warning `Investments in securities market are subject to market risks, read all the related documents carefully before investing` present (no "the", comma). The old drifted wording `the securities market` count = **0** on `/`, `/r/RJ4521`, `/r/AB`, and `/admin-panel/login/`. |
| 4 | **Full pytest (154) green**; sqlite acceptable, Postgres optional. | **PASS** | **154 passed / 0 failed / 0 skipped** on **Postgres** (`gorefer_dev`) *and* **154 passed** on **SQLite** (`DB_ENGINE=sqlite` parity) — I ran both myself this pass. `ruff check .` → **All checks passed!**; `makemigrations --check --dry-run` → **No changes detected** (no drift). The three fix-batch tests live in `tests/test_referral_profile.py` (rings-js load), `tests/test_hardening.py` (compliance byte-exact), `tests/test_landing.py` (helpline distinct from WATI share). |

## Independent-verifier notes

- The must-see item (rings) was verified **visually, from screenshots I generated in this session against a live app** — not from the pre-existing `reverify-*` PNGs and not from the builder's STATUS entry. This is exactly the non-visual-check gap the DA flagged; it is now closed with a first-hand visual pass at both widths.
- One cosmetic artifact, **not a defect:** on this fresh environment the Clicks-tab rows show `Direct / 127.0.0.1 / curl` for a few rows — those are clicks generated by my own `curl` smoke-tests during setup (loopback IP, curl UA), overlaid on the seeded demo clicks. It does not affect the ring/compliance/helpline verification and is an artifact of the verifier's own probing.
- No source files were modified by this pass. Added evidence only: `review/screenshots-m9-reverify/reverify-profile-desktop.png`, `reverify-profile-mobile.png`, `reverify-landing-desktop.png`. Server + headless Chrome stopped afterward.

## Final line (Addendum 2 — fresh independent pass)

**READY TO MERGE — YES.** All four DA scoped items independently re-verified on commit `38390fb`: (1) the three Referral Profile KPI rings **paint** as SVG at both 390 and 1280 — visually confirmed by the verifier's own live screenshots plus a CDP DOM count of 3 SVGs / 6 circles inside `[data-ring]`, not a self-confirm; (2) the landing shows the `tel:` helpline `+91 73888 82020` while the WhatsApp share stays on WATI `917080642020` (zero `wa.me` to Ashok's number); (3) `test_compliance_strings_byte_exact_on_customer_pages` passes, the full SEBI block is on the homepage footer, and the drifted wording is gone everywhere; (4) full pytest **154 passed / 0 failed** on both Postgres and SQLite, ruff clean, no migration drift. **PR #10 is clear to merge; M9 done.**
