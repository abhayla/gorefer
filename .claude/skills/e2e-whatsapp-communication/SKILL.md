---
name: e2e-whatsapp-communication
description: Test the live GoRefer site end to end against real production — click a referral link and check the record was created, send a WhatsApp message and check it actually went out, drive the Wati chatbot/keyword estate as a real contact (buttons, question-node validators, flow kits), run the follow-up nudge cadence, ingest a Zoho conversion, log into the admin dashboard, test referrer login, and check the safety guardrails hold. Use when asked to "test end to end", "run the E2E", "test everything", "verify prod", "full round of testing", or after any deploy touching redirect / Wati / Zoho / followups / login / chatbot flows.
---

# GoRefer — full live end-to-end test

Tests the real production system at `gorefer.in`. Every leg is verified **at the destination**
(Wati's own record, the prod DB, the rendered page) — never at the point of dispatch.
`queued` / `accepted` / `202` are promises, not results.

**Pass bar for messages (owner-set 2026-07-26):** PASS at **`sent`**. Meta may block delivery
(per-user cap `131049` is common; delivery has run ~43%) — that is not a GoRefer defect.
`delivered` / `read` are bonus.

Use a fresh throwaway client id per run that FITS the partner id shape — the validator enforces the
per-partner pattern (`client_id_pattern__ZMPHZC`, 6 chars, e.g. `E2E999`/`E2E998`); the old
`E2E<DDMM>` 7-char convention is REJECTED with a branded 400 since 2026-07-27.
Sanctioned test recipients ONLY (`GLOBAL.env:WATI_TEST_RECIPIENTS`): `917972672473`, `917767009136`.

## STEP 0 — PREREQUISITE GATE (run FIRST, every time, before anything else)

```bash
bash .claude/skills/e2e-whatsapp-communication/check-prereqs.sh
```

**Report its output to the owner immediately — before running any phase.** Discovering a missing
credential halfway through wastes the run; the owner gets asked ONCE, up front, with the exact
list and what each item unlocks.

| Exit | Meaning | What to do |
|---|---|---|
| **0** | Fully autonomous | Run every phase unattended. |
| **1** | A HARD prerequisite is missing | **STOP.** Nothing can run. Tell the owner exactly which item and that the run cannot start without it. |
| **2** | Partial autonomy | Run every unblocked phase. **Do NOT stall** on the blocked ones — list them for the owner and carry on. Report at the end which phases were skipped and why. |

The gate distinguishes three kinds of prerequisite:
- **HARD** — VPS ssh, Wati endpoint + token, `gorefer.in` reachable. Without these there is no run.
- **PER-PHASE** — `ZOHO_WEBHOOK_HMAC_SECRET` (Phase 5), `ZOHO_REFRESH_TOKEN` (Phase 4),
  `phase9-admin.sh` (Phase 9), `WATI_TEST_RECIPIENTS` (all sends). Missing one blocks only its phase.
- **OWNER-PROVIDED SESSIONS** — a logged-in WhatsApp Web session and a Google session on the VPS
  Chrome. These **cannot be auto-provisioned** and a login cannot be proven from disk, so the gate
  looks for an explicit confirmation marker the owner creates after logging in:
  `/root/.gorefer-e2e/whatsapp-web.ok` and `/root/.gorefer-e2e/google-session.ok`.

**Decisions are also prerequisites, and the gate cannot detect them.** Check the BLOCKED section of
`docs/integrations/E2E-TEST-QUEUE.md` and surface any open owner decision in the same up-front
message (currently: `/open` destination path, M11 OG-card vs bot 302, wire-or-delete the 9 unwired
templates, cleanup of the junk `TALK`/`ZMPHZC` identities).

## Preflight (after the gate passes)

```bash
# SSH key is NOT id_rsa — bare `ssh root@...` fails with publickey
ssh -i ~/.ssh/firekaro_v6_vps root@72.61.240.224 "hostname; cat /var/www/gorefer/DEPLOYED_SHA; systemctl is-active gorefer gorefer-qcluster"

# Effective flags — NEVER read .env, it says false while DB overrides are ON
ssh -i ~/.ssh/firekaro_v6_vps root@72.61.240.224 'cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c "
from apps.config.integration_flags import resolve_flag
print([(f, resolve_flag(f)) for f in [\"ENABLE_WATI_SEND\",\"ENABLE_ZOHO_WRITE\",\"ENABLE_ZOHO_READ\"]])"'
```

Credentials: Phase 9's staff account is **ephemeral** — created on demand and destroyed after, so no
standing prod password exists anywhere (`CLAUDE.md` §4: never a seeded plaintext credential):
`bash .claude/skills/e2e-whatsapp-communication/phase9-admin.sh create|destroy|status`.

---

## Phase 0 — Reconcile the SSOT first (never skip; run BEFORE any send)

**The HTML conversation map is SSOT** (`CLAUDE.md` §6c, owner rule). Template changes go
**HTML → Meta submit → HTML again on approval.** Testing starts by proving the three views agree:

1. Pull the live Wati inventory (`wati_list_templates`, page_size 100 — **`page_number` is ignored**,
   100 is the whole set).
2. Resolve every template name **on prod with `tenant_id`** — without it you read code defaults, not
   reality, and they differ:
   ```
   notify_template_name(role, lang=lang, tenant_id=1)     # NOT tenant_id=None
   ConfigGlobal.objects.filter(key__contains="template")   # the overrides that actually win
   ```
3. Regenerate `docs/integrations/WhatsApp-Template-Coverage-Matrix.md` and diff it.
4. **Assert every configured template name EXISTS at Meta.** A name that resolves fine but doesn't
   exist fails at send time and may cascade silently to a fallback channel. Cheap direct probe:
   ```
   get_wati_adapter().send_template(to=<test#>, template=<name>, params={...})  # accepted False + http=400 ⇒ name is bogus
   ```
5. Any disagreement (map card vs Meta status vs prod config) is a **defect** — fix it in the same
   turn, then update the HTML map.

## Phase 0b — Template sweep: every template, every scenario

"End to end" means no scenario and no template is missed. Drive the matrix, not just the happy path.

- **GoRefer-owned (8):** trigger each through its real code path — office alert, prospect welcome
  EN+HI, referrer update EN+HI, login OTP, §6.1 referrer nudge EN+HI. Assert **terminal** status per
  template. Force `pref_lang='hi'` to reach the Hindi half; nothing in the default path does.
- **Reports (2):** delivery + funnel report at 21:30 IST.
- **Wati broadcast (3) and Zoho/Wati journey (24):** owned outside this repo — cover by driving the
  Wati flow / Zoho journey directly. A GoRefer-only run **cannot** cover these; say so explicitly
  rather than implying full coverage.
- **Unwired (9):** do not send. Report them for wire-or-delete — an approved template nobody sends is
  a liability, not coverage.
- **Capacity reality:** sending dozens of MARKETING templates to one number will trip Meta
  `131049` (per-user cap). Spread across both sanctioned numbers, prefer UTILITY variants, and treat
  a cap rejection as a **recorded outcome**, not a GoRefer failure — the pass bar is `sent`.

## Phase 0c — Read the delivered message and TEST EVERY LINK IN IT (owner rule 2026-07-26)

A template that reaches `sent` is only half-verified. **The message body is a deliverable**: its
links must resolve and its data must be right. Read what actually arrived (Wati `getMessages`, or
the conversation in WhatsApp Web) and check both.

**Every link, clicked.** Extract each URL from the delivered body and follow it:

| Link | Expect |
|---|---|
| `gorefer.in/r/wa/{id}` | 302 → `signup.zerodha.com/api/lead/?c=ZMPHZC&r={id}` |
| `gorefer.in/r/{id}?s=wa` | 302, same destination (legacy form still supported) |
| `gorefer.in/open` | 302 with **no `r=`** |
| `gorefer.in/d/pifs` | 200 |

**Extract the URL exactly as the CLIENT linkifies it, not as the copy intended.** WhatsApp
auto-links a bare domain and swallows anything up to the next whitespace — so a missing space
silently corrupts the URL. Found live 2026-07-26: the Wati welcome flow read
`…here: gorefer.in/openOr reply Call me…` with no separator, WhatsApp linkified
**`gorefer.in/openOr`**, and that **404s** — a dead CTA on the primary account-opening path.
Confirm the anchor boundary visually (the link is underlined) or read the `href`; do not assume
the copy's intent.

**Data correctness in the body — verify, don't skim:**
- Every `{{n}}` substituted; **no blank variable** and no leftover placeholder.
- Names/ids match the source record; an unknown name falls back to a generic descriptor
  (`"A friend referred you"`, `"one of your recent referrals"`) rather than rendering empty.
- The **compliance block is present**: market-risk sentence + `Disclosures: https://gorefer.in/d/pifs`
  (+ the `PIFS · Zerodha Authorised Person` footer where the template carries one).
- **No partner code and no raw Zerodha URL** anywhere in the body (guardrail 3).
- Contact numbers are consistent across templates. *Open nit found 2026-07-26:* the helpline appears
  as `+91 73888 82020` in one template and `7388882020` in another — same number, two formats.
- Hindi bodies render real Devanagari with variables substituted, not mojibake.

**Constraint discovered 2026-07-26 — OTP codes are INVISIBLE on linked devices.** WhatsApp shows
*"You received a one-time passcode. For added security, you can only see it on your primary device"*
for AUTHENTICATION-category templates. So WhatsApp Web **cannot** read a login OTP, and Phase 8's
OTP half still needs the owner to read the code off their phone. Do not plan around automating it.

## Phase 1 — Redirect, share, guardrails

```bash
ID=E2E<DDMM>
curl -s -o /dev/null -w "1a %{http_code} %{redirect_url}\n" -A "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile" "https://gorefer.in/r/wa/$ID"
curl -s -o /dev/null -w "1b %{http_code} %{redirect_url}\n" -A "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile" "https://gorefer.in/open"
curl -s -o /dev/null -w "1c %{http_code} %{redirect_url}\n" -A "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile" "https://gorefer.in/share/wa/$ID"
for p in "/" "/d/pifs"; do curl -s "https://gorefer.in$p" | grep -c 'ZMPHZC\|signup.zerodha.com'; done   # must be 0
```

- **1a** 302 → `signup.zerodha.com/api/lead/?c=ZMPHZC&r={ID}`; identity + `click` event created.
- **1b** 302 with **no `r=`**; `Referral` with `source=partner_direct`, `referral_identity=None` (ADR-015).
- **1c** 302 → `wa.me`; `share_intent` event, `source='wati'`.
- **1d** guardrail 3: zero `ZMPHZC` / raw Zerodha URL in client-facing HTML.
- **1e** guardrail 1: redirect service never POSTs to Zerodha — assert via `tests/test_guardrails.py`.

## Phase 2 — Bot filter breadth (all crawlers, not just two)

```bash
for UA in "facebookexternalhit/1.1" "WhatsApp/2.23.20.0" "Telegrambot (like TwitterBot)" \
          "Slackbot-LinkExpanding 1.0" "Twitterbot/1.0" "LinkedInBot/1.0" \
          "Googlebot/2.1" "Mozilla/5.0 (compatible; bingbot/2.0)"; do
  curl -s -o /dev/null -A "$UA" "https://gorefer.in/r/wa/E2EBOT$RANDOM"
done
```
Use VALID-shaped ids (e.g. `QQ7001`…`QQ7008`, one per UA) — invalid-shaped ids 400 on the validator
and mask the bot filter. Crawlers receive **200 + the PIFS OG preview card** (M11, config-driven
copy) — not a 302 — and **no** `ReferralIdentity` may be created. (Resolved 2026-08-01: open
question 1 — bots get the card, humans get the redirect.)

## Phase 3 — Lead capture over HTTP (not the service layer)

`golive_smoke` (Phase 4) calls the service layer directly and therefore **bypasses HTTP validation,
consent enforcement, and rate limiting**. Test the real endpoint separately:

- `POST /api/leads/` valid payload → 201, `Lead` + `lead_captured` event.
- Missing/false consent → rejected (DPDP: consent required on the form).
- Malformed / oversized / illegal-char `client_id` → rejected by `validators.py`.
- Hammer past the limit → rate limiter trips (`apps/common/ratelimit.py`, DB-cache-backed so
  counters are shared across gunicorn workers). Verified 2026-08-01: 429 from request #11.
- Same-mobile re-submissions DEDUPE: 201 returns the EXISTING lead (id echoed in the response),
  touching nothing — repeat runs on the sanctioned numbers exercise the dedup path, not create.
- PROD RUNS `WATI_ALLOW_ALL_RECIPIENTS=true` by necessity — the fail-closed allowlist rail is NOT
  testable on prod (suite covers it); never fire negative-send probes at non-sanctioned numbers.
- Assert **no PII** (name/mobile/email) reached the `Event` table (Round-2 amendment #16).
- Phone normalized one canonical way (strip spaces/`+`/`()`/`-`, prefix `91`).

## Phase 4 — Capture loop → Wati template → Zoho lead write

```bash
ssh -i ~/.ssh/firekaro_v6_vps root@72.61.240.224 'cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py golive_smoke \
  --referrer E2E<DDMM> --mobile 7767009136 --name "E2E TEST <DDMon> DELETE" --email e2e-<date>@example.invalid --json'
```

Writes a **real Lead into Zoho CRM** (the source of truth) → owner approval each run; record the
returned `zoho_lead_id` for deletion.

Poll to terminal — `wati_reconcile_pending` runs **every 15 min**, so wait for it before calling
`accepted` a bug:
```
Notification.objects.filter(referral_id=<id>).values_list("recipient_role","status","meta_error_code","failure_classification")
```
PASS when office + prospect reach `sent`/`delivered`/`read`. `referrer` legitimately `skipped` when
no phone is on file. Cross-check destination via Wati MCP `wati_get_messages` → `statusString`.
Assert the compliance block + market-risk warning appear in the delivered body.

## Phase 5 — Zoho conversion ingest (the money leg, guardrail 2)

The only path allowed to write account status. Craft an HMAC-sealed webhook using
`ZOHO_WEBHOOK_HMAC_SECRET` from `GLOBAL.env` (`ENABLE_ZOHO_WEBHOOK_HMAC` is ON):

- Valid seal → `POST /api/zoho/status-webhook` ingests; `conversion_status` set, **true Zoho
  account-opening date** stored distinct from the sync date (ADR-017).
- **Tampered / missing / replayed seal → rejected.** Replay must fail on the nonce.
- Referrer credited **by Zerodha client id**, single-winner. No referrer in payload ⇒ credit nobody
  (no last-click fallback).
- Off-platform conversion (no prior click) still ingests — a converted journey may have zero clicks.
- **Guardrail 2:** attempt an internal status write and assert it is refused.
- Writes a real conversion → owner approval.

## Phase 6 — Follow-up engine, all gates

**Why this phase is not optional.** All of this logic passes unit tests, but unit tests use fake
clocks. Nobody had confirmed that on the real server, at real IST times, a night nudge actually
waits until morning and then spaces itself. The owner already caught a live duplicate-burst at
06:03 on 2026-07-25, which is precisely why the min-gap exists — so "the tests pass" is not
evidence here.

### The gate, in the exact order the code runs it

`services.evaluate_gate(sf, now)` — pure, no side effects. First match wins:

| # | Check | Outcome | Notes |
|---|---|---|---|
| 1 | `followups_enabled(tenant)` false | **CANCEL** | flag flipped off after scheduling kills pending rows |
| 2 | `rule.enabled` false | **CANCEL** | |
| 3 | `is_opted_out(tenant, mobile)` | **CANCEL** | |
| 4 | replied since this window opened | **CANCEL** `engaged: replied` | only if `rule.stop_on_reply` |
| 5 | `has_converted(tenant, mobile)` | **CANCEL** `engaged: converted` | **also only if `rule.stop_on_reply`** — see caveat |
| 6 | window state | SEND_SESSION / SEND_TEMPLATE / **SKIP** | closed + `only_if_window_open` ⇒ `SKIP`, never a failed send |
| 7 | `in_quiet_hours(now)` | **HOLD** `quiet hours — deferred to 06:00 IST` | only applies to a would-be SEND |
| 8 | `within_min_gap(...)` | **HOLD** `min-gap — spacing sends to avoid a burst` | only applies to a would-be SEND |

**HOLD ≠ CANCEL.** A held row stays `scheduled` and `fire_at` is recomputed by
`services.compute_defer()`, which returns the earliest instant satisfying **both** quiet hours and
the min-gap. That single function is what stops several night-deferred steps collapsing onto one
06:00 slot.

**Live config (verified 2026-07-26, tenant 1):**
`followup_quiet_start_hour=23` · `followup_quiet_end_hour=6` (IST) · `followup_min_gap_minutes=90`
· `followup_referrer_nudge_step=nudge_12h`. All 7 seeded rules: `enabled=True`,
`stop_on_reply=True`, `only_if_window_open=True`, `channel=session`.

**CAVEAT worth a decision.** Converted-suppression (#5) is nested *inside* the `stop_on_reply`
branch. Today all 7 rules have `stop_on_reply=True` so it is active — but a rule created through the
CRUD API with `stop_on_reply=False` would keep nudging someone who has **already opened their
account**. Coupling two unrelated concerns; flag to the DA rather than silently re-wire it.

### How to test each gate honestly

**Scaffolding can contaminate live data — check before you reach for a helper.** `services.stamp_inbound()` MUTATES the real `FollowupWindow.last_inbound_at`. Calling it to open a window for a test made the gate see a reply that never happened, so a genuinely-converted contact cancelled with `engaged: replied` instead of `engaged: converted` (2026-07-26). Record the true `last_inbound_at` first and restore it, or scaffold on a mobile with no real cadence. Prefer proving a gate on a REAL queued row over a synthetic one — a synthetic row can pass for the wrong reason.

**Quiet hours — the one that must not be faked.** Do NOT assert on `in_quiet_hours()` alone; that
only proves the predicate. Observe a real deferral:

1. Record the current values, then temporarily shift the window so "now" falls inside it — e.g. at
   16:00 IST set `followup_quiet_start_hour=15`, `followup_quiet_end_hour=17`.
2. Make one step due (`fire_at = now`) and run `fire_due_followups()`.
3. Assert: `counts["held"] == 1`, row still `scheduled`, `reason` mentions quiet hours, and
   `fire_at` has moved to `services.next_active_time(now)` — the configured end hour in IST.
4. **RESTORE both config values in the same session**, then re-assert `in_quiet_hours()` is False.

Shifting the *window* is legitimate — the clock, the sweep and the send path are all real, only the
boundary moves. Leaving it shifted would suppress real nudges, so restoring is mandatory, including
on failure.

**Anti-burst (90 min).** Send one nudge, then make a second step due immediately. Assert **HOLD**
with the min-gap reason and `fire_at ≥ last_sent_at + 90 min`. Then confirm the interaction that
matters: with the quiet window *also* shifted, `compute_defer` must satisfy **both** — the result
must be ≥ end-of-quiet AND ≥ last send + 90 min, not merely one of them.

**Converted-suppression.** Mark the mobile converted **only via the Zoho ingest path**
(`POST /api/zoho/status-webhook`, sealed — see Phase 5). Never write `conversion_status` directly:
guardrail 2 forbids it and the static scan will fail the build. Then assert the next due step
**CANCELs** with `engaged: converted`.

**Window closed.** Let a window pass 24h (or point a step at a stale window) and assert
`SKIP` + `window closed (session-only)` — and specifically that `counts["failed"] == 0`. A closed
window is a normal outcome, not an error.

**Distinct per-step copy.** Copy is read at **fire time**, so re-seeding changes pending sends.
Assert the 7 bodies are mutually distinct (this is what the owner's "identical messages" complaint
was about).

**`stop_on_reply` / opt-out.** Need a real inbound — see Phase 7 (WhatsApp Web). Until that session
exists, these two stay BLOCKED rather than faked: stamping `last_inbound_at` by hand proves only
that the comparison works, not that a real reply cancels a cadence.

**§6.1 referrer nudge.** Fires only at the configured step and only when the referrer's phone is a
known `Customer` (never guessed); capped one per step; unknown prospect name → generic descriptor;
`{{3}}` is the full link from `nudge_link_for()` (see the v5 contract).

## Phase 7 — WhatsApp Web (removes the last human step)

**Check the LOCAL Chrome first (found 2026-07-28).** The owner's WhatsApp Web session lives on the
local PC's Chrome, reachable via claude-in-chrome (`list_connected_browsers` → `switch_browser` →
navigate `web.whatsapp.com`). That session lets the engineer act as a **real contact** — trigger
keywords, tap real buttons, answer question nodes, read rendered link previews — with no VPS marker
file and no owner hands. **Never claim an inbound test "needs the owner's phone" before checking
this** (owner correction 2026-07-28; memory `verify-own-access-before-depending-on-owner`).
Former limitation, now SOLVED (2026-08-01): browser typing drops leading Devanagari, but
`document.execCommand('insertText', ...)` into the focused composer (via `javascript_tool`)
delivers intact Hindi — see Phase 7b #7. No phone needed for HI lanes.

With an authenticated `web.whatsapp.com` session (local or VPS Chrome), drive it via browser automation:
- Send the inbound "Hi" → `followup_inbound_poll` (every 5 min) opens the window **fully autonomously**.
  (The Wati inbound webhook is chatbot-suppressed — polling is the designed path, not a workaround.)
- **Read the login OTP** → unlocks Phase 8 OTP login.
- **Reply mid-cadence** → tests `stop_on_reply`.
- **Send STOP** → tests opt-out.

Never drive a conversation with any number outside the sanctioned test list.

Do NOT fake a window by setting `last_inbound_at` in the DB — Meta still rejects the session send,
so you would be testing the failure path and calling it green. To skip the 3h wait legitimately,
advance ONE step's `fire_at` while the window is genuinely open.

## Phase 7b — Chatbot & keyword estate (the Wati side of E2E; added 2026-07-28 after a live incident)

"End-to-end WhatsApp communication" includes the **Wati chatbot flows and keyword routing** — every
defect of the 2026-07-28 incident lived here, invisible to all GoRefer-side phases. Drive it as a
real contact over WhatsApp Web (Phase 7 session):

1. **Pre-check the contact's session state.** An OPEN Question node consumes EVERY inbound message
   BEFORE keyword routing — a contact stuck mid-flow makes the whole bot look dead (all buttons →
   the stock retry line). Diagnosis recipe: `getMessages` → if taps draw *"I'm afraid I didn't
   understand"* with **no Started/Ended-chatbot events**, it's an open question session, NOT broken
   keyword wiring. Clear it (complete or junk×failsCount) before judging anything else.
2. **Every quick-reply button literal, typed/tapped** → assert the mapped flow starts ONCE (a
   double-fire = two handlers on one literal — rule + legacy keyword action).
3. **Every Question node: one junk answer + one valid answer.** Assert the junk draws the node's
   configured, language-matched, example-bearing fallback (never the bare stock line) and the valid
   answer advances. **Audit `answerValidation` in the flow JSON first**: stored type Regex with an
   EMPTY `regex` rejects EVERYTHING — the trap that broke the Direct-Referral collector for every
   user who ever reached "Name?".
4. **Exhaustion behavior (precision proven live 2026-08-01):** `failsCount: "3"` means **three
   retry replies** — junk #1/#2/#3 each draw the fallback, and the **4th** bad input exits the flow
   **silently** (user freed, keywords route again, zero feedback). Test the full ladder: three junks
   → three retries → one more junk → silence → the entry keyword recovers. Expected, not a bug.
5. **Interactive-buttons/list cards:** typed non-matching text is **swallowed silently**; if the
   node's `interactiveButtonsDefaultNodeResultId` is unset the session dies and the card's buttons
   become DEAD UI. Assert every button/list node has a default branch.
5b. **POST-FLOW button taps — every card, every button (defect class found by owner screenshots
   2026-08-01).** A flow session ENDS at any terminal Message node (e.g. the advisor handoff);
   every button on cards already sitting in the chat then arrives as **plain text** on tap, and
   dies silently unless (a) the label is in the chatbot's keyword rule AND (b) the flow's START
   condition chain routes that label to its correct node. Only labels with dedicated rules (the
   advisor handoffs) survived; मेरा रेफरल लिंक / मेनू पर वापस / Get my referral link / Back to
   menu / bare "menu" were all dead until KM v7. **Test procedure:** end the flow at a terminal,
   then tap (or send the exact label text of) at least one button from EACH earlier card and
   assert the correct node answers. The ratified bar: *a tapped button is always obeyed —
   whenever it is tapped.*
5c. **Question-node junk mid-question (defect class found by owner probe 2026-08-01).** Send
   space-containing junk to every Question node and assert it draws the polite retry — never a
   confidently-wrong artifact (the v5 KM flow minted `gorefer.in/r/wa/hello there friend` as a
   "personal link"). Audit `answerValidation` in the flow JSON: the correct pattern is a **regex
   ALTERNATION** of the valid answer + every sibling button label + `[Mm]enu` (labels in the
   alternation is what keeps taps from being swallowed — labels-not-in-regex is the 07-31 trap;
   `Contains` conditions cannot express this because updateFlow silently drops them). Stored
   type "None"-as-written (numeric 3) accepts EVERYTHING including junk; stored Regex (numeric 2)
   with an EMPTY pattern rejects everything. Both are defects.
5d. **Stale sessions pin the OLD flow version.** After any flow edit, a contact mid-session (open
   question OR open buttons card) keeps running the pre-edit nodes, and typed entry keywords go to
   the open node (catch card / validation), never to keyword routing. Before judging a new
   version: END the session at a terminal node (tap the advisor button), then re-trigger fresh.
6. **Flow message bodies are deliverables** — apply the full Phase 0c bar to them: every link
   `https://`-schemed and resolving; the **first full URL in the body decides WhatsApp's preview
   card**, so the referral link must PRECEDE the disclosures link; the compliance footer
   (market-risk + `Disclosures: https://gorefer.in/d/pifs`) present on any benefit-claiming card
   (the live kit was missing it entirely until 2026-07-28); no partner code, no raw Zerodha URL.
7. **Both language lanes — and HI is now fully automatable.** The EN/HI condition split means the
   HI lane is a separate node set with its own copy, validators and fallbacks — EN passing proves
   nothing about HI. Devanagari input is SOLVED (2026-08-01): via `javascript_tool` on the WhatsApp
   Web tab, focus `footer [contenteditable="true"]` and run
   `document.execCommand('insertText', false, 'और जानें')`, then Enter via the computer tool —
   intact Hindi, no phone needed. "HI lane config-verified only" is no longer an acceptable
   end-state for a run.
7b. **Test matrix comes from the FIX SPEC / flow design, not the demo script.** Enumerate every
   scenario cell from the approved design (every button × in-flow AND post-flow, every question ×
   junk/valid/escape/exhaustion, both lanes) and classify each cell **tested / inferred / untested**
   in the report — never let a scripted happy-path sequence stand in for the matrix. Both
   2026-08-01 defects survived an "all pass" report built from the demo script alone; the owner's
   two probes ("all three buttons?", the phone screenshots) found them in minutes.
7c. **Verify the chat header before every composer send.** WhatsApp Web focus is fragile — a
   search-click can land on the wrong chat and the composer belongs to whatever chat is open
   (2026-08-01: a "Know More" landed in an unrelated human's chat). Screenshot → confirm the top
   bar shows the intended recipient → type → screenshot the sent tick in THAT chat.
8. Flow edits/backups/GET-verification: use the `wati-dashboard-automation` skill (74-key
   updateFlow write format; back up via `getFlow` FIRST; check `ok:true` + GET-after, never HTTP 200).

## Phase 8 — M13 referrer login (LIVE, both flags ON)

- `/login/` renders. **OTP path**: request → read the code from WhatsApp Web → verify → session.
  Codes are hashed+peppered, single-use, rate-limited; OTP goes only to a channel **already on file**
  (`onfile.py`) — assert a user-supplied number cannot redirect it.
- **Google OAuth path** (`/login/google/start` → `/callback` → `/bind`) — the *primary* login.
  Needs an authenticated Google session in the same browser; without it only OTP is testable.
- **Path-B ownership verification** `/login/verify-ownership` → creates a `VerificationRequest`.
- `/my/referrals` shows only that referrer's own data; `/my/logout` clears the session.
- Cross-account check: referrer A cannot see referrer B's referrals.

## Phase 9 — Admin dashboard (shared staff credential)

```bash
bash .claude/skills/e2e-whatsapp-communication/phase9-admin.sh create   # prints user+pass ONCE
# ... run the phase ...
bash .claude/skills/e2e-whatsapp-communication/phase9-admin.sh destroy  # ALWAYS, even on failure
```

Log in at `/admin-panel/login/` with the printed credential (grab the CSRF token from the login page
first — the POST needs it), then exercise every route:
`/admin-panel/` · `/explorer/` · `/journey/{id}/` · `/referrers/` · `/referrer/{client_id}/` ·
`/preferences` · `/verifications/`.

Assert: KPIs render from rollups; filters work; **PII masked**; referral vs partner-direct kept as
separate populations; unique-visitor counts **labelled approximate**; no dead UI or "Coming Soon"
anywhere (Constitution §4). Preferences writes round-trip through the config cascade.

## Phase 10 — Remaining API surface

`GET /api/analytics/funnel` · `/journey/{id}` · `/sync-health` · `POST /api/share/` ·
`POST /api/click/confirm` (nonce; idempotent; 401 on forged/expired/used) ·
`GET /api/click/referrer/{id}` (must 401 without a fresh nonce — closes id→name enumeration) ·
`POST /api/wati/webhook` — **assert CLOSED (401)**: `WATI_WEBHOOK_KEY` is unset on prod and this
endpoint had a fail-OPEN bug once. `POST /api/wati/inbound` (`?token=`) · `/api/health`.

## Phase 11 — Landing page + capture form (M3)

Unreachable while `LANDING_MODE=direct` — which is also why `is_confirmed_human` is **structurally 0**
and the daily report's "0 confirmed" is expected, not a regression. To cover it, flip a tenant to
page mode (`manage.py set_landing_mode page`), then assert: PIFS branding; does **not** resemble
Zerodha; both buttons (Continue to Zerodha / Share on WhatsApp to `+91 70806 42020`); the
"Referral ID: X" echo; disclosure block + risk warning + the single `REFERRAL_INCENTIVE_CLAIM`;
consent + privacy link; and that the JS beacon fires, producing a genuine confirmed-human click.
**Flip back afterwards.**

## Phase 12 — Language, privacy, analytics, isolation

- **Hindi** — `pref_lang='hi'` uses `body_hi`; the `referrer_language` rule is respected.
- **DPDP** — PII out of the immutable event log; raw IP + city in the separate erasable `VisitorPII`
  record; manual erasure works; the 12-month unconverted-prospect purge behaves.
- **Rollups** — `recompute_rollups` arithmetic matches raw events; conversions land on the **true
  Zoho opening date**, not the import date (ADR-017), so imports don't spike day 1.
- **Cross-tenant isolation** — tenant-scoped managers block cross-tenant reads (single tenant in
  prod today; assert at manager/test level).

## Phase 13 — The logic suite (separate from live)

This skill proves the live system behaves; it proves **nothing** about logic coverage.
Also run `python -m pytest -q -n 4` (44 test files), `ruff check .`, and
`python manage.py makemigrations --check --dry-run`.

**If you run the suite on the prod HOST, you MUST neutralise prod's `.env` or you will
chase 31 phantom failures.** Many tests assert flag-OFF / no-credentials behaviour, and
`flags.py` freezes from env at import — so prod's live flags and real creds make them fail.
This exact env produced **524 passed, 0 failed** on 2026-07-26 (verified), versus 31 failures
with prod's env:

```bash
rsync -a --exclude .venv --exclude .git /var/www/gorefer/ /tmp/gtest/   # never test in-place
ln -s /var/www/gorefer/.venv /tmp/gtest/.venv
cd /tmp/gtest && env \
  Q_ASYNC=false \
  ENABLE_CUSTOMER_LOGIN=false ENABLE_OTP_LOGIN=false ENABLE_ZOHO_WEBHOOK_HMAC=false \
  ENABLE_WATI_SEND=false ENABLE_ZOHO_WRITE=false ENABLE_ZOHO_READ=false \
  WATI_ALLOW_ALL_RECIPIENTS=false \
  WATI_API_ENDPOINT= WATI_API_TOKEN= \
  ZOHO_CLIENT_ID= ZOHO_CLIENT_SECRET= ZOHO_REFRESH_TOKEN= \
  GOOGLE_OAUTH_CLIENT_ID= GOOGLE_OAUTH_CLIENT_SECRET= \
  TEST_DB_NAME=gorefer_test_ci .venv/bin/python -m pytest -q -n 4
```

Breakdown of the phantom failures, so the pattern is recognisable: **12** from `Q_ASYNC=true`
(on-commit work queued, not inline → `zoho_sync_status='pending'` instead of `'synced'`); **15**
from live flags ON (every `..._when_flag_off`, `demo_adapter_selected`, `obeys_the_override_not_raw_env`
test); **4** from real creds being present (tests that prove the LIVE adapter *refuses to construct*
without creds, plus `oauth_start_404_without_credentials`). Note the OAuth env vars are
`GOOGLE_OAUTH_CLIENT_ID/_SECRET` — the `GOREFER_`-prefixed names in `GLOBAL.env` are a different
convention and blanking those does nothing.

**Before calling any failure a defect, get a baseline** from unmodified prod code in the same
env and diff the failure *sets*, not just the counts.

---

## Gotchas that cost real time

| Wrong | Right |
|---|---|
| `Referrer` | `ReferralIdentity` (holds `client_id`) / `Referral` (the journey) |
| `Event.occurred_at` | `Event.timestamp` |
| `FollowupRule.is_active` | `.enabled` |
| `ScheduledFollowup.step_key` / `.scheduled_for` | `.rule__step_key` / `.fire_at` |
| filtering `status="pending"` | initial status is **`scheduled`** — "pending: 0" is NOT a missing cadence |
| `Schedule.last_run` | doesn't exist; use `next_run` |
| `DailyRollup` / `.date` / `.conversions` | `DailyMetric` / `.metric_date` / `.accounts_opened` (in `apps.events`) |
| `Notification` in `apps.integrations.wati` | `apps.integrations.models` |
| reading `.env` for flags | `resolve_flag()` — DB override beats env |
| bare `ssh root@…` | `ssh -i ~/.ssh/firekaro_v6_vps` |

- Wati's `sendTemplateMessage` ack carries **no message id** → `provider_message_id` stays empty;
  terminal status is matched by recipient+template+time by the reconciler.
- A returning prospect **does** get a fresh cadence (the window timestamp is in the dedupe key).
- A contact who "gets no reply to anything" is almost always **stuck in an open Question node**
  (see Phase 7b #1), not a broken keyword estate — check chatbot events before touching wiring.
- The `getMessages` **eventType `ticket` entries are the flow audit trail** (Started/Ended chatbot,
  trigger source KeywordAction vs Rule) — they prove which handler fired and whether a session is
  still open; read them before any "keyword X is not wired" conclusion.
- WhatsApp Web keyboard-typing drops leading Devanagari — use the `execCommand('insertText')`
  method (Phase 7b #7) for Hindi; solved 2026-08-01, no phone needed.
- A flow edit does NOT reach contacts mid-session — they stay pinned to the old version until their
  session ends (Phase 7b #5d). "The fix doesn't work" is often just a stale session.

## Open questions — resolve, don't paper over

1. ~~M11 OG preview vs bot 302~~ RESOLVED 2026-08-01: crawlers get 200 + the PIFS OG card;
   humans get the 302. No contradiction.
2. ~~`Referral.first_click_at` stays `None`~~ RESOLVED 2026-08-01 (T-039): live stamping was
   already correct (`4ab05b8`); the gap was legacy rows whose one-time recovery was an ad-hoc,
   un-repeatable SQL statement — fixed with an idempotent `backfill_first_click_at` command
   (`apps/referrals/backfill.py`).
2b. ~~Credit-nobody conversions vanish from DailyMetric~~ RESOLVED 2026-08-01 (T-039, owner ruling
   option A): unattributed conversions now count under the program's rollup on their true IST date
   — `_apply_upsert` (`apps/integrations/zoho/ingest.py`) now marks the day dirty even when
   `referral is None`.
3. ~~`/open` destination~~ RESOLVED 2026-08-01: prod redirects to `signup.zerodha.com/?c=ZMPHZC`,
   matching CLAUDE.md (config-driven per §6d).
4. **Junk identities** `TALK` and `ZMPHZC` exist in prod from a malformed Wati chatbot link
   (`/r/wa/Talk to advisor`) — a flow variable leaked a menu label into the `client_id` slot.
   *Partially closed 2026-08-01:* KM v6/v7's escape chain + regex-alternation validation now route
   label text away from the id slot, so this leak path is shut; the existing junk rows still need
   the owner's delete decision.

## Cleanup checklist

- [ ] Report `zoho_lead_id` (and any test conversion) for owner deletion.
- [ ] Restore `LANDING_MODE` if Phase 11 flipped it.
- [ ] Note throwaway `E2E*` identities left in prod.
- [ ] Append a STATUS entry to `COORDINATION.md`; update `CURRENT-STATE.md` if state changed.
