# WATI Template Naming Convention (AUTHORITATIVE)

> **Locked by Abhay, 2026-07-17.** GoRefer is multi-partner across multiple partner groups, so
> template names must sort and filter by group → partner → purpose. Every **newly created** template
> follows this. Read `WATI-TEMPLATE-CREATION-RULE.md` for the whole-flow checklist; this file is only
> the naming rule.

---

## Format

```
gr_<lang>_<partnerGroup>_<partner>_<purpose>_<YYYY_MM_DD>
```

| Segment | Meaning | Rules | Examples |
|---|---|---|---|
| `gr` | GoRefer — fixed prefix | literal `gr` | `gr` |
| `<lang>` | Language — **MANDATORY, 2nd level** | **always present**, right after `gr`: `en` (English) or `hin` (Hindi). Never omitted — even the default English template carries `en`. | `en` · `hin` |
| `<partnerGroup>` | The partner's category | one lowercase token | `brokers` · (future: `insurance`, `mutualfunds`, `loans`, `properties`) |
| `<partner>` | The specific company | **one lowercase token, no internal `_`** | `zerodha` · `angelone` · `groww` |
| `<purpose>` | What the template is for | short, `_`-joined words | `office_new_lead` · `prospect_welcome` · `referrer_used` · `refer_earn` |
| `<YYYY_MM_DD>` | Creation date | always **last** | `2026_07_17` |

**Meta constraints honoured:** names are lowercase letters + digits + underscore only, and well under
Meta's 512-char limit. All segments are `_`-separated; because `<partner>` is a single token
(`angelone`, not `angel_one`), the name splits cleanly into fixed positions.

## Decisions (2026-07-17)
- **Language is MANDATORY and at the 2nd level** (right after `gr`): `en` or `hin` — **always present,
  even for the default English template** (updated 2026-07-17; supersedes the earlier "omit for English,
  before the date" form). Codes are `en` / `hin`.
- **Partner token:** single token, no internal underscore — `angelone`, NOT `angel_one` — so parsing
  the 6 segments on `_` is unambiguous.
- **Existing templates are NOT renamed.** The already-approved `gorefer_zerodha_eng_2026_07_10_v2`,
  `gorefer_zerodha_hin_2026_07_10_v2`, `gorefer_zerodha_eng_leads_2026_07_10` (Refer & Earn family) keep
  their old names — renaming would mean fresh Meta submissions + re-approval + code/reference updates
  for no functional gain. The new convention applies to **newly created** templates only.

## Worked examples

**The 3 lead-capture templates (Zerodha):**
```
gr_en_brokers_zerodha_office_new_lead_2026_07_17       (English, internal)
gr_en_brokers_zerodha_prospect_welcome_2026_07_17      (English)
gr_hin_brokers_zerodha_prospect_welcome_2026_07_17     (Hindi)
gr_en_brokers_zerodha_referrer_used_2026_07_17         (English)
gr_hin_brokers_zerodha_referrer_used_2026_07_17        (Hindi)
```

**Same purpose, a future partner (Angel One):**
```
gr_en_brokers_angelone_prospect_welcome_2026_07_17
gr_hin_brokers_angelone_prospect_welcome_2026_07_17
```
Group + partner still cluster together under `gr_<lang>_brokers_*`; language is the top filter.

**A future non-broker group (illustrative):**
```
gr_en_insurance_someinsurer_prospect_welcome_2026_08_01
```

## Versioning
- A body/button change = a **new template** (Meta won't let you edit an approved one in place). Bump by
  using a **later date** in the name (preferred over `_v2`, since the convention already carries the
  date). If two versions land the same day, append `_v2` before the date — e.g.
  `gr_en_brokers_zerodha_prospect_welcome_2026_07_17` → a same-day rebuild becomes
  `gr_en_brokers_zerodha_prospect_welcome_v2_2026_07_17`.
- **Never hardcode these names in code.** They live in config (a `ReferralProgram` field / a
  `rule_template_map` keyed by partner + role + language) and are read at send time, so a version bump
  or a new partner never needs a code deploy.

## Change log
- **2026-07-17** — Convention created (Abhay). Initial form `gr_<group>_<partner>_<purpose>_[lang]_<date>`.
- **2026-07-17 (rev)** — Abhay: **language is MANDATORY and moves to the 2nd level** (right after `gr`),
  always present even for English (`en`/`hin`). New form:
  `gr_<lang>_<partnerGroup>_<partner>_<purpose>_<YYYY_MM_DD>`. Partner = single token; existing templates
  grandfathered.
