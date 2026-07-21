# 13 — Partner Hierarchy & Vendor Independence (Target Architecture)

> **Status: RATIFIED AS MODEL-ONLY (DA, 2026-07-20) — still NOT scheduled.** Every decision in this
> doc is now carried by a locked ADR: **ADR-036…041** in
> [`02-Architecture-Decisions-ADR.md`](./02-Architecture-Decisions-ADR.md), with amendment
> annotations appended under **ADR-014** and **ADR-025**. See **§9** for the item→ADR map.
> Ratified means *decided and recorded*, **not** *scheduled to build*: per §5 this remains model-only,
> the Sprint-1 build is untouched, and nothing here is constructed until the multi-AP mission opens —
> at which point these ADRs bind it.
>
> *Provenance:* captured from Abhay (owner) verbally on **2026-07-19**, consolidating the 2026-07-09
> discussion-draft diagram (`gorefer-layered-architecture-diagram.html`, same folder) and
> S2-03 §"Category→Partner→Sub-broker"; engineer-authored as a faithful record of the owner's stated
> architecture — flagged in `COORDINATION.md` (2026-07-19). All §6 OPEN decisions and §7 gaps were
> owner-dispositioned 2026-07-19 and are now ADR-carried; **nothing in this doc is open.**

---

## 1. The hierarchy

GoRefer owns no referral program. It is a platform on which a five-level tree operates:

```
Regulator            SEBI/NSE (brokers) · IRDAI (insurance) · RBI (loans)
  └─ Partner Group   "brokers" · "insurance" · "loans" · "properties" …
       └─ Partner    Zerodha · AngelOne · Groww · LIC · …
            └─ Authorized Partner (AP) = TENANT   PIFS → Zerodha (row #1) · 50 more per partner …
                 └─ Referral links · referrers · journeys · events
```

| Level | What it is | What it carries |
|---|---|---|
| **Regulator** | Not a GoRefer entity — a rule *source* per group | Non-negotiable rules binding every partner and AP in the group (SEBI/NSE for brokers) |
| **Partner group** (a.k.a. category) | Taxonomy node: brokers, insurance, loans… | Group-wide rules = the regulator's rules; group-level defaults |
| **Partner** | The business running the referral program | Its own rules binding **all its APs**; the destination-URL template (per `ReferralProgram`). **The partner CODE is NOT partner-level — see §8 correction: it belongs to the (AP, partner) pair** |
| **Authorized Partner (AP)** | **= the tenant. One isolated login.** | Own rules, own referral links, own WhatsApp/mobile numbers, own vendor bindings (§3), own templates / send timings / email formats |
| **Referral links & below** | client_id-keyed links, journeys, immutable events | The Sprint-1 domain core, unchanged |

**NSE isolation mandate** (from the 2026-07-09 draft, unchanged): one login = exactly **one**
NSE-broker AP + any number of non-NSE partners side-by-side. A second broker **forces a new
isolated login** — NSE bars one person from operating across two brokers. This is why
**tenant = AP** is the tenancy cut, not partner or group.

## 2. Two cascades, opposite merge directions (the crux)

Rules and configuration *look* alike but must never share a resolver, because they merge in
opposite directions:

| | **Compliance cascade** | **Config cascade** (ADR-022, built) |
|---|---|---|
| Direction | **Tighten-only, most-restrictive wins** | **Override, nearest-to-the-AP wins** |
| Path | Regulator → Group → Partner → AP | Central → tenant-global → user |
| A lower tier may… | only **add** restrictions, never loosen | freely override the value |
| Example | SEBI ad rules > Zerodha AP rules > PIFS's own stricter limits | reward copy, landing mode, send timing, email format |
| Today's implementation | `COMPLIANCE_LOCKED_KEYS` resolve central-only (a 2-level approximation) | `apps/config/cascade.resolve()` — 3 tiers |

The vision extends both cascades from 3 tiers to the full 5-level path. **Compliance keys must
never ride the config cascade** — otherwise a tenant override could out-vote a regulator.

**Enforcement mode (owner decision, 2026-07-19): rules ADVISE, they do not bind, for AP-authored
communications.** The rule engine evaluates an AP's template/message/creative and returns a
verdict — *compliant* or *violates rule N* — but the AP always retains the final call. Bypassing
an adverse verdict requires an explicit, recorded acknowledgment ("proper disclosure"): the AP
confirms they saw the violation and proceed on their own responsibility, and that acknowledgment
is logged immutably (who, what rule, what content, when). The regulated entity is the AP; GoRefer
is the tool that informed them — the audit trail is the platform's protection and the AP's
informed-consent record.

