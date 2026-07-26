# E2E test queue — durable state for the fix-until-green loop

> **This file is the loop's memory.** Each iteration: read it, take the FIRST `[ ]` item in
> READY, do it, rewrite its line with the verdict, commit. Never rely on conversation context —
> it gets summarized away. Procedure for each item: `.claude/skills/e2e-whatsapp-communication`.
>
> **Definition of done for an item:** tested against LIVE prod → any defect fixed at ROOT (not
> symptom) → regression test added → full suite green (CI-parity env) → deployed → **verified at
> the destination**. Then, and only then, mark `[x]`.
>
> **Stop condition for the loop:** READY is empty. Then post the summary and end the loop.
> Items that need Abhay move to BLOCKED — never guess, never stall the whole queue on one.
>
> **Last updated:** 2026-07-26 (9 owner decisions captured — see DECIDED)

## Rails (apply to every iteration)

- WhatsApp sends: **only** `919999900000` / `919999900000`. Never any other number.
- `919999900000` is currently Meta **quality-restricted** for MARKETING — use `919999900000`
  for delivery proof, and treat a restriction failure there as a recorded outcome, not a defect.
- Pass bar for a message is **`sent`/accepted**; `delivered`/`read` is bonus.
- Template change ⇒ **HTML map FIRST**, then Meta, then map again (`CLAUDE.md` §6c).
- Never test in `/var/www/gorefer` — sync to `/tmp/glocal` and use the CI-parity env.
- Deleting Meta templates or prod rows, and any spec decision, goes to **BLOCKED**.
- Append a STATUS line to `COORDINATION.md` each iteration.
- **Attempt budget (anti-wedge):** an item that fails **3 attempts** moves to BLOCKED with the
  evidence of each attempt — the loop always takes the FIRST `[ ]` item, so without this rule one
  persistently-failing item wedges the entire queue (independent review finding, 2026-07-26).
  Mark attempts inline: `(attempt 2/3: <what failed>)`.
- **Sends are not idempotent:** re-running a send item re-messages real numbers. Before retrying
  any item that already sent something, check what actually went out (Wati `getMessages`) first.

## READY

- [x] **Zoho conversion webhook (Phase 5) — DONE 2026-07-26, all green.** See DONE section.
- [x] **Follow-up engine gates (Phase 6) — DONE 2026-07-26, all 5 green.** See DONE section.
- [x] **Admin dashboard routes (Phase 9) — DONE 2026-07-26, all 7 green.** See DONE section.
- [x] **API surface (Phase 10) — DONE 2026-07-26; found + fixed broken access control.** See DONE.
- [x] **`POST /api/leads/` over HTTP (Phase 3) — DONE 2026-07-26, all green.** See DONE section.
- [ ] **Bot filter breadth (Phase 2).** All 8 crawler UAs, not the 2 already covered.
- [ ] **Withdraw the superseded PENDING v1 template**
      `gorefer_referrer_prospect_pending_en_2026_07_25` (v2/v3/v4/v5 supersede it). NOTE: Wati
      DELETE returns `ok:true` but Meta keeps the language content (`2388024`), so the name
      cannot be reused afterwards.
- [x] **Sync prod's `tests/` tree** — DONE 2026-07-26 (review session): 4 files copied
      (`test_followups.py`, `test_m_wati1_share_intent.py`, `test_recipient_identity.py`,
      `urls_share_intent.py` — the earlier "3 files" count was wrong), prod now 48/48 vs repo.
