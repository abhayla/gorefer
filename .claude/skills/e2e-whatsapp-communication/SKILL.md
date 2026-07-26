---
name: e2e-whatsapp-communication
description: Test the live GoRefer site end to end against real production — click a referral link and check the record was created, send a WhatsApp message and check it actually went out, run the follow-up nudge cadence, ingest a Zoho conversion, log into the admin dashboard, test referrer login, and check the safety guardrails hold. Use when asked to "test end to end", "run the E2E", "test everything", "verify prod", "full round of testing", or after any deploy touching redirect / Wati / Zoho / followups / login.
---

# GoRefer — full live end-to-end test

Tests the real production system at `gorefer.in`. Every leg is verified **at the destination**
(Wati's own record, the prod DB, the rendered page) — never at the point of dispatch.
`queued` / `accepted` / `202` are promises, not results.

**Pass bar for messages (owner-set 2026-07-26):** PASS at **`sent`**. Meta may block delivery
(per-user cap `131049` is common; delivery has run ~43%) — that is not a GoRefer defect.
`delivered` / `read` are bonus.

Use a fresh throwaway client id per run (`E2E<DDMM>`) so real referrer stats stay clean.
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
Assert **no** `ReferralIdentity` created for any `E2EBOT*` id. A 302 is still returned — only the
*record* is suppressed. See open question 1 about M11 OG cards.

## Phase 3 — Lead capture over HTTP (not the service layer)

`golive_smoke` (Phase 4) calls the service layer directly and therefore **bypasses HTTP validation,
consent enforcement, and rate limiting**. Test the real endpoint separately:

- `POST /api/leads/` valid payload → 201, `Lead` + `lead_captured` event.
- Missing/false consent → rejected (DPDP: consent required on the form).
- Malformed / oversized / illegal-char `client_id` → rejected by `validators.py`.
- Hammer past the limit → rate limiter trips (`apps/common/ratelimit.py`, DB-cache-backed so
  counters are shared across gunicorn workers).
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

Beyond firing one nudge:
- All **7** steps enqueue on window open (`status='scheduled'`); `dedupe_key = tenant|mobile|step|window_open_ts`.
- **Quiet hours** 23:00–06:00 IST → a night step defers to 06:00 IST (see an actual deferral, don't
  just read the gate).
- **Anti-burst** 90-min min-gap via `compute_defer`.
- **Distinct per-step copy** (copy is read at fire time, so re-seeding changes pending sends).
- **`stop_on_reply`** — reply mid-cadence (Phase 7) → remaining steps cancel.
- **Opt-out** — send STOP → suppression.
- **Converted-suppression** — a `has_converted` mobile gets no nudges.
- **Window closed** → step skips with `window closed (session-only)`, never a failed send.
- **§6.1 referrer nudge** (`followup_referrer_nudge_on`) — fires only when the referrer's phone is a
  known `Customer`, capped one per step, name→generic descriptor.

## Phase 7 — WhatsApp Web on the VPS (removes the last human step)

With an authenticated `web.whatsapp.com` session in the VPS Chrome, drive it via browser automation:
- Send the inbound "Hi" → `followup_inbound_poll` (every 5 min) opens the window **fully autonomously**.
  (The Wati inbound webhook is chatbot-suppressed — polling is the designed path, not a workaround.)
- **Read the login OTP** → unlocks Phase 8 OTP login.
- **Reply mid-cadence** → tests `stop_on_reply`.
- **Send STOP** → tests opt-out.

Never drive a conversation with any number outside the sanctioned test list.

Do NOT fake a window by setting `last_inbound_at` in the DB — Meta still rejects the session send,
so you would be testing the failure path and calling it green. To skip the 3h wait legitimately,
advance ONE step's `fire_at` while the window is genuinely open.

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
| reading `.env` for flags | `resolve_flag()` — DB override beats env |
| bare `ssh root@…` | `ssh -i ~/.ssh/firekaro_v6_vps` |

- Wati's `sendTemplateMessage` ack carries **no message id** → `provider_message_id` stays empty;
  terminal status is matched by recipient+template+time by the reconciler.
- A returning prospect **does** get a fresh cadence (the window timestamp is in the dedupe key).

## Open questions — resolve, don't paper over

1. **M11 OG preview vs bot 302.** Crawlers get a 302 to Zerodha, so WhatsApp would render
   *Zerodha's* card, not PIFS's — yet M11 claims forwarded links render a PIFS preview card.
   Reconcile; log a COORDINATION QUESTION if genuinely contradictory.
2. **`Referral.first_click_at` stays `None`** despite recorded click events (observed 2026-07-26).
3. **`/open` destination** is `signup.zerodha.com/api/lead/?c=ZMPHZC`, but CLAUDE.md specifies
   `signup.zerodha.com/?c=ZMPHZC`. No `r=` either way; confirm which is intended.
4. **Junk identities** `TALK` and `ZMPHZC` exist in prod from a malformed Wati chatbot link
   (`/r/wa/Talk to advisor`) — a flow variable leaks a menu label into the `client_id` slot.

## Cleanup checklist

- [ ] Report `zoho_lead_id` (and any test conversion) for owner deletion.
- [ ] Restore `LANDING_MODE` if Phase 11 flipped it.
- [ ] Note throwaway `E2E*` identities left in prod.
- [ ] Append a STATUS entry to `COORDINATION.md`; update `CURRENT-STATE.md` if state changed.