**Acknowledgment UX (owner-specified, 2026-07-19).** The bypass is a popup/dialog shown at the
moment the AP saves/submits/sends content that fails a rule check. It MUST contain:

1. **The specific rule broken, cited by name and source** — for brokers a SEBI/NSE rule; for
   other partner groups their own regulator's rule (IRDAI, RBI, …). The rule engine resolves
   *which* regulator applies from the partner-group tier, so citations are data rows, not code —
   a new partner group brings its own rule set with no rebuild.
2. **What in the AP's content breaks it** (the offending claim/omission, named concretely).
3. **The platform's recommendation** — how to fix it to become compliant.
4. **An explicit first-person consent control** to proceed anyway, e.g.
   *"I understand this violates [rule ref]. I agree that I am breaking this rule and I choose
   to continue on my own responsibility."* — a deliberate act (checkbox/typed confirm + button),
   never pre-ticked, never the default path.

**The audit record** (immutable, per event): tenant, user, timestamp, content snapshot/hash,
rule id + the exact rule-text version shown, verdict, recommendation shown, and the action taken
(*fixed* vs *continued anyway*). This record — "we told him everything, he chose to proceed" —
is the platform's protection and the AP's informed-consent trail.

Scope boundary (engineer-drawn, for DA confirmation): *advisory* applies to **AP-authored content
sent from the AP's own number/identity**. It does NOT extend to:
1. **Platform-rendered surfaces** (`gorefer.in` pages) — the auto-injected disclosure block +
   risk warning stay hard (ADR-014); that is GoRefer's own liability surface.
2. **Platform behaviours** — never auto-submit a partner form, never impersonate a partner.
3. **Person-level legal duties** — opt-out/consent enforcement (DPDP) stays hard; an
   acknowledgment cannot authorize messaging someone who said stop.

⚠ **ADR reconciliation needed:** this decision softens the multi-AP reading of ADR-014
("publish blocked until compliance review passes") and ADR-025 (hard gates on AP advertising)
from *blocking* to *advise + recorded bypass*. Those ADRs are locked; the DA must formally
amend/annotate them — flagged in COORDINATION 2026-07-19.

## 3. Vendor bindings — platform-standard stack (owner decisions, 2026-07-19, final same-day revision)

Every external dependency is a **role filled through a port** (`apps/integrations/base.py`).
An earlier capture the same day had each AP bringing their *own* CRM/BSP; **Abhay revised this
before end of day: all APs use the platform's shared stack.** Vendor independence is preserved
at the **platform** level — GoRefer can swap its CRM or BSP by writing one adapter against the
contract doc — but it is **not a per-AP choice**.

| Port (role) | Binding | Decision |
|---|---|---|
| **CRM of record** | **One shared CRM for the whole platform — Zoho today.** | **Per-AP CRM option DROPPED** (owner, 2026-07-19, supersedes the earlier same-day capture). Every new AP onboards into the platform CRM. (A Google Sheet is not a CRM in any case — same-day decision.) |
| **WhatsApp BSP** | **One BSP (WATI today); ~~the shared business number is the standard posture "as of now"~~ → SUPERSEDED by §7 G-1: each AP gets their OWN number, all under the platform's WABA.** | **Per-AP own number is the standard posture** (§7 G-1, owner 2026-07-19; ratified as ADR-040). Templates approve once at WABA level and serve every number; Meta's quality rating is per number, so one AP's misbehaviour throttles only that AP. The **AP-owned-WABA** path remains a separate *optional* branch: an AP who insists on their own WABA/branding owns getting their template set approved on it; GoRefer tracks per-number approval and gates sends on it. |
| **Email** | (future port) | Per-AP formats/templates are plain config-cascade keys at tenant tier — no new machinery. |
| **Partner program** | `ReferralProgram` row per partner | Already config — add `partner_group`. |

> **SUPERSESSION NOTE (DA, 2026-07-20 — ruling 3 of the ratification pass).** This section was
> written before the §7 dispositions and originally recorded *"the shared business number is the
> standard posture"*. **§7 G-1 supersedes that**: the messaging topology is **one number per AP,
> all under the platform's WABA**. The BSP-level decision in this section is otherwise unchanged
> (one platform BSP, not a per-AP choice). The table row above has been corrected so this doc no
> longer contradicts itself; the authoritative statement of the topology is **§7 G-1**, ratified as
> **ADR-040**.

