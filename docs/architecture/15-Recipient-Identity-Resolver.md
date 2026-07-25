# 15 — Recipient-Identity Resolver (who is this message for?)

> **Status: DESIGN — PROPOSAL, awaiting DA sign-off.** Phase 1 is tenant-scoped (PIFS as sole AP)
> and buildable now; the design is **provider-agnostic (config over code)** with **Zerodha as
> program #1** — no `Zerodha*`-named file/table/route (Constitution / ADR-024). Feeds the doc-14
> Follow-up Engine and reuses the doc-13 §4 config cascade. Behind `followups_enabled` (default OFF).
> Author: session 2026-07-25, grounded in a read of the current code (file:line refs throughout).

## 0. The capability in one line
Before GoRefer sends any WhatsApp message, resolve **who the recipient is** — their **role**
(prospect vs referrer), their **originating referrer's client_id**, and their **language** — so the
engine can pick the right message **and** embed a referral link that carries the correct client_id
(preserving referral credit), instead of sending one static, identity-blind nudge to everyone.

## 1. Grounding — the gap, verified in code
The follow-up engine today identifies a recipient by **mobile only**:
- **Trigger** — `apps/followups/tasks.py:229` calls `record_inbound(tenant, mobile, latest)` with
  **no `prospect_id`, no language** — so even while looping `Prospect` mobiles (`tasks.py:209`) it
  discards which prospect it is.
- **Storage** — `FollowupWindow` and `ScheduledFollowup` are keyed by `(tenant, mobile)`
  (`apps/followups/models.py:88,134`). The `prospect` FK is *"best-effort … may be null"*
  (`models.py:129-133`); `pref_lang` defaults `"en"` (`models.py:135`).
- **Copy** — `apps/followups/management/commands/seed_followup_cadence.py:30` `STEP_BODIES` is **one
  static set for everyone** — no per-recipient link, no client_id.

So nothing in the send path resolves **role**, **referrer/client_id**, or **language**. It *assumes*
"prospect." **This is the gap.** (Confirmed: no `resolve-recipient-by-mobile` helper exists —
`grep` finds only unrelated `resolve_*` in `landing_mode.py`/`disclosure_service.py`.)

**The link the owner wants (prospect's nudge carrying their referrer's client_id) is only partly
resolvable today** — see §3. The pieces exist; nothing joins them at send time.

## 2. What the data model already gives us (the join is possible)
| Fact | Where | File:line |
|---|---|---|
| A referrer we know by phone | `Customer(tenant, program, client_id, mobile)` — an existing Zerodha client who refers; `mobile` is indexed | `apps/referrals/models.py:21,34-35,48` |
| A referrer's canonical identity | `ReferralIdentity(partner, program, client_id, id_source)` — the referrer keyed by raw client_id | `models.py:151-167` |
| The prospect (PII, erasable) | `Prospect(mobile, name, email, city)` — **no referrer field** | `models.py:271-283` |
| Prospect → their referral | `Lead(prospect FK, referral FK)` | `models.py:313-314` |
| Referral → referrer client_id | `Referral.referral_identity.client_id` (NULL for `partner_direct`); `Referral.credited_referrer` = winning client_id from Zoho | `models.py:214,230` |
| Existing referrer-by-client_id resolver (M5) | `_referrer_if_known(tenant, client_id)` → `Customer` with a phone | `apps/integrations/wati/notify.py:43-52` |
| Lead↔referrer wiring at capture | `_referrer_client_id(referral)` = `referral.referral_identity.client_id or ""` | `apps/referrals/lead_service.py:88,103-105` |

**The chain `mobile → Prospect → Lead → Referral → referral_identity.client_id` exists** — but only
once the prospect has a **Lead** (form submitted). A **bot-only contact** (messaged WhatsApp, window
opened, never filled the form) has a `FollowupWindow` but **no Lead → no referrer to embed** → needs
a fallback.

