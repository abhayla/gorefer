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
> **Last updated:** 2026-07-26 (Phase 5 complete)

## Rails (apply to every iteration)

- WhatsApp sends: **only** `917972672473` / `917767009136`. Never any other number.
- `917972672473` is currently Meta **quality-restricted** for MARKETING — use `917767009136`
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
- [ ] **Follow-up engine remaining gates (Phase 6).** Full gate order + per-gate test method now
      documented in the skill. Live config verified: quiet **23:00–06:00 IST**, min-gap **90 min**,
      all 7 rules `stop_on_reply=True` / `only_if_window_open=True` / session channel.
      To cover: (a) **quiet-hours deferral OBSERVED** — temporarily shift the quiet window so "now"
      is inside it, assert `held=1` + row stays `scheduled` + `fire_at` moves to
      `next_active_time()`, then **RESTORE both config values in the same session**;
      (b) **90-min anti-burst**, incl. `compute_defer` satisfying quiet-hours AND the gap together,
      not just one; (c) **converted-suppression** — mark converted ONLY via the sealed Zoho webhook
      (guardrail 2 forbids a direct write), assert `CANCEL engaged: converted`;
      (d) **window closed** ⇒ `SKIP` with `failed == 0`; (e) **7 distinct bodies** (copy is read at
      fire time). `stop_on_reply` + opt-out stay BLOCKED — they need a real inbound (Phase 7),
      and hand-stamping `last_inbound_at` proves the comparison, not the behaviour.
- [ ] **Admin dashboard routes (Phase 9).** Log in with `E2E_ADMIN_USER`/`E2E_ADMIN_PASSWORD`
      (already verified working), then exercise `/`, `/explorer/`, `/journey/{id}/`,
      `/referrers/`, `/referrer/{id}/`, `/preferences`, `/verifications/`. Assert PII masked,
      unique counts labelled approximate, no dead UI (Constitution §4).
- [ ] **API surface (Phase 10).** `/api/analytics/{funnel,journey,sync-health}`,
      `/api/share/`, `/api/click/confirm` (nonce; 401 on forged/expired/used),
      `/api/click/referrer/{id}` (401 without fresh nonce), `/api/health`. **Assert
      `/api/wati/webhook` is CLOSED (401)** — it had a fail-open bug once.
- [ ] **`POST /api/leads/` over HTTP (Phase 3).** `golive_smoke` bypasses HTTP validation,
      consent enforcement and rate limiting — test those directly, and assert no PII in `Event`.
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

## BLOCKED — needs Abhay (loop must skip, not stall)

- [ ] **M13 login (Phase 8).** OTP half needs a logged-in **WhatsApp Web** session on the VPS
      to read the code; Google OAuth half needs an authenticated **Google** session in that same
      browser. Both offered, neither set up yet.
- [ ] **Junk identities `TALK` and `ZMPHZC`** in prod, created by the (since-fixed) malformed
      chatbot link `/r/wa/Talk to advisor`. Soft-delete is reversible but it is still prod data
      — needs an explicit go.
- [ ] **9 approved-but-unwired templates** — wire or delete? Product decision.
- [ ] **`/open` destination.** Live sends `signup.zerodha.com/api/lead/?c=ZMPHZC`; `CLAUDE.md`
      specifies `signup.zerodha.com/?c=ZMPHZC`. No `r=` either way. Which is intended?
- [ ] **M11 OG preview vs bot 302.** Crawlers get a 302 to Zerodha, so WhatsApp would render
      *Zerodha's* card, not PIFS's — yet M11 claims forwarded links render a PIFS card.
      Contradiction to resolve.
- [ ] **DA DECISION: converted-suppression is coupled to `stop_on_reply`.** In
      `services.evaluate_gate`, the `has_converted` check (#5) sits INSIDE the `rule.stop_on_reply`
      branch. All 7 live rules have it True, so suppression is active today and there is no live
      defect — but a rule created via the CRUD API with `stop_on_reply=False` would keep nudging
      someone who has **already opened their account**. Two unrelated concerns share one switch.
      Surfaced for the DA rather than silently re-wired (CLAUDE.md §3).
- [ ] **SECURITY: the Zoho webhook IP allowlist is effectively DISABLED in production.**
      `ZOHO_WEBHOOK_IP_ALLOWLIST=''` and `WEBHOOK_REQUIRE_IP_ALLOWLIST=False` with `DEBUG=False`,
      so `_ip_allowed()` falls through to allow-any. The code's own comment says an empty allowlist
      in production is meant to fail closed, and `CURRENT-STATE` describes the posture as
      "HMAC + the same IP allowlist" — neither is true today. **Impact: defence-in-depth is one
      layer, not two.** Forgery still needs the HMAC secret (verified: I could not forge without
      it), so this is not an open door — but a leaked secret would have nothing behind it.
      **Not fixed unilaterally:** populating the allowlist with the wrong IPs would silently stop
      real conversion ingestion. Needs Zoho's current outbound IP ranges from the owner, then set
      both settings together and re-verify a live conversion arrives.
- [ ] **Meta quality restriction on `917972672473`.** Diagnosed as per-recipient (v4 failed
      there while succeeding on the other number), not copy-related. Recovery is Meta-side
      ("retry in a few days") plus lowering marketing volume — not a code fix.

## DONE

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