**Future-proofing requirement (owner, 2026-07-19 — same session, clarifying the above):**
platform-standard is today's *posture*, not a structural commitment. The architecture must keep
two moves permanently cheap:

1. **Adding a new CRM later** (multi-CRM may return in the future): one new adapter written
   against the role contract (`Zoho-Integration-Contract.md` is its seed). This stays cheap only
   while vendor vocabulary stays quarantined in the adapter package (status map, webhook shape,
   seal) and the domain core never learns a CRM's name — which the contract-doc CI gate and the
   `apps/integrations` boundary already enforce.
2. **Swapping the WhatsApp BSP:** template approvals attach to the **WABA at the Meta level, not
   to the BSP** — keep the same WABA/number, re-point it at the new provider, and the approved
   template set carries over; only the API surface and provider-specific features change.
   Corollary rule: **BSP-native extras (chatbots, CDP attributes, campaign tooling) must never
   become load-bearing in GoRefer** — GoRefer's dependency stays deliberately thin: send-template
   + terminal delivery status + webhook, exactly the surface `Wati-Integration-Contract.md`
   describes. (Changing the *number* is the expensive move — that re-enters template approval —
   so BSP portability planning should always preserve the WABA.)

Invariants that hold **regardless of which vendor fills a slot** (these are role-level rules,
already enforced in Sprint 1, and any replacement adapter must honor them):

1. **The CRM of record is the sole source of truth** for account/reward status; GoRefer never
   fabricates. (An adapter may satisfy the *ingest* contract by polling instead of webhook —
   the contract doesn't change, only the transport.)
2. **Messaging success = terminal delivery status**, never HTTP 200 (a Meta-level rule; survives
   any BSP).
3. **Never auto-submit a partner's signup form**; redirect a real human browser only.
4. Save the lead in GoRefer first; true open-date preserved; single-winner attribution.
5. Contract docs move with adapter code (CI-enforced, `CLAUDE.md` §6b) — a new vendor adapter
   is written *against* the existing contract doc.

## 4. What exists today vs. what the vision needs

| Vision element | Today (Sprint 1 code) | Gap |
|---|---|---|
| Tenant = AP, isolated | `apps.tenants.Tenant` + `tenant_id` discriminator (ADR-023) | None — cut is correct; only PIFS seeded |
| Partner + program | `Partner`, `ReferralProgram` models (provider-agnostic) | No `PartnerGroup`/category model; no regulator/rule tables |
| Config cascade | 3-tier `resolve()` + compliance-locked keys | Missing group + partner tiers; no tighten-only compliance resolver |
| Vendor binding | Adapters are process-global, chosen by flag | **None — platform-standard stack keeps this exactly as built** (owner, 2026-07-19). No per-tenant adapter registry, no per-tenant CRM credentials needed. |
| Per-AP WhatsApp identity | One WABA (`WATI_BUSINESS_NUMBER`), one number, one template set | **Per §7 G-1 / ADR-040:** one number **per AP**, all under the platform's WABA — needs per-AP number registration + routing of replies to the owning AP. Templates still approve **once at WABA level**, so no per-number approval tracking is needed here; that is required **only** for the *optional* AP-owned-WABA path (naming convention `gr_<group>_<partner>_…` already anticipates it) |
| Per-AP timings/formats | — | Plain config-cascade keys at tenant tier (no new machinery) |

## 5. Explicitly NOT being built now

Per the 2026-07-09 draft banner and Sprint-1 discipline: **model only**. The core refactor (if
ratified) happens later, on its own branch, after the current sprint is production-stable. No
`PartnerGroup` table, no rules engine, no per-tenant adapter registry exists or should be
speculatively built. The cheap, non-speculative step available *now* is keeping new schema
provider-agnostic (already policy) — everything else waits for partner #2 / AP #2 to be real.

## 6. ~~OPEN~~ RATIFIED decisions (kept verbatim as the record of what was open)

> **DA note (2026-07-20):** nothing in this section is open any more — all of it is owner-decided
> and now ADR-carried (see **§9**). The wording below is left **as originally written** so the
> record of what was asked is intact. Two phrasings here predate the §7 dispositions and are
> superseded: **D-13-3's** "for an AP who opts out of the shared number" should be read as *"for an
> AP who takes the optional **AP-owned-WABA** path"* (under G-1/ADR-040 every AP already has their
> own number, under the platform's WABA — so there is no shared number to opt out of, and
> per-number template-approval tracking applies only to that optional branch); and **D-13-2's**
> "tighten-only merge semantics (union of restrictions), and its resolver being *separate*" was
> **decided differently** — §7 settles it as **one resolver with per-key `locked_at_tier`**, where
> tighten-only is a hard stop at the locked tier, **not** a union merge (ADR-037).

