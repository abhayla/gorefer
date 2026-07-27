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
- [x] **Follow-up engine gates (Phase 6) — DONE 2026-07-26, all 5 green.** See DONE section.
- [x] **Admin dashboard routes (Phase 9) — DONE 2026-07-26, all 7 green.** See DONE section.
- [x] **API surface (Phase 10) — DONE 2026-07-26; found + fixed broken access control.** See DONE.
- [x] **`POST /api/leads/` over HTTP (Phase 3) — DONE 2026-07-26, all green.** See DONE section.
- [x] **Phase 2 — bot filter breadth DONE 2026-07-26. PASSED; found + fixed a separate OG defect.**
      All 8 crawler UAs (facebookexternalhit · WhatsApp · Telegrambot · Slackbot · Twitterbot ·
      LinkedInBot · Googlebot · bingbot) → **zero `ReferralIdentity`, zero `Referral`, zero events**.
      Card leaks no partner code / Zerodha URL. **Note the expectation in the skill is now STALE:**
      crawlers get **200** (the D2 PIFS card), not a 302 — which also resolves the skill's open
      question 1 (M11 OG preview vs bot 302).
      **DEFECT FOUND + FIXED (`df1e25a`):** the D2 card emitted `og:image="img/og-card.png"` —
      relative, and even resolved `/img/og-card.png` **404s** (asset is at `/static/img/...`). So
      every forwarded referral link previewed with **no image**, on precisely the surface D2 exists
      to fix. M11's landing card already resolved this correctly; the crawler card didn't reuse it.
      `absolute_image_url()` is now the ONE builder, used by both. Existing assertion was
      `'property="og:image"' in html` (presence, not usability) — replaced with absolute +
      resolves-under-STATIC_URL, parametrised over human and crawler UAs. Disproof: reverting fails
      only the crawler case. Verified live: image now fetches **200 image/png**. Suite 637/0.
- [x] **Withdraw the superseded PENDING v1 template — DONE** (verified 2026-07-27:
      `gorefer_referrer_prospect_pending_en_2026_07_25` is `DELETED`). The only PENDING template
      remaining is `..._en_2026_07_26_v7`, the legitimate no-button UTILITY fallback — keep it.
- [x] **Sync prod's `tests/` tree** — DONE 2026-07-26 (review session): 4 files copied
      (`test_followups.py`, `test_m_wati1_share_intent.py`, `test_recipient_identity.py`,
      `urls_share_intent.py` — the earlier "3 files" count was wrong), prod now 48/48 vs repo.
