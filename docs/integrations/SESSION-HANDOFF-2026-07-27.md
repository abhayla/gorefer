# Session handoff — 2026-07-27 (E2E programme complete; 12 defects fixed)

> **Next session: read this, then `docs/integrations/E2E-TEST-QUEUE.md`.**
> Supersedes `SESSION-HANDOFF-2026-07-26.md`.

## State

`main` is current and prod matches it. Suite **699 passed / 0 failed** (CI-parity env).
Working branch for anything new: **`feature/gorefer-e2e-hardening`** (off `main`).

**Do NOT work on `auto/work-*` branches.** They bit three times this session — see "Process
hazards" below.

## The E2E programme is COMPLETE — 16 of 16 phases

Phases 0, 0b, 0c, 1–13 all covered, including 7 and 8 which an earlier note wrongly called
blocked (the VPS has no Chrome; the OWNER'S LOCAL PC does).

## Defects found and fixed this session

| # | Defect | Where |
|---|---|---|
| 1 | OTP always cascaded to `manual` — no login OTP had EVER been delivered over WhatsApp | `apps/otp/adapters.py` |
| 2 | **Guardrail 3** — partner code `ZMPHZC` shown to every logged-in referrer | `apps/accounts/selfview.py` |
| 3 | Crawler card `og:image` relative **and** 404 → every forwarded link previewed blank | `apps/referrals/og.py` |
| 4 | `/share` prefill carried **no disclosure**, and its copy was code not config | `apps/referrals/share_intent_service.py` |
| 5 | **P0-H** — `mark_dirty` used the UTC date, not IST → would misdate a month's conversions | `apps/integrations/zoho/ingest.py` |
| 6 | Reconciler reported `failed: 6` on **every** sweep — a permanent blind spot | `apps/integrations/zoho/reconcile.py` |
| 7 | **DPDP erasure did not exist** (specified, never built) | `apps/common/privacy.py` (new) |
| 8 | **12-month retention purge did not exist** | `purge_expired_pii` + daily schedule |
| 9 | Hindi cadence had **no Hindi** — `body_hi=""` on all 7 rules | `seed_followup_cadence.py` |
| 10 | Junk ids could become referrers (`TALK`, `ZMPHZC`, `ABHAY`) | `apps/referrals/validators.py` |
| 11 | D9 — referral link moved into a UTILITY-safe button (escapes Meta `131049` cap) | `apps/followups/tasks.py` |
| 12 | 16 commits **deployed to prod but merged nowhere** | PR #56 |

## Two findings that matter more than the fixes

**A test that does the work it verifies is worse than no test.**
`test_i3_visitor_pii_is_erasable` performed the erasure *itself* — set `raw_ip=None`, stamped
`erased_at`, saved, asserted they stuck. It proved the MODEL could hold an erased state while
nothing in the application could PRODUCE one. DPDP erasure was unimplemented for months behind
a green test. Rewritten to call the real service.

**Read the vendor's policy before declaring something impossible.**
Three WhatsApp templates were flipped UTILITY→MARKETING and I was about to record "intrinsically
marketing". The owner pushed back. Meta's published policy names the disqualifier outright
(retargeting / cross-sell); v7 passed first try after reading it.
See `docs/integrations/Meta-Template-Categorization-Policy.md`.

## Process hazards — read before trusting any test run

- **Auto-checkpoint branches split work.** They moved HEAD mid-session twice, once separating a
  change from its tests (auto-PR #54 merged the client-ID validator with no tests). Symptom was
  the suite total DROPPING 680 → 646 — **a falling test count means the tree changed, not that
  code broke.** Chasing the individual failures would have "fixed" tests against absent code.
- **A merged PR does not reopen for new pushes.** PR #53 merged an early branch state; 16 later
  commits were deployed but merged nowhere. **Verify `main` matches prod by hashing, not by
  trusting `DEPLOYED_SHA`.**
- **Never hide sync stderr.** `tar ... 2>/dev/null` on the VPS sync would mask a stale-tree run.
- **Never reuse a script containing a DELETE for a create-only task.** That is how the Round-1
  templates were destroyed; Meta holds a deleted name ~30 days.

## Outstanding

**Owner decisions (2):**
- **Opt-out (`STOP`)** — the last untested gate. Deliberately NOT tested: it is a one-way door
  on a live number with no re-subscribe path. Recorded as **REQ-F02** (spec §12.8). Owner said
  **record, do not build**.
- **EN nudge label** — `v9a` "Share Referral Link" is live; `v9b`/`v9d`/`v9e` are approved
  UTILITY alternates kept for a one-line switch. Delete them once the label is confirmed.

**Blocked on a permission (1):**
- **4 Zoho test Leads** — `475281000041836002`, `475281000041538002`, `475281000041592002`,
  `475281000030612001`. Deletion is blocked by a safety classifier; the owner must remove them
  (recoverable from Zoho's Recycle Bin regardless). All confirmed test records:
  `@example.invalid` emails, names like "E2e Test 26jul Delete", referrer `E2E0726`.

**Parked deliberately (3):**
- **P0-A / P0-G** — point the Zoho trigger at Contacts. No longer urgent: the reconciler now
  catches every opening within 15 min. Needs the Zoho UI, or the
  `ZohoCRM.settings.automation.ALL` scope added to the refresh token (today's token has only
  `ZohoCRM.modules.ALL`). **Note: a plain Zoho webhook cannot compute our HMAC seal — a Deluge
  function is required either way.**
- **D3** — webhook IP allowlist. Still premature; arming a second lock on a door that has never
  been used only adds a silent-failure mode.
- **Partner hierarchy** (Category → Group → Partner → Member). Recorded in the queue with the
  crux: **the model is inverted** — code calls PIFS the Partner and Zerodha the Program. That
  already produced debt (the client-ID pattern is keyed under PIFS though the rule is Zerodha's).
  Wants an ADR before code.

**Outside this repo (1):**
- **24 Zoho/Wati journey templates** — driven by Zoho Deluge functions and Wati flows. A
  GoRefer-only run cannot reach them; never counted as covered.

**Verified only at rest (2):**
- The Wati welcome-flow card (needs a trigger inside 9–19 IST) and the off-hours reply (needs a
  fresh conversation session).

## Cleanup done this session

Soft-deleted (reversible, rows retained — D7 pattern): `E2E0726`, `FCLIVE01`, `REVW2607`,
`PRODWA01`, plus `ABHAY` and `E2EBOTVERIFY` (junk my own probes created). **All 14 real
identities verified intact afterwards.** Conversions 4/5 were already reversed, so they were
already out of analytics — nothing owed there.

**Left alone deliberately:** conversions 1/2 (`ZA9001`/`ZA9002`) are pre-existing `seed_demo`
rows dated May/June. They inflate those months but predate this session, and removing them is a
data decision rather than cleanup.

## Facts that cost time (do not re-derive)

- SSH: `ssh -i ~/.ssh/firekaro_v6_vps root@72.61.240.224` — bare `ssh` fails.
- **Never read `.env` for flag state** — prod `.env` says false while DB overrides are ON. Use
  `apps.config.integration_flags.resolve_flag()`.
- Server is **UTC**; `next_run` looks "overdue" against IST wall-clock. It isn't.
- **Wati:** `ok:true` on template create says NOTHING about the button — read
  `buttonParamMapping` back. Positional body params make Wati silently rewrite a button's
  `{{client_id}}` to `{{1}}` (the recipient's NAME). `buttonsType` is required alongside
  `buttons`. **10 template submissions per hour.** A PENDING template's category is not a
  predictor — only APPROVED counts.
- **`/r/wa/{id}` vs `/share/wa/{id}`:** the first 302s to Zerodha SIGNUP (right for body text a
  referrer copies, WRONG for a button he taps); the second opens WhatsApp's share sheet.
- **Phases 7/8 need the LOCAL PC, not the VPS** — the VPS has no Chrome. Local Chrome has a live
  WhatsApp Web session (logged in as `+91 77670 09136`) and Google sessions.