- **D-13-1 Taxonomy schema:** `PartnerGroup` model + `Partner.partner_group` FK; where regulator
  rules live (rows vs. code vs. locked config keys).
- **D-13-2 Cascade extension:** 5-tier paths for both cascades; the tighten-only merge semantics
  for compliance (union of restrictions), and its resolver being *separate* from `resolve()`.
- **D-13-3 Own-number WhatsApp path (narrowed 2026-07-19 — the CRM half is GONE):** for an AP who
  opts out of the shared number: per-AP number registration, per-number template-approval tracking,
  and send gating until approved. No adapter registry needed — the BSP itself stays platform-wide.
- **D-13-4 Credential custody (narrowed 2026-07-19):** only the own-number WABA credentials, if
  that path is exercised — per-tenant, encrypted, never in `.env`. Platform CRM/BSP creds stay as
  today.
- **D-13-5 — RESOLVED by owner 2026-07-19:** one shared platform CRM (Zoho) for all APs; per-AP
  CRM choice dropped, Google Sheets never qualified. A certification checklist is only needed if
  the *platform* ever swaps CRM — at that point the existing `Zoho-Integration-Contract.md` is the
  checklist's seed.
- **D-13-6 Multi-login UX for the NSE rule:** how one human operating two broker-APs experiences
  "two separate people" without cross-view leakage.
- **D-13-7 Port naming:** rename vendor-named ports (`ZohoAdapter`, `WatiAdapter`) to role names
  (`CrmAdapter`, `MessagingAdapter`) — naming-only coupling today, cheap to fix at refactor time.

## 7. Engineer-surfaced gaps & edge cases (review, 2026-07-19 — for DA disposition)

Raised by the Engineer after the owner decisions above. **All dispositioned by Abhay on
2026-07-19 (options + recommendation reviewed per item); the DA ratifies but the owner has
decided.** Nothing here is built in Sprint 1 — these bind the multi-AP mission when it starts.

- **G-1 Shared-number blast radius — DISSOLVED by topology decision.** Owner decision: **no
  shared number across APs. Each AP gets their OWN number, all under the platform's WABA**
  (templates approved once at WABA level serve every number; Meta quality rating is per number,
  so one AP's misbehaviour throttles only that AP). Costs accepted: Wati bills per connected
  number (passable to the AP); ~20 numbers per WABA before a second WABA (one batch template
  re-approval there). This SUPERSEDES the earlier "shared number as standard posture" — the
  AP-owned-WABA path stays optional for APs who insist on their own branding.
- **G-2 Upsert key — DECIDED: `(tenant, mobile)`.** One lead per prospect per AP; strict NSE
  isolation; duplicate-outreach handled at the send layer (which dedups by mobile). Must be the
  FIRST migration of any multi-AP mission.
- **G-3 Inbound conversation ownership — DISSOLVED by the same topology decision.** Replies
  arrive on the owning AP's number; no routing rule needed.
- **G-4 Opt-out scope — DECIDED: per-AP opt-out + platform kill-switch.** Default: an opt-out
  binds that AP's number only (each AP is a distinct sender relationship). A second explicit
  "stop everything" escalation opts the person out platform-wide, enforced at the send gate for
  every AP number. The stop-confirmation message must explain the distinction.
- **G-5 Off-platform referrer home — DECIDED: holding tenant + admin assignment.** Unknown
  referrers land in a system "unassigned" tenant; admin assigns (auditable). Hard uniqueness
  rule: one client_id → one tenant per partner.
- **G-6 Approval + metering — FULLY CLOSED.** Approval half superseded by the advisory
  enforcement mode (§2): no blocking approval workflow; the rule-check verdict + acknowledged-
  bypass audit log IS the compliance artifact. **Metering half DECIDED (owner, 2026-07-19):
  YES — per-AP usage counters (messages, conversations, numbers) run from day one of multi-AP.**
  Counting only, no billing machinery; rationale: invoicing can be retroactive, counting cannot.

**D-13-2 mechanism — DECIDED: one cascade + per-key `locked_at_tier`** (generalizing
`COMPLIANCE_LOCKED_KEYS` to 5 tiers; unlocked keys stay nearest-wins). Locks apply to platform
config and platform-rendered surfaces; for AP-authored communications the enforcement mode is
ADVISORY per §2 (verdict + recorded bypass, never a hard block).

## 8. Pre-finalization additions (Engineer-raised, owner-accepted 2026-07-19)

### LOCKED CORRECTION — partner codes belong to the (AP, partner) pair, not the partner

`ZMPHZC` is not Zerodha's code — it is **PIFS's AP code at Zerodha**. Every AP brings their own
code per partner they're registered with, and their links must redirect with **their** code.
Therefore: the **destination-URL template** stays partner-level (`ReferralProgram`); the
**partner code** moves to the AP–partner link (today's `Partner.code` works only because PIFS is
the sole AP). Without this correction every AP's conversions would credit PIFS. Must land with
the (tenant, mobile) upsert-key change as part of the first multi-AP migration (G-2).

### Open requirements O-1…O-5 (accepted into scope; detail at multi-AP build time)

- **O-1 AP onboarding verification.** Before an AP's links go live, the platform verifies the
  AP's regulator registration number (e.g. NSE AP reg. no.) and their partner code per partner.
  Advisory mode protects the platform on *content*; this protects it on *who* — an unregistered
  person soliciting via GoRefer is platform exposure.
- **O-2 AP lifecycle: active → suspended → exited.** Per state, decide each asset's fate: the
  AP's number (stays in the platform WABA; NO quick recycling to another AP — stray replies
  would reach a competitor), in-flight conversions (accounts opening after exit — credit rule),
  referrer data (DPDP retention), and links (suspended = links resolve but all sending stops
  immediately, e.g. on regulator suspension).