## 3. The contract
A single pure resolver in the referrals domain (reusable by follow-ups, M5 notify, dashboard):

```
# apps/referrals/recipient_identity.py
@dataclass(frozen=True)
class RecipientIdentity:
    role: str                 # "prospect" | "referrer" | "unknown"
    referrer_client_id: str   # the client_id whose link a PROSPECT should get (their referrer); "" if none
    referrer_mobile: str      # the referrer's phone IF GoRefer knows it (Customer/M5 _referrer_if_known); "" — for the referrer-nudge (§6.1)
    self_client_id: str       # a REFERRER's own client_id (to build their share link); "" if n/a
    prospect_id: int | None
    lead_id: int | None
    lang: str                 # "en" | "hi" — from the EXISTING referrer_language cascade key (§8), NOT a new signal
    confidence: str           # "customer_match" | "lead_join" | "zoho_credited" | "none"

def resolve_recipient(tenant, mobile: str) -> RecipientIdentity: ...
```

Pure, tenant-scoped, no side effects, defensively wrapped (a schema surprise returns
`role="unknown"`, never raises into the sweep — mirrors `services.has_converted`).

## 4. Resolution algorithm (Zerodha = program #1, program-agnostic shape)
Given `(tenant, mobile)`, normalized via the one canonical `normalize_phone`:

1. **Prospect-in-progress? (role=prospect)** — `Prospect` by `(tenant, mobile, deleted_at__isnull=True)`.
   If found, take the most-recent live `Lead`:
   - `referrer_client_id` = `lead.referral.credited_referrer` if set (Zoho winner, ADR-016), else
     `lead.referral.referral_identity.client_id` (NULL/"" for `partner_direct`).
   - `confidence` = `zoho_credited` | `lead_join` | `none` (prospect exists, no lead/referrer).
2. **Referrer? (role=referrer)** — `Customer` by `(tenant, mobile)` with a client_id
   (reuse the `_referrer_if_known` pattern, reversed to key on mobile). `self_client_id` = that
   client_id. `confidence=customer_match`.
3. **Unknown** — neither → `role="unknown"`, all ids empty (bot-only / watch-list contact).

**Precedence when a mobile is BOTH** (a referrer who is also opening their own account): a
**prospect journey that is not yet `account_opened` wins** (they need the completion message);
otherwise `referrer`. The resolver returns the winning `role` **and** both client_ids so a caller
can override by context.

## 5. Link rule (Phase 1, Zerodha)
The link is a **GoRefer route** (already provider-agnostic; the partner code is injected server-side):

| Role | resolvable? | Link in the message |
|---|---|---|
| prospect | referrer known | **`gorefer.in/r/{referrer_client_id}`** — credits the **original referrer** (idempotent with their pending application; no attribution conflict) |
| prospect | no referrer (truly partner-direct) | **`gorefer.in/open`** → `?c=ZMPHZC` — PIFS partner credit (never override an existing referrer with this) |
| referrer | — | their own `gorefer.in/r/{self_client_id}` (to re-share) — **but see §6: Phase 1 does not send prospect nudges to referrers** |
| unknown | — | `gorefer.in/open` fallback |

**Single-winner guard (ADR-016):** a prospect who already has a referrer must get **that referrer's**
link — `gorefer.in/open` is a fallback *only* when no referrer is resolvable, never a substitute that
would steal credit to partner-direct.

