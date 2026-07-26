# Session handoff — 2026-07-26 (live E2E testing + fixes)

> **Next session: read this, then `docs/integrations/E2E-TEST-QUEUE.md`, then continue.**
> The queue is the durable worklist. This file is the "what just happened / what you were
> mid-way through" that the queue alone does not carry.

## STOP — you are mid-task. Finish this first.

**D8, WhatsApp-OTP login.** Uncommitted right now:

```
 M apps/otp/adapters.py      # the fix
 M tests/test_qmotp.py       # 2 new tests, BOTH FAILING, not yet diagnosed
```

**What was found (verified on prod):** `WatiWhatsAppOtpAdapter.send()` sends the template, then
**immediately** demands terminal `DELIVERED` status in the same request. WhatsApp delivery takes
seconds, so the check always failed and the WhatsApp channel **always** cascaded to `manual`.
Proof: `OtpChallenge` **id=1** was the first challenge ever recorded on prod, and it had already
fallen back to `manual` (`delivery_status='queued'`, `provider_ref='manual-assisted'`). **No login
OTP has ever actually been delivered over WhatsApp.** This is a second, independent break on the
same path as the template-name P0 fixed earlier the same day.

**The fix applied (uncommitted):** not-yet-terminal ⇒ `STATUS_QUEUED` (accepted, unproven, stops
the cascade); terminal-and-delivered ⇒ `STATUS_DELIVERED`; terminal-but-failed ⇒ `STATUS_FAILED`
(a real rejection, cascade is correct). `STATUS_QUEUED` already sits in the service's
cascade-stopping set, so no service change is needed.

**Next actions, in order:**
1. Diagnose the 2 failing tests — they were written blind against `SendResult` /
   `get_message_status` and the constructor or return shape is probably wrong. Run:
   `pytest tests/test_qmotp.py::test_whatsapp_otp_not_yet_delivered_is_QUEUED_not_a_failure -q`
2. Full suite green (CI-parity env — see the skill; the prod host needs prod `.env` neutralised
   or you chase 31 phantom failures).
3. Deploy `apps/otp/adapters.py`, restart both services.
4. **Complete D8 with the owner present** — he is willing to read the 6-digit code off his phone
   (WhatsApp hides OTPs from linked devices, so this CANNOT be automated). Flow:
   - `POST /login/otp/request` with `client_id=DA1707` (that id resolves on-file to
     `917767009136`; `EKU497` resolves to a real customer's number — do not use it).
   - Owner pastes the code → `POST /login/otp/verify` → assert session + `/my/referrals`.
   - Already verified: supplying `mobile=` in the request is **refused 400** (ADR-035 — the
     recipient is never user-supplied). Keep that assertion.
5. Google OAuth stays **UNTESTED** — owner chose WhatsApp-only (D8). Keep reporting it as untested;
   it is the PRIMARY referrer login.

## Then, in priority order

- **D9 — cut marketing volume, re-cut nudges as UTILITY.** Biggest delivery win. UTILITY escapes
  Meta's `131049` per-user cap, the dominant cause of the ~43% delivery rate. Reframe copy as
  transactional ("your account is still pending") not re-solicitation ("still want to open one?")
  — proven to flip Meta's classification on this tenant. **Template change ⇒ HTML map FIRST**
  (`CLAUDE.md` §6c), then Meta, then map again.
- **P0-A — point the Zoho trigger at Contacts.** Not urgent: the reconciler now delivers within
  15 min regardless. Needs the Zoho UI (workflow rules are not in the CRM REST API).
- **P0-H — month-boundary rollup bug.** `account_opened_at` is stored IST-midnight-in-UTC
  (`18:30` previous day) while `_accounts_opened_for_range` compares NAIVE datetimes, so an
  account opened on the **1st of a month IST** would be counted in the **previous** month. No live
  error today (none of the 6 falls on a 1st) — it will misdate silently the first time one does.
- **Verify the two Wati fixes actually DELIVER** (both verified at rest only):
  - the welcome-flow card — needs a trigger **inside business hours 9–19 IST**;
  - the off-hours reply — needs a **fresh conversation session** (`sendOutOfOfficeMessageAlways`
    is false, so it fires once per session).
- **Remaining test phases:** Phase 2 (6 more crawler UAs), Phase 11 (landing page — needs a
  temporary `set_landing_mode page` flip, revert after), Phase 12 (Hindi / DPDP / rollups /
  cross-tenant), and the **24 Zoho/Wati journey templates** (owned outside this repo).
- **Cleanup owed:** test identities still live in prod — `E2E0726`, `FCLIVE01`, `REVW2607` (and
  the earlier Zoho test lead `475281000041836002`). Owner has NOT approved deleting these; ask.

## What was fixed today (all deployed unless noted)

| # | Defect | Status |
|---|---|---|
| 1 | `otp_whatsapp_template` named `gorefer_login_otp`, which never existed at Meta → HTTP 400, silent degrade to `manual` | fixed |
| 2 | `Referral.first_click_at` never written | fixed + 16 rows backfilled |
| 3 | Converted customers still nudged (`has_converted` read `Lead.status`, which nothing writes) | fixed |
| 4 | `/api/analytics/*` publicly readable — full funnel + enumerable journeys | fixed (staff-gated) |
| 5 | A reversed conversion left the referrer still credited | fixed |
| 6 | `?s=wa` legacy link form in the referrer nudge → canonical `/r/wa/{id}` (v5 templates) | fixed |
| 7 | Dead CTA `gorefer.in/openOr` (404) — Wati flow serializer honours only literal `\n` | fixed, delivery unverified |
| 8 | **Conversion ingest inert** — GoRefer watched Zoho *Leads*, openings land in *Contacts* | reconciler shipped |
| 9 | OTP always cascaded to `manual` (delivery race) | **fix uncommitted, tests failing** |

Owner decisions D1–D7 all implemented; D8 in flight; D9 pending. `BLOCKED` is empty.

## Facts that cost time to learn (do not re-derive)

- SSH: `ssh -i ~/.ssh/firekaro_v6_vps root@72.61.240.224` — bare `ssh` fails with publickey.
- **Never read `.env` for flag state** — prod `.env` says `false` while DB overrides are ON. Use
  `apps.config.integration_flags.resolve_flag()`, and pass `tenant_id` when resolving template
  names or you read code defaults, not reality.
- Testing on the prod host requires neutralising prod `.env` (exact env block is in the skill,
  `Phase 13`) or you get 31 phantom failures. Sync the **repo**, not `/var/www/gorefer` — prod's
  `tests/` tree lags.
- Wati flow message bodies: line breaks come from **literal `\n`**, NOT from `<p>` tags.
  `</p><p>` renders as nothing and silently glues text together (that is how the dead CTA formed).
- Wati template `DELETE` returns `ok:true` but Meta holds the name ~30 days — pick a new name.
- Zoho: the live refresh token has **no COQL scope**; use `/crm/v8/Contacts/search`.
- `git status` on prod code is meaningless — deploys are file-copies. Verify by hashing against
  `origin/main`.

## Repo state

Branch `main`, **17 commits ahead of origin — unpushed.** Suite was **629 passed / 0 failed**
before the uncommitted D8 change. Skill: `.claude/skills/e2e-whatsapp-communication/`
(16 phases + `check-prereqs.sh` + `phase9-admin.sh`, which creates/destroys an ephemeral prod
admin — there is deliberately no standing prod password).
