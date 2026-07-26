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
> **Last updated:** 2026-07-26

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

- [ ] **Zoho conversion webhook (Phase 5) — highest value.** `POST /api/zoho/status-webhook`
      with a valid HMAC seal (`ZOHO_WEBHOOK_HMAC_SECRET`): conversion ingests, true Zoho
      opening date stored distinct from sync date (ADR-017), referrer credited by client_id,
      single-winner, no-referrer ⇒ credit nobody. Tampered/missing/replayed seal ⇒ rejected
      (replay must fail on the nonce). **Guardrail 2:** attempt an internal status write and
      assert refusal. Writes one real conversion — record its id for cleanup.
- [ ] **Follow-up engine remaining gates (Phase 6).** Quiet-hours deferral (see a real
      deferral, not just the gate), 90-min anti-burst, distinct per-step copy, converted-
      suppression, window-closed ⇒ `skipped` not `failed`.
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
- [ ] **Sync prod's `tests/` tree** — prod is missing **4** files (`test_followups.py`,
      `test_m_wati1_share_intent.py`, `test_recipient_identity.py`, `urls_share_intent.py` —
      the review found the earlier "3 files" count wrong). Prod correctness isn't affected,
      but anyone testing on the host gets a false green.
- [ ] **Fix `CURRENT-STATE.md` staleness** — it says the funnel-report template is PENDING at
      Meta; the live inventory says APPROVED.
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
- [ ] **Meta quality restriction on `917972672473`.** Diagnosed as per-recipient (v4 failed
      there while succeeding on the other number), not copy-related. Recovery is Meta-side
      ("retry in a few days") plus lowering marketing volume — not a code fix.

## DONE

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
