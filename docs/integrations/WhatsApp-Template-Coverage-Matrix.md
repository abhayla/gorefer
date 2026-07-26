# WhatsApp Template Coverage Matrix

> **Generated 2026-07-26, refreshed same day after the v5 cutover** from the live Wati inventory
> (100 records: 75 APPROVED, 24 DELETED, 1 PENDING) cross-referenced against template names
> **resolved on prod** (tenant 1) and the GoRefer code paths that send them.
>
> **Scope rule:** this matrix covers the **GoRefer-scoped** templates only. The shared Wati tenant
> `105355` holds **26 further live templates owned by other projects** (`firekaro_*`, `notifier_*`,
> `noter_*`, `realestate_*`, Angel One, and several **legacy `zerodha_*` referral broadcasts** such
> as `zerodha_refer_earn_v3`, `zerodha_referral_eng_2026_06_14`, `zerodha_account_opening_2026_06_02`,
> `leads_referrel_broadcast_2025_11_16`, `referrer_re_broadcast_2025_08_01`). They are deliberately
> outside this matrix — **except that the legacy Zerodha-referral ones are a Zerodha-AP compliance
> surface nobody currently owns**: they carry referral claims and predate the current disclosure
> conventions. Owner decision needed: re-verify or delete them.
>
> **The HTML conversation map is SSOT** — see `CLAUDE.md` §6c. This matrix is a *derived
> reconciliation view*: it exists to make config-vs-Meta drift visible. Where this matrix and the
> map disagree, the map states intent and the difference is a defect.
>
> **Regenerate** whenever a template is added, versioned, rewired, or deleted.
> Note: Wati's `wati_list_templates` **ignores `page_number`** (page 2 returns page 1), so 100 is
> the whole set, not a page.

## How to read this

- **Owner** = what actually triggers the send. `GoRefer code` = this repo. `Zoho/Wati journey` =
  driven outside GoRefer (Zoho Deluge functions / Wati flows) — *inferred from naming, verify before
  relying on it*. `UNWIRED / superseded` = approved at Meta but no known sender.
- **Cat** — `UTIL` (UTILITY) messages are not subject to the marketing per-user cap; `MARK`
  (MARKETING) are. `AUTH` = authentication. **Category is a deliverability decision, not cosmetic:**
  delivery has been running ~43% with Meta error `131049` (per-user marketing cap) dominating, so
  moving a must-arrive message from UTILITY to MARKETING actively harms it.