- **O-3 Rule-library ownership.** Rules-as-data need a maintainer and a review cadence: each
  rule row carries its source circular reference and a review date; stale rule text = wrong
  advice with the platform's name on it (the audit log already records the rule-text version
  shown). Owner: Abhay/DA until delegated.
- **O-4 Platform–AP agreement mirrors the popup.** The onboarding contract must state what the
  acknowledgment popup states: the platform advises, the AP decides, regulated conduct is the
  AP's responsibility. Contract clause + per-event recorded consent are far stronger together.
  (Legal task — tracked here so it is not forgotten.)
- **O-5 Ops maturity as a platform obligation.** Before APs depend on the platform: verified
  nightly Postgres backups, a TESTED restore, and a stated recovery expectation (RPO/RTO) in the
  AP agreement. One VPS serving 50 APs' businesses is a promise, not just a server.
- **O-6 Hierarchy-scoped WhatsApp delivery report (feature + in-product page).** A daily
  reconciliation: the **Zoho side** (how many messages were *supposed* to send — Send-Queue rows by
  rule → partner → AP, by hour) joined against the **Wati side** (how many actually SENT, DELIVERED,
  FAILED — with Meta failure reasons: 131049 cap, 131026 bad number, etc.). Two deliverables: (a) an
  **operational scheduled report** (buildable now, single-AP, hierarchy-shaped — engine + skill:
  `build-daily-delivery-report`); (b) a **GoRefer in-product report page**, permission-scoped to the
  hierarchy — **an AP sees only their own numbers, a partner-group lead sees the whole group, admin
  sees everything** (ADR-036 tree). The page is a **future, model-only feature** — built when a
  mission opens, not speculatively; it needs the partner-group tagging that arrives with the first
  multi-AP migration (until then group/partner is derived from `Source_Rule`). Owner idea: Abhay
  2026-07-20. The reconciliation contract + data engine already exist as the skill above; the page
  renders it. The report is the natural place a new AP or partner group first *sees* their activity.

## 9. DA ratification (2026-07-20)

Every decision, gap and open requirement in this doc is now carried by a locked ADR in
[`02-Architecture-Decisions-ADR.md`](./02-Architecture-Decisions-ADR.md). All six new ADRs carry
**Status: Locked (2026-07-20, DA ratification of doc 13)** and are **model-only — not scheduled;
they bind the multi-AP mission when it starts** (per §5).