- [x] **Fix `CURRENT-STATE.md` staleness** — DONE 2026-07-26 (review session): funnel-report
      line corrected to APPROVED (verified vs live inventory); deployed-SHA row rewritten to
      `324a1b8` (PR #52); OTP P0 recorded on the `ENABLE_OTP_LOGIN` row.
- [ ] **Landing page + capture form (Phase 11).** Needs a temporary `set_landing_mode page`
      flip (revert after). Only way to exercise the JS beacon / confirmed-human click.
- [ ] **Hindi, DPDP, rollups, cross-tenant (Phase 12).** `pref_lang='hi'` end-to-end; PII out of
      the event log + erasable `VisitorPII`; manual erasure; rollup arithmetic vs raw events;
      conversions on the true opening date; tenant-scoped manager isolation.
- [ ] **24 Zoho/Wati journey templates.** Owned outside this repo — drive the Zoho Deluge
      functions (`ZOHO_FN_ZAPIKEY_WA_JOURNEY_*` in `GLOBAL.env`) and Wati flows directly.
      A GoRefer-only run cannot reach these; do not report them as covered until driven.

## DECIDED by the owner 2026-07-26 — now actionable (was BLOCKED)

**Standing principle stated by the owner:** *"All such message settings should be configurable"* —
message behaviour belongs in the config cascade + Preferences, never hard-coded. Apply to every
item below and to future work.

- [ ] **D1 · `/open` destination → default `https://signup.zerodha.com/?c=ZMPHZC`, but CONFIGURABLE.**
      Owner wants to switch it to `/api/lead/?c=ZMPHZC` or any other URL without a code change.
      So: add a cascade key + Preferences field, default to the bare signup (the CLAUDE.md value),
      which also CHANGES current live behaviour away from `/api/lead/`.
- [ ] **D2 · Crawlers get a PIFS preview card, and its text is CONFIGURABLE.** Real humans still
      302 to Zerodha; only the crawler fetch changes. Title/description from config.
- [ ] **D3 · Turn the Zoho webhook IP allowlist ON.** Owner: fetch Zoho's ranges myself — no Zoho
      login needed (they are published publicly). Order: fetch ranges → cross-check against real
      inbound webhook IPs → set `ZOHO_WEBHOOK_IP_ALLOWLIST` + `WEBHOOK_REQUIRE_IP_ALLOWLIST=true`
      → **immediately send a live sealed conversion to prove ingestion still works.** Wrong IPs
      silently stop real conversions, so the live re-test is mandatory, not optional.
- [ ] **D4 · Repeat form submissions: FILL BLANKS ONLY + ONE LEAD PER MOBILE.** Empty field → take
      the new value; already-populated field → keep it (so spam/typos can't overwrite good data).
      Plus: a mobile gets **one** Lead — a re-submission updates that Lead instead of creating a
      second. (Prod today has 2 leads on `919876543210`.) This also aligns GoRefer with Zoho, which
      already upserts by mobile. **Flag when implementing:** decide what a *different* referrer
      re-submitting the same mobile means for attribution — Zoho stays the single source of credit.
- [ ] **D5 · Decouple converted-suppression from `stop_on_reply`, and make it CONFIGURABLE.**
      "Account already open → never nudge" must always apply regardless of the reply setting, and
      be switchable from config without code.
- [ ] **D6 · Delete the superseded duplicate templates, keep genuinely different ones.** Only ones
      that are an older version of a message already in use. Note Meta holds a deleted name ~30 days.
- [ ] **D7 · Soft-delete the junk `TALK` and `ZMPHZC` referrer records** (reversible; rows retained).
- [ ] **D8 · Test the WhatsApp-OTP login path only; SKIP Google OAuth for now.** Owner will paste the
      6-digit code when asked (WhatsApp hides OTPs from linked devices, so this cannot be automated).
      Google sign-in — the PRIMARY referrer login — therefore stays UNTESTED; keep saying so.
- [ ] **D9 · Cut marketing volume and re-cut nudges as UTILITY.** UTILITY escapes Meta's per-user cap
      (`131049`), the dominant cause of the ~43% delivery rate. Reframe copy as transactional
      ("your account is still pending") not re-solicitation ("still want to open one?") — proven to
      flip Meta's classification on this tenant. Leave `919999900000` to recover on its own.

## BLOCKED — still needs Abhay

## DONE

- [x] **Phase 3 — `POST /api/leads/` over HTTP verified LIVE (2026-07-26). No defects.**
      This is the path `golive_smoke` bypasses, so none of it had ever been exercised.
      **Validation, all correct:** `consent:false` → **422 "consent is required"** (the DPDP gate) ·
      consent field absent → 422 at the schema · mobile starting `5` → 422 · 1-char name → 422 ·
      `client_id` with spaces/`!` → **400** · 40-char `client_id` → 400 · unknown `client_id` → 400
      "no active referral journey". Every rejection happens BEFORE `capture_lead`, so an invalid
      POST cannot reach Zoho.
      **Rate limiter WORKS — 429 at request 11 of a 10/60s budget, in a 7-second burst.** First
      attempt appeared to show it dead; that was my own test spread over more than the 60s window,
      not a defect. Direct `check_rate` also blocked 5 of 15 at limit 10. Cache backend is the DB
      table `gorefer_cache` (shared across gunicorn workers, as intended).
      **Phone normalization:** `"+91 98765-43210"` → stored `919876543210`.
      **PII stays out of the event log** (Round-2 #16): `lead_captured` metadata `{}`; zero hits for
      the submitted name / mobile / email / city across every event on the referral; no metadata key
      intersects the `PII_KEYS` guard (`address,city,email,ip,mobile,name,phone,raw_ip`). Raw IP
      lives in the separate erasable `VisitorPII` table (143 rows).
      **Response leaks nothing:** `continue_url` is `/r/E2E0726/continue` — no partner code, no
      Zerodha URL (guardrail 3).
      **CLEANUP OWED:** Lead 10 + Zoho lead `475281000030612001`.
      Raised as a DA decision: the returning-prospect upsert discards newly-submitted details.

- [x] **Phase 10 — API surface verified LIVE (2026-07-26). P1 FOUND + FIXED: broken access control.**
      `/api/analytics/funnel`, `/journey/{id}` and `/sync-health` had **NO auth** and answered any
      anonymous caller on the internet: the AP's whole funnel (124 clicks, 44 landing views, 9 leads,
      4 accounts opened, 25 confirmed-human, 84 approx unique visitors), an **enumerable** per-journey
      event timeline (ids are sequential ints), and internal integration health. The `/admin-panel/`
      screens showing the same figures were behind `login_required` + `is_staff` — the UI was gated,
      the API feeding it was not. **No PII leaked** (the event log excludes PII by design, Round-2
      #16 — that guardrail held), but the metrics are business-confidential.
      Fixed by gating the router with `apps.followups.api.require_staff` — the SAME plain-callable
      auth the follow-up CRUD router already uses, so there is one staff-auth mechanism, not two.
      Safe to gate: grep proved nothing but tests called these endpoints (the dashboard computes
      server-side). Verified live in BOTH directions — anonymous **401**, staff **200**, and the
      dashboard byte-identical at 27,744 bytes.
      **Already correct, confirmed:** `/api/wati/webhook` **401** (the old fail-OPEN bug is closed) ·
      `/api/wati/inbound` **401** · `/api/click/referrer/{id}` **401** without a fresh nonce
      (id→name enumeration shut) · `/api/health` 200 exposing no partner code or Zerodha URL ·
      `/api/click/confirm`, `/api/share/`, `/api/leads/` all 422 on an empty body (schema validation).
      Tests: 2 new access-control tests (anonymous AND authenticated-but-not-staff). Suite 601/0.

- [x] **Phase 9 — admin dashboard, all 7 routes verified LIVE (2026-07-26).**
      Ephemeral credential created → login **302 → dashboard 200** → destroyed → session dead (302).
      All 7 routes **200**: `/` (27.7KB) · `/explorer/` (33.7KB) · `/journey/17/` (13.6KB) ·
      `/referrers/` (7.8KB) · `/referrer/E2E0726/` (16.0KB) · `/preferences` (43.7KB) ·
      `/verifications/` (8.0KB).
      **PII:** names + client IDs render; **no phone or email digits anywhere** (the only digit runs
      on the page are the NSE AP reg number and a CSS id). Conservative DPDP posture.
      **Unique visitors IS labelled** — an `APPROX` badge sits beside the count. (My first grep looked
      for "approximate" and wrongly flagged it missing.)
      **No dead UI** — the single `disabled` hit is a JS click guard, not a rendered disabled button;
      all `placeholder` hits are ordinary input placeholders.
      **Referral vs partner-direct kept separate** in the explorer (`Referral link` ×17,
      `Partner-direct` present).
      **Preferences read path verified** — the screen renders the live cascade values exactly,
      including the OTP P0 fix (`gr_platform_gorefer_login_otp_en_2026_07_21`), all three integration
      flags correctly checked ON, and WATI business number `917080642020`.
      **Preferences WRITE deliberately NOT executed:** the form submits all 35 fields including
      `enable_wati_send` / `enable_zoho_write` / template names, and Django treats an omitted
      checkbox as OFF — a hand-built POST could disable a live integration or blank a template.
      The write path is already covered green by `test_qmpref_preferences.py` +
      `test_toggle_persists_through_the_screen`, so the risk was not worth the marginal coverage.
      Flagged for a real-browser run once the VPS Chrome session exists.

- [x] **Phase 6 — all five gates verified LIVE (2026-07-26).**
      **P1 DEFECT FOUND + FIXED: converted-suppression was silently dead in production.**
      `has_converted()` read only `Lead.status == "account_opened"`, but the Zoho ingest — the only
      path allowed to record a conversion — writes `Referral.conversion_status` and never advances
      `Lead.status`. Every prod Lead read `"new"`, so the gate always returned False and a customer
      who had ALREADY opened their account kept getting "your account is still pending" nudges for
      the full 21h cadence. Fixed to read the field Zoho actually maintains; verified live on a REAL
      cadence row: `cancelled / engaged: converted`.
      **Quiet hours OBSERVED, not asserted:** shifted the window to 16-18 IST, sweep returned
      `held=1`, row stayed `scheduled`, and `fire_at` moved 11:12Z -> 12:30Z = exactly 18:00 IST =
      `next_active_time()`. Config restored to (23,6) in a `finally`.
      **Bug found while doing it:** the hold reason hardcoded "06:00 IST" while actually deferring to
      the configured hour — a lie in the audit trail for any AP with a custom window. Fixed + test.
      **Anti-burst:** `within_min_gap` True and `compute_defer` satisfied BOTH constraints
      simultaneously (>= last_send + 90 min AND outside quiet hours).
      **Window closed** -> `skipped` with `failed == 0`. **7 distinct bodies** confirmed.
      **My own contamination, owned and reverted:** `stamp_inbound()` mutates the real window, so my
      scaffolding briefly made the gate see a reply that never happened; true `last_inbound_at`
      restored and the proof re-run. Rail added to the skill.
      Suite 599 passed / 0 failed. Deployed.

- [x] **Phase 5 — Zoho conversion ingest, verified live end to end (2026-07-26).**
      Negative cases all **401 with a flat, reason-free body** (no probing oracle):
      tampered signature · missing signature header · body swapped after signing ·
      stale timestamp (>300s). Positive: valid seal → **200 `applied:true`** (conversion 4);
      **replay of byte-identical ts+nonce+body → 401** (nonce burned); no-referrer payload →
      **200 but credited NOBODY** (`referrer_client_id=''`), i.e. it does not guess.
      **ADR-017 proven:** `account_opened_at` = 2026-05-13T18:30Z (the true date I sent, 14 May IST)
      while `synced_at` = 2026-07-26 — and the ingest marked **2026-05-14** dirty, so monthly
      `accounts_opened` reads May=3 / June=1 / **July=0**. Backdated conversions land in their real
      period; no fake import-day spike. Referral 17 updated: `conversion_status=account_opened`,
      `credited_referrer=E2E0726`, `conversion_source=zoho`.
      **Guardrail 2** is enforced by a static source scan (`test_conversion_status_only_written_by_zoho_ingest_path`
      + a meta-test proving the scanner catches a bulk-update bypass + `test_lead_capture_never_sets_account_opened`)
      — all green in the 596. No new regression tests needed: `tests/test_zoho_webhook_waxseal.py`
      already covers all 14 seal cases including the IP allowlist.
      **Chased and cleared:** conversion 3 (RJ4521, opened 18-Jul) is invisible in July analytics
      because `is_reversed=True` and the rollup correctly excludes reversed rows — system is right.
      Note `CURRENT-STATE` presents that row as a live ingest without saying it was later reversed.
      **CLEANUP OWED:** prod conversions **id 4 (`E2ECONV01`)** and **id 5 (`E2ECONV02`)**, plus
      referral 17's conversion fields. Zoho lead `475281000041836002` still outstanding too.

- [x] Guardrails 1/2-partial/3, `/r/{ch}/{id}`, `/open`, `/share`, bot suppression (Phase 1)
- [x] Capture loop → Wati template → Zoho lead write (Phase 4); lead `475281000041836002`
- [x] Session-cadence trigger: real inbound → poll opened window → 7 steps enqueued → 1 fired,
      **READ** at destination (Phase C/7)
- [x] All **8** GoRefer-owned templates swept EN+HI, terminal status read from Wati
- [x] **P0 fixed:** `otp_whatsapp_template` pointed at `gorefer_login_otp`, which never existed
      at Meta (HTTP 400) — every WhatsApp OTP silently degraded to `manual`
- [x] **Fixed:** `Referral.first_click_at` never written; stamped in `_record_event`, 16 rows
      backfilled (`4ab05b8`)
- [x] **Fixed:** `?s=wa` legacy link form in the referrer nudge → canonical `/r/wa/{id}` via
      `nudge_link_for()`, v5 templates approved + deployed, verified live (`8219e6d`)
- [x] Full suite **596 passed / 0 failed** (CI-parity env); the 31 "failures" were harness env
- [x] Template coverage matrix built and reconciled (46 live templates)
