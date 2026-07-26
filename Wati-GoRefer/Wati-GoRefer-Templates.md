# Wati templates GoRefer uses

> The WhatsApp templates GoRefer's own notification path sends, their Meta status/category, and the
> role→template config mapping. **Only GoRefer's templates are listed here** — the full account-wide
> catalogue (including Zoho's `zoho_auto_*` sending templates) lives in
> `C:\Abhay\5Wealths\Wati-Project\docs\wati-templates.json`.
>
> Wati acct `105355`. Verified against the live account 2026-07-19.

---

## 1. Role → template mapping (the live config defaults)

Source of truth in code: `NOTIFY_TEMPLATE_DEFAULTS` in `apps/config/preferences.py`. Every one of
these is **overridable per tenant on the Settings screen with no deploy**.

| Role | Lang | Template (`elementName`) | Editable on Settings as |
|---|---|---|---|
| office | en | `gr_brokers_zerodha_office_lead_alert_en_2026_07_17` | Office / Ashok alert (English) |
| office | hi | *(maps to the en name — no Hindi variant)* | — |
| prospect | en | `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2` | Prospect welcome (English) |
| prospect | hi | `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2` | Prospect welcome (Hindi) |
| referrer | en | `gr_brokers_zerodha_referrer_thankyou_en_2026_07_17` | Referrer thank-you (English) |
| referrer | hi | `gr_brokers_zerodha_referrer_thankyou_hi_2026_07_17` | Referrer thank-you (Hindi) |

Resolution: `notify_template_name(role, lang=…)` → cascade (tenant override → central default).
Unknown language falls back to English; an unknown **role raises** (a new role must register a
default rather than silently resolving to something wrong).

**Login OTP (M13, separate from the role map):** the referrer-login OTP template name resolves
via `OTP_WHATSAPP_TEMPLATE` (settings/env default → per-tenant Preferences override), default
**`gr_platform_gorefer_login_otp_en_2026_07_21`** (AUTHENTICATION, copy-code button). Variables are
**NAMED** (owner rule 2026-07-21, never positional): `{{otp_code}}` then `{{expiry_minutes}}` — the
exact ordered `template_params` the OTP adapter sends (`apps/otp/adapters.py`; expiry derived from
the live TTL config at send time). Staged in
`apps/integrations/wati/wati-templates.json` — **APPROVED by Meta 2026-07-21** (submitted on
Abhay's review-go the same day; `waTemplateId 27564734539863645`; live-verified DELIVERED to the
owner's allowlisted number via terminal status). The OTP door's template precondition is met;
`ENABLE_OTP_LOGIN` may go on once the M13 code is deployed.

---

## 2. The approved `gr_*` templates in the Wati account

| elementName | Lang | Category | Status | `waTemplateId` |
|---|---|---|---|---|
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_17` | en | ⚠️ **MARKETING** | APPROVED | `2085330198687561` |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17` | en | ⚠️ **MARKETING** | APPROVED | `1403403211837882` |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17` | hi | ⚠️ **MARKETING** | APPROVED | `1080468977988332` |
| `gr_brokers_zerodha_referrer_thankyou_en_2026_07_17` | en | ⚠️ **MARKETING** | APPROVED | `1046549474582913` |
| `gr_brokers_zerodha_referrer_thankyou_hi_2026_07_17` | hi | ⚠️ **MARKETING** | APPROVED | `2132802414252307` |
| **`gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2`** | en | ✅ UTILITY | APPROVED | `1711546776760651` |
| **`gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2`** | hi | ✅ UTILITY | APPROVED | `1956926981638623` |
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_19` | en | ✅ UTILITY | APPROVED | `1049428880884247` |
| `gr_brokers_zerodha_referrer_update_en_2026_07_19` | en | ✅ UTILITY | APPROVED | `1367694621989458` |
| `gr_brokers_zerodha_referrer_update_hin_2026_07_19` | hi | ✅ UTILITY | APPROVED | `1282268567125664` |

### 2.1 The MARKETING reclassification — why `_v2` exists

The original 2026-07-17 five were submitted as **UTILITY** but **Meta reclassified them to
MARKETING**. That matters operationally, not cosmetically:

- MARKETING is subject to Meta's **per-user marketing cap (error 131049)** — the single largest
  failure mode on this account.
- A **welcome message must arrive**. Sending a must-arrive lifecycle message on a capped
  MARKETING template is the wrong trade.

So the prospect-welcome pair was **re-cut as `_v2` with the promotional phrasing removed**, and
those re-submissions **hold UTILITY**. The code therefore points prospect/en + prospect/hi at the
`_v2` names (see §1). The office alert was likewise re-cut under a fresh `_2026_07_19` name as
UTILITY.

⚠️ **Still on MARKETING and still wired in §1:** the two **referrer thank-you** templates. They are
lower-stakes than a welcome (a missed thank-you doesn't break the funnel) but they remain exposed to
131049. The UTILITY `referrer_update_*_2026_07_19` pair exists and is approved — **swapping the
referrer role onto it is a one-field Settings change, no deploy.** Worth doing.

### 2.2 Naming convention

`gr_<partnerGroup>_<partner>_<purpose>_<lang>_<YYYY_MM_DD>` — the language segment (`en` / `hi`,
occasionally `hin`) is mandatory immediately before the date. Older `gorefer_zerodha_*` names are
grandfathered. Authoring standards: the `wati-template-design-best-practices` skill; submission +
approval tracking: `wati-template-create-and-track`.

---

## 3. Parameter contract

Callers build **semantic** named params; the adapter remaps them to Wati's **positional** `"1"`,
`"2"`, `"3"` by order at the API boundary (see the contract doc §2). The three-variable shape used
by the lead-capture family, with fallbacks so a missing value never renders blank:

| Position | Meaning | Fallback |
|---|---|---|
| 1 | prospect / recipient name | — |
| 2 | referrer name | `"not on file"` |
| 3 | referral client id | — |

Email, where used, falls back to `"not provided"`. The resolved params are snapshotted onto
`Notification.template_params` at create time, so a later customer-record edit cannot retroactively
change what was actually sent. That field holds PII (name/email) — it is part of the **erasable**
operational record, deliberately not the immutable event log.

---

## 4. Related

- Send/verify mechanics: [`Wati-Integration-Contract.md`](./Wati-Integration-Contract.md)
- Full account catalogue + approval history: `Wati-Project/docs/wati-templates.json`,
  `Wati-Project/docs/wati-shared-template-category-rules.md`
- Delivery health (52.29% and the 131049 story): `Wati-Project/docs/`

## §6.1 referrer nudge — v5 (2026-07-26): the link is a VARIABLE, not template-hardcoded

**Owner-reported bug.** The referrer nudge rendered `gorefer.in/r/{client_id}?s=wa` — the channel as a
trailing query param (legacy M11 form) — instead of the canonical channel-path
`gorefer.in/r/wa/{client_id}` (B1 / Q-M-CHANNELPATH).

**Root cause — two link builders, one drifted.** `nudge_link_for()`
(`apps/referrals/recipient_identity.py`) is the single canonical builder and already emits
`/r/{channel}/{client_id}`. The **prospect** session nudge uses it. `_maybe_referrer_nudge()`
did **not**: it passed a bare `client_id` as positional `{{3}}` and let the **template body**
hardcode the URL shape. The `?s=` form exists only because a WhatsApp **URL button** requires its
variable to be LAST, so nothing may follow it — a constraint that does **not** apply to a message
**body**, so the body should never have adopted it.

**Contract change (v5).**

| | v3 / v4 | **v5** |
|---|---|---|
| `{{3}}` | bare `client_id` (`RJ4521`) | **full link** (`gorefer.in/r/wa/RJ4521`) |
| Body around it | `gorefer.in/r/{{3}}?s=wa` | `{{3}}` alone on its line |
| Source of the URL shape | the template body | `nudge_link_for()` — code only |

Templates: `gorefer_referrer_prospect_pending_{en,hi}_2026_07_26_v5`. Body is otherwise byte-identical
to v4; the mandatory market-risk + Disclosures block is unchanged and still follows the variable (Meta
requires static text after the last variable).

**Sequencing matters — do not flip one without the other.** Passing a full link to a v3/v4 template
renders `gorefer.in/r/gorefer.in/r/wa/RJ4521?s=wa`. Code (full link) and config
(`followup_referrer_nudge_template_{lang}` → v5) must ship together, and only once Meta has approved
v5 in that language.

**`link_mode="none"`** now skips the referrer nudge entirely rather than sending a blank variable
(Meta rejects blank variables, and "share your link again" without a link is meaningless).

**Operational note.** Wati's template `DELETE` returns `ok:true` but Meta retains the language content
(`error_subcode 2388024`, *"Content in this language already exists"*), so an `elementName` **cannot be
reused** after deletion — pick a new name (this is why the interim Hindi cut is `..._v4b`).