| Template | Status | Cat | Lang | Vars | Btn | Owner | Scenario | Config key |
|---|---|---|---|---|---|---|---|---|
| `gorefer_referrer_prospect_pending_en_2026_07_26_v5` | APPROVED | MARK* | en | 3 | 0 | GoRefer code | S6.1 referrer nudge - idle prospect (EN); `{{3}}` = FULL link from `nudge_link_for()` | `followup_referrer_nudge_template_en` |
| `gorefer_referrer_prospect_pending_hi_2026_07_26_v5` | APPROVED | MARK* | hi | 3 | 0 | GoRefer code | S6.1 referrer nudge - idle prospect (HI); `{{3}}` = FULL link from `nudge_link_for()` | `followup_referrer_nudge_template_hi` |
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_19` | APPROVED | UTIL | en | 4 | 0 | GoRefer code | Lead captured -> office/Ashok alert | `notify_template_office_en` |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2` | APPROVED | UTIL | en | 3 | 0 | GoRefer code | Lead captured -> prospect welcome (EN) | `notify_template_prospect_en` |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2` | APPROVED | UTIL | hi | 3 | 0 | GoRefer code | Lead captured -> prospect welcome (HI) | `notify_template_prospect_hi` |
| `gr_brokers_zerodha_referrer_update_en_2026_07_19` | APPROVED | UTIL | en | 2 | 0 | GoRefer code | Lead captured -> referrer update (EN) | `notify_template_referrer_en` |
| `gr_brokers_zerodha_referrer_update_hin_2026_07_19` | APPROVED | UTIL | hi | 2 | 0 | GoRefer code | Lead captured -> referrer update (HI) | `notify_template_referrer_hi` |
| `gr_platform_gorefer_login_otp_en_2026_07_21` | APPROVED | AUTH | en | 2 | 1 | GoRefer code | Referrer login OTP (M13) | `otp_whatsapp_template` |
| `gorefer_zerodha_eng_2026_07_10_v2` | APPROVED | MARK | en | 2 | 3 | Wati broadcast | Referral invite campaign | - |
| `gorefer_zerodha_eng_leads_2026_07_10` | APPROVED | MARK | en | 0 | 3 | Wati broadcast | Referral invite campaign | - |
| `gorefer_zerodha_hin_2026_07_10_v2` | APPROVED | MARK | hi | 2 | 3 | Wati broadcast | Referral invite campaign | - |
| `gr_platform_gorefer_delivery_report_en_2026_07_21` | APPROVED | UTIL | en | 11 | 0 | Wati-Project daily_report | 21:30 IST delivery report | - |
| `gr_platform_gorefer_funnel_report_en_2026_07_21` | APPROVED | UTIL | en | 15 | 0 | Wati-Project daily_report | 21:30 IST funnel report | - |
| `gorefer_prospect_day14_en_v2` | APPROVED | MARK | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day14_en_v3` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day14_hi_v2` | APPROVED | MARK | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day14_hi_v3` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_en_v2` | APPROVED | MARK | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_en_v3` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_hi_v2` | APPROVED | MARK | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_hi_v3` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day7_en_v2` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day7_hi_v2` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day10_en_v2` | APPROVED | MARK | en | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day10_hi_v2` | APPROVED | MARK | hi | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day3_en_v2` | APPROVED | MARK | en | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day3_hi_v2` | APPROVED | MARK | hi | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_prospect_day1_en` | APPROVED | MARK | en | 1 | 1 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_prospect_day1_hi` | APPROVED | UTIL | hi | 1 | 1 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_reopen_en` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_reopen_hi` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_welcome_en` | APPROVED | UTIL | en | 2 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_welcome_hi` | APPROVED | UTIL | hi | 2 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17` | APPROVED | MARK | en | 3 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v3` | APPROVED | MARK | en | 3 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17` | APPROVED | MARK | hi | 3 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v3` | APPROVED | MARK | hi | 3 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_prospect_pending_en_2026_07_25` | PENDING | MARK | en | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_en_2026_07_25_v2` | APPROVED | MARK | en | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_hi_2026_07_25` | APPROVED | MARK | hi | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_hi_2026_07_25_v2` | APPROVED | MARK | hi | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_en_2026_07_25_v3` | APPROVED | MARK | en | 3 | 0 | **UNWIRED / superseded** (was wired until v5, 2026-07-26) | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_hi_2026_07_25_v3` | APPROVED | MARK | hi | 3 | 0 | **UNWIRED / superseded** (was wired until v5, 2026-07-26) | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_en_2026_07_26_v4` | APPROVED | MARK | en | 3 | 0 | **UNWIRED / superseded** (UTILITY re-cut attempt; Meta kept MARKETING) | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_hi_2026_07_26_v4b` | APPROVED | MARK | hi | 3 | 0 | **UNWIRED / superseded** (`v4b` because Wati DELETE leaves Meta's language content — name unreusable) | not sent by any known path | - |
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_17` | APPROVED | MARK | en | 4 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_thankyou_en_2026_07_17` | APPROVED | MARK | en | 2 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_thankyou_hi_2026_07_17` | APPROVED | MARK | hi | 2 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_update_en_2026_07_19_v2` | APPROVED | UTIL | en | 2 | 1 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_update_hin_2026_07_19_v2` | APPROVED | UTIL | hi | 2 | 1 | **UNWIRED / superseded** | not sent by any known path | - |

**Totals:** 50 live GoRefer-scoped templates (of 76 live on the shared tenant — see scope rule) -
Zoho/Wati journey *(inferred - verify)*: 24; **UNWIRED / superseded**: 13; GoRefer code: 8;
Wati broadcast: 3; Wati-Project daily_report: 2

\* `MARK*` on the v5 pair: **UTILITY was requested, Meta granted MARKETING** (same reclassification
story as the 2026-07-17 five). The manifest records the split as `category` (requested) vs
`metaCategory` (granted).

## Findings from the 2026-07-26 reconciliation

1. **FIXED (was P0).** Prod `otp_whatsapp_template` was `gorefer_login_otp` — a name that has
   **never existed** at Meta in any status. Live probe returned **HTTP 400 / `accepted=False`**, so
   every WhatsApp login OTP failed and silently cascaded to the `manual` channel while
   `ENABLE_OTP_LOGIN` read ON. The adapter's correct hardcoded default
   (`gr_platform_gorefer_login_otp_en_2026_07_21`) was bypassed because the bad config value was
   truthy. Corrected in the config cascade and verified `accepted=True` with a live send.
2. **9 templates are approved but unwired**, including both `prospect_welcome_*_v3` and both
   `referrer_update_*_v2`. Each is a Meta-approved asset nobody sends — decide: wire, or delete.
3. **`prospect_welcome` v2 is UTILITY, v3 is MARKETING.** Bumping to v3 would push a must-arrive
   transactional welcome into the capped bucket. Do not treat that bump as routine.
4. **`gorefer_referrer_prospect_pending_en_2026_07_25` (v1) is the account's only PENDING template**
   and is superseded by v2/v3/v4/v5. Withdraw/delete it (queue item exists; NOTE Wati DELETE
   leaves Meta's language content behind, so the name cannot be reused).
5. **The Hindi office alert points at the older English template.** `notify_template_office_hi` has
   no override, so it falls back to `..._en_2026_07_17` while EN resolves to `..._en_2026_07_19`.
   Harmless today (office sends use EN) but it is latent drift.
6. **24 of 46 templates are owned outside GoRefer.** A GoRefer-only E2E run can never cover them;
   covering "all templates in all scenarios" requires driving the Zoho journeys and Wati flows too.

## Sweep results — 2026-07-26, all 8 GoRefer-owned templates (EN + HI)

Sent via the live prod adapter with **positional** params; verified at destination by reading
Wati's own terminal `statusString`, not the send ack.

| # | Template | Lang | Cat | Terminal status | Body rendered |
|---|---|---|---|---|---|
| 1 | `gr_brokers_zerodha_office_lead_alert_en_2026_07_19` | en | UTIL | **READ** | all 4 vars filled |
| 2 | `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2` | en | UTIL | **READ** | ok |
| 3 | `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2` | hi | UTIL | **READ** | Devanagari + vars ok |
| 4 | `gr_brokers_zerodha_referrer_update_en_2026_07_19` | en | UTIL | **READ** | ok |
| 5 | `gr_brokers_zerodha_referrer_update_hin_2026_07_19` | hi | UTIL | **READ** | Devanagari + vars ok |
| 6 | `gr_platform_gorefer_login_otp_en_2026_07_21` | en | AUTH | **DELIVERED** | code rendered |
| 7 | `gorefer_referrer_prospect_pending_en_2026_07_25_v3` | en | MARK | **FAILED** (Meta) | copy correct |
| 8 | `gorefer_referrer_prospect_pending_hi_2026_07_25_v3` | hi | MARK | **FAILED** (Meta) | copy correct |

**6/8 delivered or read. 2 accepted by Wati but blocked by Meta** — per the owner's pass bar
(`sent`), those count as PASS; the block is not a GoRefer defect.

### New findings from the sweep

7. **The §6.1 referrer nudge is being QUALITY-restricted by Meta**, not merely rate-capped. Failure
   detail: *"Message undeliverable as Meta has restricted it for higher quality messaging — retry
   again in a few days."* Distinct from `131049` (per-user cap). Both EN and HI v3 failed. This is
   GoRefer's newest live feature and its template is **MARKETING** — so in production it is
   currently throttled. ~~Re-cutting it as **UTILITY** is the likely fix~~ **DISPROVEN same day:**
   the v4 UTILITY re-cut reproduced the identical failure on `919999900000`, and Meta kept v4/v5
   as MARKETING anyway. The restriction is **per-recipient**, recovery is Meta-side (wait it out +
   lower marketing volume to that number) — not copy- or category-fixable from our side.
8. **Named vs positional params: no bug.** All 8 templates declare positional params (`1,2,3,4`)
   while `apps/otp/adapters.py` sends *named* (`otp_code`, `expiry_minutes`). Both rendered the code
   correctly (named → READ, positional → DELIVERED), so Wati accepts either. Flagged and cleared.
9. **Hindi is now covered.** Templates 3, 5, 8 rendered correct Devanagari with variables
   substituted. Nothing in the default code path sets `pref_lang='hi'`, so Hindi only gets exercised
   by an explicit sweep like this one — keep it in every run.
