---
name: gorefer-zoho-deluge-functions
description: Use when creating, editing, or debugging any Deluge function for the GoRefer/PIFS Zoho estate (sweeps, gatekeepers, journey nudges, webhooks, schedule wrappers), when pasting a function into the Zoho console errors, when a function silently returns created=0/empty results, or when wiring a new function into the WA_Send_Queue pipeline. Registry + wiring map + hard-won Deluge/data standards for this org (passiveincomesolutions, 60019670093).
---

# GoRefer Zoho Deluge functions — registry, wiring, standards

## Overview

Every Deluge function in this estate runs inside Zoho CRM and moves the same machinery: the
WhatsApp send-queue pipeline. This skill is the project memory for that estate — what exists,
how it connects, and the standards every NEW function must meet, each learned from a live
failure (dated below). **Before authoring or editing any function: read the registry and the
standards; after landing one: update the registry in the same turn.**

**Composes with (read for mechanics, don't duplicate):**
- `5Wealths/Zoho-Project/skills/manage-zoho-functions/SKILL.md` — tool routing: authoring is
  UI-paste-ONLY (no API can write Deluge); expose-as-REST + zapikey for execution/iteration;
  MCP for records/fields/config.
- Source SSOT for all function code: `D:\Abhay\VibeCoding\5Wealths\Zoho-Project\deluge\`
  (versioned in the `5wealths` repo; VPS copy `C:\Abhay\5Wealths\Zoho-Project\deluge` synced
  manually). Wati-Project/deluge no longer exists (moves 2026-07-19 and 2026-07-31).

## The wiring map (how everything connects)

```
Zoho workflow rules / blasts / journey functions
        │  create rows (Source_Rule, Mobile 91-prefixed, Params_JSON, Dry_Run, ...)
        ▼
   WA_Send_Queue  (custom module — the single send spine)
        │  read by
        ▼
gatekeepers (wa_gatekeeper_contacts/leads/referrers) — honor Dry_Run, allowlist, caps
        │  send via Wati API → recipients; reconciler (wa_reconcile_status) stamps
        ▼  Queue_Status SENT/FAILED + Fail_Code (prose strings, not numeric codes)
sweeps (wa_utility_fallback_sweep, wa_callcheck_sweep, wa_visitcheck_sweep)
        │  react to queue states → enqueue NEW rows (never send directly)
        ▼
   WA_Queue_Config (Config_Key/Config_Value rows) — every knob; NO literals in functions
```

- **Schedules can only execute schedule-category functions** → every `automation.*` worker has
  a one-liner `schedule.*` wrapper (schedule_<name>.dg). Zoho edition minimum interval: **2 hours**.
- **Zapikeys** for REST-triggering each sweep live in `GLOBAL.env` (`ZOHO_FN_ZAPIKEY_WA_*`,
  synced to the Windows VPS copy). Execute URL: `/crm/v7/functions/<name>/actions/execute?auth_type=apikey&zapikey=...`
- The fallback sweep's template names come from `fallback_template_map` (config row, per-language;
  empty lane = skip by design). Template governance lives in the conversation-map SSOT + the
  `whatsapp-zoho-template-review` and `meta-utility-template-approval-probability` skills.

## Function registry (update in the SAME turn as any change)

| Function (automation.*) | Purpose | Schedule | State 2026-07-31 |
|---|---|---|---|
| wa_utility_fallback_sweep | §6f UTILITY fallback for cap-blocked MARKETING failures | "WA Utility Fallback Sweep" every 2h + REST zapikey | **LIVE + E2E-PROVEN** (first real send DELIVERED 2026-07-31 18:44 IST to the allowlisted test number, terminal-status verified); EN lane only, HI deferred |
| wa_callcheck_sweep | Post-callback feedback check | "WA Callcheck Sweep" every 2h | Pasted; callcheck_enabled unset → no-op |
| wa_visitcheck_sweep | Post-office-visit feedback | "WA Visitcheck Sweep" every 2h | Pasted; visitcheck_enabled unset → no-op |
| schedule_wa_*_sweep ×3 | Schedule-category wrappers for the above | (they ARE the schedule targets) | Pasted + scheduled |
| wa_gatekeeper_contacts/leads/referrers | Queue senders (Wati API, allowlist, caps, Dry_Run) | scheduled (pre-existing) | LIVE |
| wa_reconcile_status (v2) | Stamps terminal statuses + Fail_Code from Wati | scheduled | LIVE |
| wa_journey_referrer_activation / _prospect_nudges | Daily journey nudges | daily 09:30 / 11:30 | LIVE |
| send_office_visitor_* + schedule_office_visitor_* | Office-visitor flow + wrappers | every 2h | LIVE |
| others (webhook handler, note-writers, wa_set_pref_lang, seed config, day summary, callback task v3, gorefer_webhook_signer) | see source headers | various | see Zoho-Project/deluge |

## Standards — every one bought with a live failure (violate = repeat it)

**Console/paste format**
1. File STARTS with `void <category>.<name>()` — comments before the signature are rejected
   ("Improper code format", 2026-07-30). Header comments go inside the braces.
2. **No `while` loops** — Deluge has none ("syntax incorrect Line 82", 2026-07-30). Use bounded
   `for each` over a list with guard flags. `break`/`continue` are fine.
3. Schedules can't see `automation.*` functions — ship the `schedule.*` wrapper with every worker.

**Zoho API reality (from inside Deluge)**
4. **Never put a datetime in searchRecords criteria** — `+05:30` decodes as a space and the
   function dies SILENTLY (2026-07-31; identical criteria REST-verified valid). For windowed
   reads: `zoho.crm.getRecords(module, page, 200, {"sort_by":"Modified_Time","sort_order":"desc"})`,
   filter in-loop, `break` when older than cutoff.
5. **searchRecords pages oldest-first** — a bare status query on a big module starves recent rows
   behind history (1,204-row lesson, 2026-07-31). Sort DESC via getRecords or constrain hard.
6. searchRecords has no `:in:` operator (INVALID_DATA/[BIGINT]) — loop equals-queries instead.
7. Every zoho.crm.* call that can return null goes through `ifnull()`; `.size()` on a failed
   search result throws.

18. **Datetime FIELD writes need the ISO string form** — `put("Eligible_After", nowT)` with a
   raw Deluge time object fails createRecord with INVALID_DATA; use
   `nowT.toString("yyyy-MM-dd'T'HH:mm:ss")` (2026-07-31, first live EN E2E test; precedent
   was already documented in wa_reconcile_status_v2.dg:343 — READ the existing functions'
   inline comments before writing new ones, they are case law).

19. **Params_JSON is an ARRAY of {name,value} pairs** — `[{"name":"name","value":"Abhay"}]`;
   a bare map is silently rejected by Wati's sendTemplateMessage (2026-07-31 E2E; the
   journey-nudge functions were the precedent).
20. **Guard every subString** — `resp.toString().subString(0,200)` on a short error response
   crashed the ENTIRE gatekeeper run, blocking all queue rows behind it (2026-07-31 E2E).
   Length-check before slicing; a truncation helper failing is worse than no truncation.

**Data reality (this org — verified via getFields/REST, do not trust memory)**
8. `Referrers.Client_Id` (underscore) vs `Contacts.ClientId` (no underscore) — not a typo.
9. `Contacts.Mobile` stores the **10-digit national** number; `WA_Send_Queue.Mobile` is
   **91-prefixed**. Convert with subString before matching.
10. **Blast-enqueued queue rows have EMPTY `Source_Record_Id`** (2026-07-31) — never rely on
    by-id resolution alone; fall back to by-mobile Contact lookup. (Root-cause fix — stamping
    the id in the blast enqueuer — is open backlog.)
11. `Fail_Code` holds Meta's PROSE strings ("Message undeliverable", "User's number is part of
    an experiment", quality-restriction long form) — classify by EXACT equality; the plain
    string must never substring-match the longer quality one.

**Behavior discipline**
12. Config over literals: every knob is a `WA_Queue_Config` row read at run start; a new
    function registers its keys (enabled=false + dry_run=true defaults) BEFORE first paste.
13. Fail-closed: master-switch check first; missing config → no-op with an `info` line, never
    a guess. Sweeps enqueue rows; ONLY gatekeepers send.
14. Never-blank params: every template variable gets a value or the row is skipped-and-logged
    (name → "Investor"; missing record_date → skip).
15. Dry-run first, always: new/changed send-path functions run with their dry_run config true
    until the owner reviews the WOULD-SEND output. The 2026-07-31 dry-run day caught THREE
    defects (std 1/4/5/10) before a single customer message.
16. Log skips as a map (`skipped.put(mobile, reason)`) and `info` it at exit — an empty skip
    map with zero output is what exposed the pagination bug; silent filters hide defects.
17. Idempotency/dedup: one action per target per day (check before create), stamp the source
    row (e.g. `Fallback_Sent`) so retry sweeps never double-fire.

## Checklist for a NEW function (all YES before first paste)

- [ ] Read this registry + the wiring map; name follows `wa_*` / `schedule_*` convention
- [ ] Source file created in `Zoho-Project/deluge/`, committed to the 5wealths repo, VPS copy synced
- [ ] Signature-first format, no `while`, wrapper included if scheduled (stds 1–3)
- [ ] Config keys registered with safe defaults; zapikey placeholder added to GLOBAL.env if
      REST-triggering is wanted
- [ ] Field api-names verified via getFields for every module touched (std 8) — never assumed
- [ ] Dry-run path + skip-logging + never-blank guards in the code (stds 13–16)
- [ ] After paste: one REST-triggered dry-run reviewed; registry row added HERE in the same turn

## Common mistakes

| Mistake | Reality |
|---|---|
| "The criteria works in REST so it works in Deluge" | Deluge mangles it (std 4) — the function dies with no error |
| Trusting Source_Record_Id | Blast rows don't have it (std 10) |
| Testing only the happy path via console "Execute" | Execute runs as YOU; schedules/REST run differently — verify via the zapikey path |
| Editing the repo file and assuming Zoho has it | Zoho runs the PASTED copy; every fix requires a console re-paste (owner action) — batch fixes to respect their time |
| Declaring done at `created=N` | Verify the created rows' content (params, Dry_Run flag) at the destination module |
