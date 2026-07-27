# Session handoff — 2026-07-27 (D8 closed, D9 shipped, 6 defects fixed)

> **Next session: read this, then `docs/integrations/E2E-TEST-QUEUE.md`.** Supersedes
> `SESSION-HANDOFF-2026-07-26.md` (whose "17 commits ahead — unpushed" line was already stale).

## FIRST THING — one step is owed and it needs the owner's phone

**The D9 live verified send.** Everything is coded, tested, deployed and wired, but the
delivered message has never been seen. Deferred deliberately: it was ~01:00 IST and the
follow-up engine enforces quiet hours 23:00–06:00 precisely so we do not message people at
night.

**In working hours (9–19 IST):** trigger a referrer nudge to `917767009136` and confirm the
button resolves to **`gorefer.in/share/wa/DA1707`** — **not to a name**.

**Why this is required, not ceremony.** D9 moved the referral link into a template URL button,
so the URL SHAPE lives in the template where code cannot assert it — exactly what the earlier
`?s=wa` fix had removed. A near-miss proves the risk: submitting with positional params made
Wati silently bind the button to `{{1}}`, the referrer's NAME, which would have rendered
`gorefer.in/share/wa/Ramesh Kumar` on every send. Only reading the delivered message catches
that class of fault.

## State

Branch `fix/d8-otp-delivery-race`, PR **#53** open, CI green. Suite **643 passed / 0 failed**
(CI-parity env). Prod `DEPLOYED_SHA=c62c581`; all seven changed files hash-match local.

## Done this session

| # | Item | Outcome |
|---|---|---|
| D8 | WhatsApp-OTP login | **verified live end to end** — challenge `channel=whatsapp_wati`, delivered + READ, verify → session, replay → 400, logout clean, ADR-035 holds. Google OAuth still **UNTESTED** |
| D9 | Re-cut nudge as UTILITY | **shipped** — EN `v9a` (button), HI `v10` (no button), both APPROVED UTILITY, uncapped |
| P0-D | False "Zoho ingesting" claim | corrected in `CURRENT-STATE.md` |
| P0-H | Month-boundary rollup | reported bug was a false alarm; a **real** latent trap found + fixed |
| — | Guardrail-3 leak on `/my/referrals` | partner code `ZMPHZC` was shown to every logged-in referrer — fixed |
| — | Crawler card `og:image` | was relative AND 404 — every forwarded link previewed with no image; fixed |
| — | `/share` prefill compliance | had no disclosure line; now appended by the builder + cascade-driven |
| — | ADR-026 shared-template sweep | audited; no further leaks; whole-context regression test added |

## The D9 finding, in one table

Body held byte-identical, button the only variable, all APPROVED:

| Button label | EN | HI |
|---|---|---|
| Share Referral Link · My Referral Link · Share on WhatsApp · Refer | **UTILITY** | MARKETING |
| Refer & Earn | MARKETING | MARKETING |
| *(no button)* | pending | **UTILITY** |

1. A referral **share** button holds UTILITY in English.
2. **"Earn" is the one fatal word** — the only variant to flip in both languages.
3. **Hindi rejects the button itself** — four labels flipped, including one with no referral or
   reward wording at all, while Hindi without a button is UTILITY. Do not spend more
   submissions hunting a Hindi label; that question is closed.

## Facts that cost time (do not re-derive)

- **Meta policy is the authority, not the pattern of failures.** Three attempts were flipped
  before anyone read the actual rule. `docs/integrations/Meta-Template-Categorization-Policy.md`
  now holds the two-part test, the worked examples, and an authoring checklist. Read it before
  touching a template.
- **`ok:true` on template create proves nothing about the button.** Read `buttonParamMapping`
  back. Positional body params make Wati rewrite `{{client_id}}` → `{{1}}`.
- **`buttonsType` is required** alongside `buttons` (`call_to_action`), or create is rejected —
  nothing is created, so it costs no submission.
- **Wati allows 10 template submissions per HOUR.** Budget label experiments accordingly.
- **A pending template's category is NOT a predictor** — identical designs showed opposite
  pending categories per language, then settled differently again. Only APPROVED counts.
- **`/r/wa/{id}` vs `/share/wa/{id}`:** the first 302s to Zerodha SIGNUP (right for body text a
  referrer copies, WRONG for a button he taps — he already has an account); the second opens
  WhatsApp's contact picker. Owner phone-tested the second.
- The 2026-07-26 handoff's "17 commits ahead — unpushed" was false, and prod's `DEPLOYED_SHA`
  was stale while prod CONTENT matched `main`. **Verify deploys by hashing, not by the marker.**
- Server is UTC; `next_run` on schedules looks "overdue" if compared against IST wall-clock. It
  isn't. The qcluster is healthy.

## Mistake made, recorded so it isn't repeated

**I deleted the Round-1 templates (v8c/v8d) by accident.** A create-only run was built by
`sed`-transforming a previous script that still contained a DELETE block; the transform failed
silently while the following commands ran anyway. Meta holds a deleted name ~30 days. Nothing
production broke, and the deleted design turned out to be the wrong one — but the rule is:
**never reuse a script containing a destructive block, and grep-verify the artifact before
running it.** Subsequent scripts were written from scratch and checked for destructive verbs
first.

## Pending, in priority order

1. **The D9 live send** (above) — needs working hours.
2. **P0-A / P0-G — point the Zoho trigger at Contacts.** *The most valuable open item.* Until
   it lands, no real conversion reaches GoRefer; July is right only because it was backfilled by
   hand. Workflow rules are not in the CRM REST API → needs the **Zoho UI**. P0-G: the trigger
   must filter to Zerodha/PIFS accounts (`AACK095261` is an AngelOne account in the same module).
3. **D3 — Zoho webhook IP allowlist.** Deliberately not started: arming a second lock on a door
   that has never been used adds a silent-failure mode. Do after P0-A, against IPs actually seen.
4. **Confirm the EN label** — three others also hold UTILITY; `v9a` was chosen as the owner's
   original wording.
5. **Delete losing variants** (v9b/v9c/v9d/v9e, v6) once the winner is proven live.
6. **Remaining phases:** 11 (landing page — needs a temporary `set_landing_mode page` flip,
   revert after), 12 (Hindi / DPDP / erasure / rollups / cross-tenant), and the 24 Zoho-Wati
   journey templates (owned outside this repo).
7. **Two Wati flow fixes still verified only at rest** — the welcome-flow card needs a trigger
   inside 9–19 IST; the off-hours reply needs a fresh conversation session.
8. **`v7 en` has been PENDING at Meta for many hours** while everything else approved in
   minutes. Worth a look; English does not depend on it (v9a is approved).

## Cleanup owed in prod

Test identities `E2E0726`, `FCLIVE01`, `REVW2607`; conversions id 4/5; Zoho lead
`475281000041836002`; Lead 10 + Zoho lead `475281000030612001`. **Owner has not approved
deleting any of these — ask, do not assume.**