| Item (this doc) | Now carried by | Note |
|---|---|---|
| **D-13-1** Taxonomy schema (`PartnerGroup` + FK; where regulator rules live) | **ADR-036** | Five-level tree; rules-as-data at the group tier |
| **NSE isolation mandate** (§1) | **ADR-036** | The reason tenant = AP |
| **D-13-6** Multi-login UX for two broker-APs | **ADR-036** | No cross-view, no combined dashboard — stated requirement |
| **O-1** AP onboarding verification (reg. no. + partner code) | **ADR-036** | Precondition of activation |
| **D-13-2** Cascade extension → **one cascade + per-key `locked_at_tier`** (§7) | **ADR-037** | Tighten-only = a hard stop at the locked tier, not a merge |
| **§2** Enforcement mode: ADVISORY for AP-authored content | **ADR-038** | + 4-part popup, immutable audit record |
| **§2** Scope boundary (platform surfaces / behaviours / DPDP stay hard) | **ADR-038** (DA Ruling 2) | Confirmed **as drawn** |
| *(new)* Render boundary — injected block hard, AP claims advisory | **ADR-038** (DA Ruling 1) | Resolves an ADR-014 ambiguity |
| **O-3** Rule-library ownership + review cadence + source circular ref | **ADR-038** | Owner: Abhay/DA until delegated |
| **O-4** Platform–AP agreement mirrors the popup | **ADR-038** | Legal task, tracked |
| **§2** ⚠ ADR reconciliation needed | **ADR-014 + ADR-025 amendments** | Appended as `**AMENDED 2026-07-20 (ADR-038):**` blocks; locked text untouched |
| **D-13-5** One shared platform CRM (per-AP CRM **dropped**) | **ADR-039** | |
| **D-13-3** Own-number path (narrowed — CRM half gone) | **ADR-039** + **ADR-040** | Per-number approval tracking applies only to the optional AP-owned-WABA path |
| **D-13-4** Credential custody (narrowed) | **ADR-039** (DA Ruling 4) | **Narrowed further:** per-AP WABA creds arise ONLY in the AP-owned-WABA path |
| **D-13-7** Rename vendor-named ports to role names | **ADR-039** | At refactor time; naming-only coupling today |
| **§3** Portability: new CRM adapter; BSP swap preserving the WABA | **ADR-039** | Incl. the corollary that BSP-native extras must never become load-bearing |
| **§3** Five role-level invariants | **ADR-039** | Any replacement adapter must honor them |
| **G-1** Per-AP own number under the platform WABA | **ADR-040** | **Supersedes** §3's "shared number" posture (corrected inline, DA Ruling 3) |
| **G-3** Inbound conversation ownership | **ADR-040** | **Dissolved** by G-1 — replies land on the owning AP's number |
| **G-4** Opt-out scope: per-AP + explicit platform kill-switch | **ADR-040** | Stop-confirmation must explain the distinction |
| **G-6** Metering half — per-AP counters from day one | **ADR-040** | Counting only; *invoicing can be retroactive, counting cannot* |
| **G-6** Approval half | **ADR-038** | Superseded by advisory mode — no blocking approval workflow |
| **O-2** AP lifecycle active → suspended → exited | **ADR-040** | No number recycling; suspended = links resolve, sending stops |
| **§8 LOCKED CORRECTION** — partner code belongs to the (AP, partner) pair | **ADR-041** | Template stays partner-level; code moves to the AP–partner link |
| **G-2** Upsert key `(tenant, mobile)` | **ADR-041** | FIRST migration of any multi-AP mission |
| **G-5** Off-platform referrer → holding tenant, admin-assigned | **ADR-041** | One `client_id` → one tenant per partner |
| **O-5** Ops maturity (backups, tested restore, RPO/RTO) | *not an ADR* | An **operational obligation**, not an architecture decision — no design choice to lock. Tracked as a platform prerequisite before APs depend on the platform. |

**Corrections applied to this doc in the same pass:** §3's shared-number posture superseded by
G-1 (table row + inline supersession note); §4's per-AP WhatsApp-identity gap row updated to match;
the status banner flipped from *VISION / CONSOLIDATION — not locked* to *ratified as model-only*.

---

*Grounding: Abhay 2026-07-19 (verbal, this doc is the record) · `gorefer-layered-architecture-diagram.html`
(draft v1, 2026-07-09) · `docs/sprint2/S2-03` · ADR-022/023/024 · `apps/integrations/base.py` ·
`Wati-Project\docs\wati-shared-template-naming-convention.md` (moved from this repo 2026-07-19).*