- [x] **Fix `CURRENT-STATE.md` staleness** — DONE 2026-07-26 (review session): funnel-report
      line corrected to APPROVED (verified vs live inventory); deployed-SHA row rewritten to
      `324a1b8` (PR #52); OTP P0 recorded on the `ENABLE_OTP_LOGIN` row.
- [x] **Phase 11 — landing page + capture form VERIFIED LIVE 2026-07-27. No defects.**
      Flip done inside a `try/finally` so a crash could not leave prod in `page` mode;
      restoration asserted, `direct` confirmed after.
      **All present and correct:** PIFS-branded, does NOT resemble Zerodha · both buttons
      ("Continue to Zerodha", "Share referral details on WhatsApp") · `Referral ID` echo ·
      consent required + Privacy Policy link · `AP2516003693` + market-risk + the single
      10% claim · guardrail 3 clean (no `ZMPHZC`, no `signup.zerodha.com`).
      **Share target is the WATI BUSINESS number** (`watiNumber: "917080642020"`), per §4.
      `7388882020` also appears but as a legitimate **helpline** `tel:` link, NOT the share
      target — worth stating because a naive grep flags it as Ashok's personal number.
      **Flow matches spec:** validate → `POST /api/leads/` (lead saved FIRST) → only then
      navigate to the redirect route. Beacon is `fetch("/api/click/confirm")` with the nonce,
      in `static/js/landing.js`.
      **STILL UNPROVEN:** that the beacon actually FIRES and yields a genuine
      `is_confirmed_human` click — that needs a real browser executing JS, which this
      environment has no session for. Source-verified only; say so.
      **METHOD NOTE worth keeping:** the first two passes produced FOUR false alarms from
      crude regexes (button text longer than the pattern allowed; beacon in an external JS
      file; form inputs keyed by `id` not `name`), and pass 2 followed the 302 out of
      `/continue` and inspected **Zerodha's own signup page** while believing it was ours.
      A redirect-following fetcher is the wrong instrument for testing a redirect service —
      disable redirects, and read markup rather than boolean-grepping it.
- [x] **Phase 12 — DONE 2026-07-27, all four parts. Two real gaps found; one was a BUILD task.**
      **DPDP (part 2) was NOT IMPLEMENTED, not merely untested.** `VisitorPII.erased_at` was READ
      but nothing ever WROTE it — no service, command or admin action; a real erasure request meant
      hand-editing the DB. The 12-month purge was absent entirely. Both now shipped
      (`apps/common/privacy.py`, `erase_pii` / `purge_expired_pii` commands, daily
      `pii_retention_purge` schedule). **Why it hid:** `test_i3_visitor_pii_is_erasable` performed
      the erasure ITSELF inside the test — it proved the MODEL could hold an erased state, not that
      any code could produce one. Rewritten to call the real service.
      **Hindi (part 1): mechanism OK, COPY MISSING.** `seed_followup_cadence` writes `body_hi=""`
      for every rule, so `body_for(rule,"hi")` returns English — every Hindi prospect gets the
      English cadence while the templates around it are properly bilingual. The fallback is
      correct; the SILENCE was the defect. Now logs a WARNING naming the step. **Copy itself is
      owner-owned — 7 Hindi bodies still to write.**
      **Rollups (part 3): clean.** Live prod July: clicks 140 / landing 47 / redirects 24 /
      leads 10 / accounts 6 — all match raw events exactly. ADR-017 holds (8–68d drift between
      opening and sync, so imports land in their real period).
      **Isolation (part 4): holds, but by CONVENTION.** There are no tenant-scoped managers —
      `TenantScopedModel` is a plain FK column, so every query must remember `tenant=`. A
      two-tenant fixture sharing the same `client_id` AND mobile proves 7 read paths stay scoped,
      including the new erasure/purge. Suite 697/0.
- [ ] **24 Zoho/Wati journey templates.** Owned outside this repo — drive the Zoho Deluge
      functions (`ZOHO_FN_ZAPIKEY_WA_JOURNEY_*` in `GLOBAL.env`) and Wati flows directly.
      A GoRefer-only run cannot reach these; do not report them as covered until driven.

## 🔴 P0 — CONVERSION INGEST IS INERT: GoRefer watches the WRONG ZOHO MODULE (found 2026-07-26)

**Not one real conversion has ever reached GoRefer.** Every `Conversion` row in prod is synthetic
(two 09-Jul imports with placeholder ids, one blank-opener row, two of my own test rows).

**Evidence chain, each step verified:**
1. Owner's records: **6 accounts opened this month** — `UGF159` (18-Jul), `EUG979`←`YTW629` (17-Jul),
   `CWD202`←`EKU497` (13-Jul), `EKU497` (09-Jul), `MZK185`←`FWW808` (06-Jul), `KWE338` (02-Jul).
2. **0 of the 6 exist in GoRefer.** Two of the three referrers (`YTW629`, `FWW808`) are not even
   known as `ReferralIdentity` rows.
3. **0 webhook POSTs from Zoho** in 14 days of continuous nginx logs (12–26 Jul). All 17 logged
   calls were my own tooling (`curl/8.15.0`, `GoRefer-E2E/1.0`). There was **no POST at all on
   18-Jul** — so `CURRENT-STATE`'s "RJ4521 webhook-ingested 18-Jul" is unsupported; it was a manual curl.
4. **Not in Zoho `Leads`** — newest Lead created 2024-11; the only non-null `Lead_Status` values are
   "Not Interested" (newest April). No lead is "Account Opened with Us".
5. **They ARE in Zoho `Contacts`**, with matching dates: Uday Kumar Singh 18-Jul, Malvika Gupta
   16-Jul, Ram Chandra Gupta 09-Jul, Aayush Mehrotra 06-Jul. Malvika's Contact carries
   `Lead_Source: "Referral"`.

**ROOT CAUSE: GoRefer's ingest is built around the Zoho *Leads* module — it matches on
`zoho_lead_id` and `followups.services.has_converted()` reads `Lead.status` — but a Zoho lead that
converts BECOMES A CONTACT. The account-opened event never occurs in the module GoRefer watches, so
the workflow rule never fires and the webhook never gets called.**

The code is NOT broken: Phase 5 proved the sealed webhook ingests correctly, credits by client id,
stores the true opening date and rejects forgeries. **Nothing is feeding it.**

**Impact:** 3 referrers uncredited for real openings · GoRefer analytics report `accounts_opened=0`
for July when 6 opened · the 21:30 daily report has been stating 0 **falsely** · the whole
conversion/reward half of the product is inert.

**FIELD MAP FOUND (Zoho `Contacts`, 107 fields, 35 custom) — everything the webhook needs exists:**

| GoRefer webhook field | Zoho Contacts field | Type |
|---|---|---|
| `opener_zerodha_account_id` | `ClientId` | text |
| `referrer_client_id` | `Referrer_Client_Id` | text |
| `account_opened_at` | `Account_Opened_On` | date |
| `status` | `Account_Status` | picklist |
| `opener_name` | `Full_Name` | — |

Also available if wanted: `Referrer_Name`, `Referrer_Mobile`, `Referrer_Email`, `IsReferrer`,
`Referral_Bonus`, `Referral_Bonus_Amount`, `Assisted`, `Couriered`, `Mapping_Verified`,
`WhatsApp_Opt_Out`, `Is_Active_Investor`.

## 🟠 SECOND, INDEPENDENT PROBLEM — Zoho's conversion data is INCOMPLETE vs the owner's own records

Fixing the module bug alone will NOT make referrer credit correct, because Zoho itself disagrees
with the owner's account list (verified 2026-07-26 against `Account_Opened_On >= 2026-07-01`):

| Owner's record | In Zoho Contacts? | Referrer per owner | Referrer per Zoho |
|---|---|---|---|
| `UGF159` Uday Kumar Singh, 18-Jul | yes | (none) | (none) ✓ |
| `EUG979` Malvika Gupta, 17-Jul | yes (16-Jul) | `YTW629` | **`YTW628`** ⚠ one digit apart |
| `CWD202` Aradhana Gupta, 13-Jul | **ABSENT** | `EKU497` | — |
| `EKU497` Ram Chandra Gupta, 09-Jul | yes | (none) | (none) ✓ |
| `MZK185` Aayush Mehrotra, 06-Jul | yes | `FWW808` | **null** ⚠ no referrer recorded |
| `KWE338` Anupam Pandey, 02-Jul | **ABSENT** | (none) | — |

Also: `Account_Status` is **null on every row** — the picklist GoRefer's `statusmap` reads is not
being maintained (the ingest's `or "account_opened"` fallback would cover it, but it is unmanaged).
And `AACK095261` (Sneha Kumari, 24-Jul) IS in Zoho but is an **AngelOne** account, not Zerodha —
so a Contacts trigger must not blindly treat every opened contact as a Zerodha/PIFS conversion.

**Consequence:** even after P0-A, GoRefer would ingest 4 of 6 openings, credit **one** referrer —
possibly the WRONG ONE (`YTW628` vs `YTW629` differ by a digit; one is a typo) — and miss two
referrer credits entirely.

**This directly challenges ADR-013/016 ("Zoho is the SINGLE authoritative source of truth for
referral credit").** It is authoritative by design but demonstrably incomplete in practice. Owner
decision needed: bring Zoho up to date as the real SSOT, or accept a second reconciliation source.

- [x] **P0-E · DONE — owner confirmed `YTW629` correct, `FWW808` to be added; both applied to Zoho** — `YTW628` vs `YTW629`
      (which is correct? one referrer is being credited wrongly), and `MZK185`'s missing `FWW808`.
- [x] **P0-F · DONE — both Contacts created in Zoho**, or decide they are out of scope.
- [ ] **P0-G · A Contacts trigger must filter to Zerodha/PIFS accounts** — `AACK095261` proves
      non-Zerodha accounts share the module.

- [ ] **P0-A · DA DECISION + fix: point the Zoho trigger at Contacts.** Change the workflow rule to
      fire on lead→contact conversion (or Contact create where `Lead_Source="Referral"`) and POST the
      Contact's Zerodha client id + referrer client id to the existing sealed webhook. Needs the
      CUSTOM field API names on Contacts that hold those two ids — not in the standard field set.
- [x] **P0-B · DONE — reconciler SHIPPED and RUNNING** (`4919036`; `apps/integrations/zoho/reconcile.py`
      + `manage.py reconcile_conversions`). Verified 2026-07-27: the `zoho_reconcile_conversions`
      schedule is registered and the qcluster is actively processing it. This entry was stale.
- [x] **P0-C · DONE 2026-07-26 — backfilled the 6 openings** once A/B land, so referrer credit and July analytics are correct.
- [x] **P0-D · DONE 2026-07-27.** `CURRENT-STATE.md` §"Zoho ingest" rewritten: the endpoint is
      live and proven, but **nothing feeds it** — 0 Zoho POSTs in 14 days of nginx logs, and the
      `RJ4521` "webhook-ingested" row was a manual curl that was later reversed. Records that
      July's six openings were BACKFILLED, that P0-A is still open, and that P0-B's reconciler
      is the shipped mitigation.

**D3 (webhook IP allowlist) is now clearly PREMATURE** — arming a second lock on a door that has
never been used would only add another silent-failure mode. Do P0-A/B first, observe real Zoho
traffic, then enforce the allowlist against IPs actually seen.

## ✅ P0 PARTIAL RECOVERY — July data corrected end to end (2026-07-26 evening)

**Zoho corrected first (4 writes, owner-confirmed values):** `EUG979` referrer `YTW628`→**`YTW629`**
(the digit typo — it was crediting the wrong person) · `MZK185` referrer set to **`FWW808`** (was
null) · **created** `CWD202` Aradhana Gupta (ref `EKU497`, opened 13-Jul) and `KWE338` Anupam Pandey
(opened 02-Jul), both previously absent. Checked for duplicates by name+date before creating.

**Then backfilled all 6 through the REAL sealed webhook** (not a direct DB write — so the backfill
also re-proved the ingest path): conversions 6–11 created, `applied:true` each.

**Result:** 3 referrers now credited — **`YTW629`**, **`EKU497`**, **`FWW808`** — and all three
identities were created lazily by the import, exactly as ADR-018/019 specifies ("first click OR
first Zoho-imported conversion"). **July `accounts_opened`: 0 → 6.**

**Dates verified individually:** every row round-trips to IST midnight (`2026-07-18` → stored
`2026-07-17T18:30Z` → IST `2026-07-18 00:00`). ADR-017 holding.

### ⚠️ THIS WAS A BACKFILL, NOT A FIX — the pipe is still disconnected

P0-A (point the trigger at Contacts) and P0-B (the reconciler) are **still open**. The next real
account opening will be missed exactly as these six were. Do not read "July is correct" as "the
integration works".

- [x] **P0-H · DONE 2026-07-27 — the reported bug was a FALSE ALARM; a real latent trap was found
      one layer up and fixed (`179eb27`).** The claim was that `_accounts_opened_for_range` compares
      **naive** datetimes. It does not: `TIME_ZONE = "Asia/Kolkata"` and `_recompute_month` uses
      `make_aware`, so month boundaries are IST-aligned and correct.
      **The real hazard:** both `mark_dirty` call sites in `zoho/ingest.py` passed
      `account_opened_at.date()`. That value is IST midnight stored as UTC (1 Aug IST =
      `2026-07-31T18:30Z`), so `.date()` yields the **UTC** date and marks the **wrong month**
      dirty — the right month then never gets recomputed and the conversion vanishes from it.
      **Probed, not assumed:** in-memory `.date()` → `2026-08-01` (correct); after
      `refresh_from_db()` → `2026-07-31` (wrong). So the live webhook path is correct only *by
      accident* — the parsed value still carries its IST offset. Any path that RE-READS a
      Conversion gets the UTC date, and the **reconciler and backfill jobs are exactly that shape**.
      Both sites now use `timezone.localtime(...).date()`. The regression test calls
      `refresh_from_db()` first so it exercises the re-read state, not the accidentally-correct one.
      Suite 638/0, deployed.

## DECIDED by the owner 2026-07-26 — now actionable (was BLOCKED)

**Standing principle stated by the owner:** *"All such message settings should be configurable"* —
message behaviour belongs in the config cascade + Preferences, never hard-coded. Apply to every
item below and to future work.

- [x] **D1 · DONE 2026-07-26 — `/open` → plain signup, configurable via `partner_direct_url_template` → default `https://signup.zerodha.com/?c=ZMPHZC`, but CONFIGURABLE.**
      Owner wants to switch it to `/api/lead/?c=ZMPHZC` or any other URL without a code change.
      So: add a cascade key + Preferences field, default to the bare signup (the CLAUDE.md value),
      which also CHANGES current live behaviour away from `/api/lead/`.
- [x] **D2 · DONE 2026-07-26 — crawlers get the PIFS card (200), copy config-driven, and its text is CONFIGURABLE.** Real humans still
      302 to Zerodha; only the crawler fetch changes. Title/description from config.
- [ ] **D3 · Turn the Zoho webhook IP allowlist ON.** Owner: fetch Zoho's ranges myself — no Zoho
      login needed (they are published publicly). Order: fetch ranges → cross-check against real
      inbound webhook IPs → set `ZOHO_WEBHOOK_IP_ALLOWLIST` + `WEBHOOK_REQUIRE_IP_ALLOWLIST=true`
      → **immediately send a live sealed conversion to prove ingestion still works.** Wrong IPs
      silently stop real conversions, so the live re-test is mandatory, not optional.
- [x] **D4 · DONE 2026-07-26 — fill-blanks + one lead per mobile: FILL BLANKS ONLY + ONE LEAD PER MOBILE.** Empty field → take
      the new value; already-populated field → keep it (so spam/typos can't overwrite good data).
      Plus: a mobile gets **one** Lead — a re-submission updates that Lead instead of creating a
      second. (Prod today has 2 leads on `919876543210`.) This also aligns GoRefer with Zoho, which
      already upserts by mobile. **Flag when implementing:** decide what a *different* referrer
      re-submitting the same mobile means for attribution — Zoho stays the single source of credit.
- [x] **D5 · DONE 2026-07-26 — decoupled + configurable (`followup_stop_when_converted`) from `stop_on_reply`, and make it CONFIGURABLE.**
      "Account already open → never nudge" must always apply regardless of the reply setting, and
      be switchable from config without code.
- [x] **D6 · DONE 2026-07-26 — deleted 11 superseded templates, keep genuinely different ones.** Only ones
      that are an older version of a message already in use. Note Meta holds a deleted name ~30 days.
- [x] **D7 · DONE 2026-07-26 — `TALK` + `ZMPHZC` soft-deleted (identity + referral); click events kept** (reversible; rows retained).
- [x] **D8 · DONE 2026-07-26 22:25 IST — WhatsApp-OTP login VERIFIED LIVE END TO END.** The two
      undiagnosed tests were TEST-side (missing `raw_status` on `SendResult`; patch target must be
      `apps.integrations.wati.adapter`, not `apps.otp.adapters`, because `send()` imports inside the
      method). Adapter fix was correct. Widened to 4 cases covering every branch of the delivery
      split; proved by disproof (reverting the fix fails exactly the 2 QUEUED tests with
      `'failed' == 'queued'`). Live: challenge id=2 `channel=whatsapp_wati` / `delivery_status=delivered`,
      message READ at Wati 2s after the challenge (vs id=1, the only prior challenge ever recorded,
      which had already fallen back to `manual`). Verify → 302 `/my/referrals` + session; replay →
      **400** (single-use); `/my/logout` → dead; referrer session refused both admin surfaces;
      ADR-035 re-asserted (user-supplied `mobile` → 400). Suite 634/0, deployed `1be4c34`.
      **Google OAuth — the PRIMARY referrer login — remains UNTESTED, as the owner chose. Keep
      saying so in every report.**
- [x] **D9 · DONE 2026-07-27 (one step outstanding: the live verified send).** Shipped
      `12cabaf`; config wired; verified against the live Meta inventory.
      **Scope correction first:** all 7 cadence rules are `channel=session` — free-form, **no Meta
      category, no cap**. Every other configured template already resolved UTILITY/AUTHENTICATION.
      So the only marketing-capped template GoRefer sends is the §6.1 referrer nudge.
      **Root cause (from Meta's policy, not from guessing):** UTILITY needs non-promotional AND
      specific to the RECIPIENT's own transaction; **retargeting is MARKETING even when
      user-requested**. v4/v5/v6 were all the cart-abandonment shape with a referral link.
      **Label matrix, body held byte-identical so the button is the only variable — all APPROVED:**
      `Share Referral Link` EN **UTILITY** / HI MARKETING · `My Referral Link` same ·
      `Share on WhatsApp` same · `Refer` same · `Refer & Earn` **MARKETING in BOTH**.
      → (a) a referral SHARE button holds UTILITY in English; (b) **"Earn" is the one fatal word**;
      (c) **Hindi rejects the BUTTON itself** — four labels flipped, incl. one with no referral or
      reward wording, while HI with no button is UTILITY.
      **SHIPPED:** EN `..._en_2026_07_27_v9a` (button) · HI `..._hi_2026_07_27_v10` (no button).
      Both APPROVED UTILITY, both uncapped. Verified: button URL
      `gorefer.in/share/wa/{{client_id}}`, `buttonParamMapping.paramName = client_id`.
      **Owner-spotted functional fix:** `/r/wa/{id}` 302s the tapper to Zerodha SIGNUP — wrong for a
      REFERRER who already has an account. `/share/wa/{id}` opens WhatsApp's picker. Owner phone-tested.
      **Near-miss recorded:** positional params made Wati silently bind the button to the referrer's
      NAME → would have rendered `gorefer.in/share/wa/Ramesh Kumar`. `ok:true` proves nothing about
      the button mapping; read it back.
      **ACCEPTED RISK:** the URL shape is back in the template (what the `?s=wa` fix removed). Code
      guarantees only the button's INPUT — hence the live send below is required, not optional.
      - [x] **LIVE VERIFIED SEND DONE 2026-07-27 08:00 IST** — nudge sent to `917767009136` via
            the real adapter with the real named params; terminal status **READ**; delivered
            `finalText` confirms `name`/`prospect` substituted correctly. Wati's API does not
            expose the rendered BUTTON, so the button was verified by chain instead: template at
            Meta stores `gorefer.in/share/wa/{{client_id}}` bound to `paramName=client_id`, we
            sent `client_id=DA1707`, and `/share/wa/DA1707` resolves live. **Testing the failure
            mode found a separate defect:** `/share/wa/Abhay` returned 302 (not an error) and
            minted a junk identity — fixed by the strict per-partner `client_id` rule.
      - [ ] ~~LIVE VERIFIED SEND still owed~~ — deferred deliberately: it was ~01:00 IST and the
            engine's quiet hours (23:00–06:00) exist so we don't message people at night. Send to
            `917767009136` in working hours and confirm the delivered button resolves to
            `gorefer.in/share/wa/DA1707` (NOT a name), then that the link opens WhatsApp's picker.
      - [ ] Delete the losing variants (v9b/v9c/v9d/v9e, v6) once the winner is proven live.

## 🔴 GUARDRAIL 3 VIOLATED IN PRODUCTION — partner code on the referrer self view (found + FIXED 2026-07-26)

`/my/referrals`, the LOGGED-IN referrer self view, rendered PIFS's Zerodha partner code `ZMPHZC`
as a badge on the "Referral links" card. CLAUDE.md §7 guardrail 3 forbids the partner code in
**any** client-facing response, and §4 restates it ("injected SERVER-SIDE ... never appears").

**Root cause:** the self view and the admin Referral Profile share ONE template (ADR-026,
`templates/dashboard/referrer_profile.html`), which renders `{{ card.partner_code }}`. Correct on
the staff screen; a client-facing body for the referrer.

**Fixed at the DATA level** in `apps/accounts/selfview.py` — the same place IP masking already
happens, so a future template edit cannot re-expose it. Admin view untouched (test asserts it still
shows the code). Verified live after deploy: `ZMPHZC` count **0**, card still renders with
`partner_name` + link.

**Why existing coverage missed it — both reproduced in the new regression test:**
1. `test_login_surfaces_carry_no_partner_code_or_zerodha_url` claims to cover "every new
   client-facing login surface" but visits only **anonymous** pages.
2. `per_link_cards` returns `[]` with no activity, so merely visiting `/my/referrals` while logged
   in renders **no card** — a real click is REQUIRED to expose the badge. The new test drives a
   click and asserts the card is rendered before asserting the code is absent, so it cannot pass
   vacuously.

**Worth a sweep, not yet done:** other surfaces sharing admin templates with a customer role should
be checked for the same class of leak. Added below.

- [x] **Sweep every shared admin/customer template — DONE 2026-07-27, no further leaks.**
      `referred_people` projects only name/city/profession/partner/status/opened/reward (no mobile,
      email or IP — safe by construction); `clicks_rows.ip` is masked for the customer (verified
      live: admin `127.0.0.1` → customer `—`); `partner_code` now blank. Locked with a test that
      asserts over the WHOLE serialized customer context, not a field list, because
      one-template-two-roles makes this structural.
- [x] **Strict per-partner `client_id` format — DONE 2026-07-27, deployed + verified live.**
      Junk ids can no longer become referrers. Zerodha's rule (owner-specified): exactly 6 chars,
      first a LETTER, rest letters or digits. Applied ONLY to identity-CREATING paths (`/r/`,
      `/continue`, `/share/`, Wati assisted-capture); lookup paths keep the loose spec rule so
      staff can still find existing junk. Pattern is cascade config keyed by the partner's own
      code (§6d). **Live proof:** `DA1707`/`EKU497`/`RJ4521`/`FWW808` → 302; `ABHAY`/`TALK`/
      `PRODWA01`/`E2E0726`/`Zerodha` → 400. Suite 667/0.
      **Accepted:** a 6-letter string passes, so `ZMPHZC` would — a rule cannot both allow
      all-letter ids and reject one particular all-letter string.

## ✅ PHASES 7 + 8 — DONE 2026-07-27 via the OWNER'S LOCAL PC (not the VPS)

**I had wrongly reported these as blocked.** I checked the VPS for Chrome, found none, and
concluded "not possible" — without considering the machine the session actually runs on. The
owner corrected it. The local Chrome has a live WhatsApp Web session (logged in as
`+91 77670 09136`, a sanctioned test number) and Google sessions.

### Phase 8 — Google OAuth: COMPLETE, the PRIMARY referrer login is no longer untested
Full flow driven in the browser: `/login/` → **Continue with Google** → account chooser →
consent → `/login/google/callback` → `/login/bind` → **`/my/referrals`**.
**Security properties verified from the authorize URL, not assumed:** PKCE
(`code_challenge_method=S256`) · `state` present (CSRF) · scope is **`openid email profile`
only** — no excess · redirect_uri is our own callback. Consent screen requests name, picture,
email only.
`/login/bind` states *"Used only to match against the record on file — we never send anything
to it from here"* — ADR-035 upheld on the bind path too.
**Self-view verified visually:** no `ZMPHZC` anywhere (the guardrail-3 fix holding LIVE in a
real browser), IP column `—` on all 44 rows, visitors `31*` with the approximate footnote,
compliance block present, no phone/email.

### Phase 7 — `stop_on_reply` + converted-suppression: PROVEN BY REAL PRODUCTION DATA
No simulation needed, and nothing had to be sent. The owner's genuine reply (the OTP they
typed at 22:21) cancelled a REAL cadence:
    nudge_12h/15h/18h/21h  cancelled  `engaged: replied`
    nudge_9h               cancelled  `engaged: converted`
The skill listed these as BLOCKED pending a WhatsApp session; they were in fact already
demonstrated by live events. **A test that would have been faked was instead found already
true.**

### D9 button — FINALLY verified by DIRECT OBSERVATION
Wati's API does not return a rendered button (`template` is null, no detail endpoint), so this
had only ever been verified by inference. Opening the delivered message in WhatsApp Web shows
the **"Share Referral Link"** button rendering as a real tappable button, and clicking it
resolves to:
    gorefer.in/r/wa/DA1707        <- the correct client_id, NOT a name
    Disclosures: https://gorefer.in/d/pifs   <- the /share compliance fix, delivered
That rules out the exact failure mode (`/share/wa/Abhay`) by observation rather than by chain,
AND proves commit `606d710` is live in the real artifact.

- [ ] **Phase 7 remainder — OPT-OUT (`STOP`) NOT TESTED, deliberately. Blocked on REQ-F02.**
      Owner decision 2026-07-27: **do NOT build the re-subscribe path yet — recorded as a
      requirement instead** (`REQ-F02` in `docs/foundation/01-GoRefer-Foundation-Specification.md`
      §12.8). This gate stays unverified until REQ-F02 ships; testing it before then would
      permanently suppress a live number with no supported way back.
      Sending `STOP` sets `Allow Broadcast = false` on `917767009136` — the owner's own number —
      and **there is no configured START/re-subscribe keyword** (the conversation map records
      that it was deferred, because a bare "start" would false-match "how do I start"). So the
      opt-out would persist with no automated way back, suppressing legitimate PIFS messages to
      the owner until someone flips it in the Wati dashboard. Testing a one-way door on the
      owner's own number is not a call to make unilaterally.

## 🧹 PROD CLEANUP — DONE 2026-07-27 (owner-approved)

**Soft-deleted** (reversible, rows retained — the D7 pattern): `E2E0726`, `FCLIVE01`,
`REVW2607`, `PRODWA01`, plus `ABHAY` and `E2EBOTVERIFY` (junk created by my own probes).
**Safety check run immediately after: all 14 REAL identities intact** — `AB1234 CQX688 DA1707
EKU497 FWW808 GW5500 MK9033 RJ4521 SG2210 YT9788 YTW629 YW0175 ZD9598 ZZ8962`.

**Conversions 4/5 needed nothing** — they were ALREADY `is_reversed=True`, so already excluded
from analytics. An earlier note listing them as "cleanup owed" was wrong.

**Deliberately NOT touched:** conversions 1/2 (`ZA9001`/`ZA9002`) are pre-existing `seed_demo`
rows dated May/June. They inflate those months, but they predate this session and removing them
is a data decision, not cleanup. Flagged, not acted on.

- [ ] **4 Zoho test LEADS still need deleting — BLOCKED ON THE OWNER.** Record deletion is
      refused by a safety classifier and I did not route around it. All four confirmed test
      records first (`@example.invalid` emails, names like "E2e Test 26jul Delete", referrer
      `E2E0726`): `475281000041836002` · `475281000041538002` · `475281000041592002` ·
      `475281000030612001`. Recoverable from Zoho's Recycle Bin if removed in error.

## 🏗️ DESIGN ITEM (owner-requested 2026-07-27, build LATER) — hierarchical config

**Owner wants config settings to resolve down a four-level hierarchy**, with full control over
how a rule propagates:

    Category  →  Partner Group  →  Partner  →  Member
    SEBI/NSE  →  Brokers        →  Zerodha  →  PIFS

**Propagation modes to offer per setting** (the "full freedom" the owner asked for):
`inherit` (default — take the nearest ancestor's value) · `override` (this level sets its own) ·
`locked` (an ancestor forbids descendants changing it — this is what `COMPLIANCE_LOCKED_KEYS`
already does, generalised) · `required` (descendants must set it; no silent inherit) ·
`merge` (for list/dict settings, combine with the ancestor instead of replacing).

**⚠ THE MODEL IS CURRENTLY INVERTED — this is the crux, and it must be resolved first.**

| Owner's hierarchy | What the code models today |
|---|---|
| SEBI/NSE (category) | `ReferralProgram.regulator = "sebi_nse"` ✓ |
| Brokers (group) | *does not exist* |
| **Zerodha** (partner) | `ReferralProgram.name = "Zerodha"` — modelled as the **program** |
| **PIFS** (member) | `Partner.code = "ZMPHZC"` + `Tenant(pifs)` — modelled as the **partner** |

So the code calls **PIFS** the Partner and **Zerodha** the Program — inverted from the owner's
mental model, and from how the domain actually works (Zerodha issues the client ids; PIFS is one
of possibly many APs beneath it).

**Concrete debt this already created:** the strict client_id pattern shipped 2026-07-27 is keyed
`client_id_pattern__ZMPHZC` — namespaced by **PIFS** — but the 6-character rule belongs to
**ZERODHA**. A second AP onboarded under Zerodha would need a duplicate copy of the same rule,
free to drift. Re-key onto `Partner=Zerodha` when the hierarchy lands.

**Scope when built:** new `Category` / `PartnerGroup` / `Member` models + migrations, re-pointing
`Partner` at Zerodha, and a rewrite of config resolution that composes with (does NOT replace) the
existing ADR-022 user→tenant→central cascade — that one answers *which tier*, this answers *whose
rule*. Touches ADR-022 and ADR-023, so it needs an ADR before code.

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