## 6. Message selection by role
- **prospect** → the account-completion cadence (doc-14), copy templated with `{link}` from §5
  (their referrer's `/r/{client_id}`), in the resolved language (§8).
- **unknown** → send the generic prospect nudge with the `gorefer.in/open` fallback link (preserves
  today's behavior; identity only *improves* the link). Watch-list test numbers land here.
  *(DA decision #2, 2026-07-25.)*

### 6.1 Referrer also gets nudged about their idle prospect (DA decision #1, 2026-07-25)
**Reverses the earlier "suppress referrers" recommendation.** When a prospect is idle/pending, GoRefer
ALSO nudges **that prospect's originating referrer** (when we know their phone) so the referrer — who
often knows the prospect personally — can give a direct, personal push. Owner rationale: **a personal
nudge from the referrer lifts conversion** more than a platform reminder alone.

Design:
- **Recipient** = the prospect's referrer, from `RecipientIdentity.referrer_mobile` (resolved via the
  M5 `Customer`/`_referrer_if_known` path; **skip silently if the phone is unknown — never guess**,
  matching `notify.py`'s referrer rule).
- **Channel/mechanics** — the referrer's own 24h window is usually CLOSED, so this is a **template**
  send (out-of-window), reusing the approved `referrer` template family via
  `notify_template_name("referrer", lang, tenant_id)`. Copy: names the prospect (best-effort) + gives
  the referrer their share link `gorefer.in/r/{self_client_id}` + a "give them a nudge" CTA.
- **Frequency cap (recommended default):** **one referrer-nudge per idle prospect**, fired at a single
  configured step (e.g. after the prospect crosses a longer-idle threshold), **not once per prospect
  cadence step** — so the referrer is never spammed. Tunable via a cascade key (§8).
- **Opt-out / routing** honored (referrer opt-out + the existing `referrer` routing toggle).
- **Attribution unaffected** — this is a message, not a status write (guardrail #2).

## 7. Where it plugs in
- **Resolve at SEND (fire) time, not enqueue time** — a prospect may become a Lead *after* the window
  opens; resolving in `fire_due_followups` / the gate (`apps/followups/`) keeps the link fresh.
  Memoize per `(tenant, mobile)` within one sweep.
- `body_for(rule, lang)` gains a `{link}` substitution filled from the resolved `RecipientIdentity`.
- `enqueue_followups` may still store a best-effort `prospect_id`/`role` for observability, but the
  **authoritative** resolution is at send.
- Reuse in M5 `queue_lead_notifications` (`notify.py`) is optional and out of scope for Phase 1.

## 8. Data model / config
- **No new PII, no schema change** — **resolve-on-send only** (DA decision #4, 2026-07-25). The
  resolver reads existing tables; no `resolved_role`/`resolved_client_id` columns are added (keeps PII
  out of the event log, #16, and avoids a migration).
- **Language — reuse the EXISTING rule, do NOT add a new one** (DA decision #3, 2026-07-25). Source
  `lang` from the existing `REFERRER_LANGUAGE` (`"referrer_language"`) cascade key + the
  `notify_template_name(role, lang, tenant_id)` mapping already in `apps/config/preferences.py:55,88`.
  The only change is **wiring the engine to READ it**: `notify.py:123` currently hardcodes
  `lang = LANG_EN` ("dormant until customer login") — replace that with
  `resolve(REFERRER_LANGUAGE, tenant_id)` (tenant-tier resolves today; a PIFS `referrer_language=hi`
  override then flows to prospect + referrer sends). No new field, no new signal, no new rule.
- **Config keys (cascade, tenant tier)** — `followup_link_mode` = `referrer_then_open` (default) |
  `open_only` | `none`; `followup_referrer_nudge_step` (which step fires the §6.1 referrer nudge;
  default = one, late step) + `followup_referrer_nudge_on` (bool, default true). Reuses
  `REFERRAL_INCENTIVE_CLAIM`, disclosure block (compliance-locked, central-only). Zerodha specifics
  (`ZMPHZC`, URL template) already come from `ProgramRedirectRule`
  (`redirect_service.assemble_destination`, `redirect_service.py:43-64`).

## 9. Compliance
- Disclosure block + market-risk warning are auto-injected/baked (context processor) — a link does
  not remove them. Nudge stays **UTILITY** (in-progress framing; no promotional claim in the nudge).
- **Duplicate-application caveat:** because a prospect gets *their own referrer's* link (not a new
  partner-direct one), re-opening is consistent with their existing attribution — no second competing
  credit. This is the reason the referrer link is preferred over `gorefer.in/open`.
- Never fabricate status; the resolver only READS attribution, never writes it (guardrail #2).

## 10. Provider-agnostic / extensibility
The resolver takes `(tenant, mobile)` and resolves **within the tenant's active program(s)**; Zerodha
is row #1. `client_id` semantics and the link template are program config, not code. Adding Groww/MF/
insurance later = a new `ReferralProgram` row + its `ProgramRedirectRule`, no resolver rewrite. If a
mobile maps to referrers in multiple programs, the resolver scopes to the program in context (the
follow-up's program), else returns the most-recent.

## 11. Edge cases
- Mobile is both prospect & referrer → §4 precedence.
- Multiple live Leads for one prospect (merged mobiles, ADR-018/019) → newest live Lead; prefer one
  whose `referral.credited_referrer` is set.
- Prospect with no Lead / no referrer → `role=prospect, confidence=none` → `gorefer.in/open`.
- Opted-out contact → the gate already cancels (`services.is_opted_out`); resolver not reached.
- Soft-deleted Prospect/Lead → excluded (`deleted_at__isnull=True`).

## 12. Testing (TDD — write first)
- prospect+referrer(identity) → `role=prospect`, `referrer_client_id` = identity client_id, link `/r/{id}`.
- prospect+partner_direct → referrer_client_id "" → link `/open`.
- prospect+Zoho `credited_referrer` set → uses the Zoho winner over the identity.
- referrer-only (Customer by mobile) → `role=referrer`, `self_client_id` set, **no prospect nudge**.
- dual role, open prospect journey → prospect wins; converted → referrer wins.
- unknown mobile → `role=unknown`, link `/open`.
- Hindi prospect → `lang="hi"` (once a lang signal exists; default en until then).
- resolver never raises → schema-error path returns `unknown`.

## 13. DA decisions — LOCKED 2026-07-25 (owner)
1. **Referrers are NOT suppressed — they get nudged about their idle prospect** so they can push the
   prospect personally (conversion lift). See §6.1 (template-based, phone-known-only, frequency-capped).
2. **Unknown recipients:** send the generic nudge + `gorefer.in/open` fallback (preserves behavior). ✓
3. **Language:** reuse the EXISTING `referrer_language` rule + `notify_template_name` — **wire the
   engine to read it**, add NO new rule/field. See §8.
4. **Observability:** resolve-on-send only, **no new columns**, no migration. ✓

Residual sub-decisions (my recommended defaults, tunable via config — flag if you want different):
- §6.1 referrer-nudge fires **once per idle prospect** at a late step (`followup_referrer_nudge_step`),
  not every step.
- `followup_link_mode` default `referrer_then_open`.

## 14. Build order / DoD
1. `recipient_identity.py` + resolver tests (TDD, §12) — pure, no engine coupling; returns
   `referrer_mobile` + `lang` (from `referrer_language`).
2. Wire into `fire_due_followups`/gate; add `{link}` substitution to the prospect cadence copy
   (their referrer's `/r/{client_id}`, else `/open`); resolve `lang` from `REFERRER_LANGUAGE`
   (replace the hardcoded `lang = LANG_EN`).
3. **Referrer-nudge path (§6.1)** — at `followup_referrer_nudge_step`, template-send the prospect's
   referrer (phone-known-only, capped, opt-out-aware) via `notify_template_name("referrer", lang)`.
   New referrer-nudge template copy may need Meta approval → gate behind the flag until approved.
4. Update `STEP_BODIES` copy to include `{link}` (the doc-14 nudges) — behind `followups_enabled`.
5. Update the SSOT conversation map (`Wati-Project/wati-chat-flow.html`) to encode recipient-role →
   message + link (prospect nudge + link, referrer-about-prospect nudge).
6. DoD: three guardrail tests pass; demo mode works flags-off; no PII in the event log; **no
   migration** (resolve-on-send); referrer nudge skips cleanly when phone unknown; PR per doc-14
   mission conventions.
