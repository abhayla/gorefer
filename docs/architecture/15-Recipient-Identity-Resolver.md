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
    self_client_id: str       # a REFERRER's own client_id (to build their share link); "" if n/a
    prospect_id: int | None
    lead_id: int | None
    lang: str                 # "en" | "hi"  (best-effort; defaults "en")
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
- **prospect** → the account-completion cadence (doc-14), copy templated with `{link}` from §5.
- **referrer** → **Phase 1: SUPPRESS** the prospect nudges (a referrer must never receive
  "your account opening is still pending"). A referrer-specific cadence is a later mission.
- **unknown** → send the generic prospect nudge with the `gorefer.in/open` fallback link (preserves
  today's behavior; identity only *improves* the link). Watch-list test numbers land here.

## 7. Where it plugs in
- **Resolve at SEND (fire) time, not enqueue time** — a prospect may become a Lead *after* the window
  opens; resolving in `fire_due_followups` / the gate (`apps/followups/`) keeps the link fresh.
  Memoize per `(tenant, mobile)` within one sweep.
- `body_for(rule, lang)` gains a `{link}` substitution filled from the resolved `RecipientIdentity`.
- `enqueue_followups` may still store a best-effort `prospect_id`/`role` for observability, but the
  **authoritative** resolution is at send.
- Reuse in M5 `queue_lead_notifications` (`notify.py`) is optional and out of scope for Phase 1.

## 8. Data model / config
- **No new PII, no schema change required** for the resolve-on-send design (the resolver reads
  existing tables). *Optional* observability: add `resolved_role`/`resolved_client_id` columns to
  `ScheduledFollowup` — **defer unless needed** (keep PII out of the event log, #16).
- **Config keys (cascade, tenant tier)** — `followup_link_mode` = `referrer_then_open` (default) |
  `open_only` | `none`; reuses `REFERRAL_INCENTIVE_CLAIM`, disclosure block (compliance-locked,
  central-only). Zerodha specifics (`ZMPHZC`, URL template) already come from
  `ProgramRedirectRule` (`redirect_service.assemble_destination`, `redirect_service.py:43-64`).

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

## 13. Open decisions for the DA (please confirm)
1. **Referrer recipients:** Phase 1 **suppress** prospect nudges to referrers (recommended), or send a
   minimal referrer message now?
2. **Unknown recipients:** send generic nudge + `gorefer.in/open` (recommended, preserves behavior),
   or **suppress until identified**?
3. **Language:** ship with `en` default + best-effort now, and add a real language signal
   (inbound-language or a Prospect `pref_lang`) as a fast-follow — OK?
4. **Observability columns** on `ScheduledFollowup` (`resolved_role`/`resolved_client_id`): add now
   for auditability, or resolve-on-send only (recommended: resolve-on-send)?

## 14. Build order / DoD
1. `recipient_identity.py` + resolver tests (TDD, §12) — pure, no engine coupling.
2. Wire into `fire_due_followups`/gate; add `{link}` substitution to the cadence copy; role-based
   suppression (§6).
3. Update `STEP_BODIES` copy to include `{link}` (the doc-14 nudges) — behind `followups_enabled`.
4. Update the SSOT conversation map (`Wati-Project/wati-chat-flow.html`) to encode recipient-role →
   message + link.
5. DoD: three guardrail tests pass; demo mode works flags-off; no PII in the event log; migrations
   only if the optional columns are chosen; PR per doc-14 mission conventions.
