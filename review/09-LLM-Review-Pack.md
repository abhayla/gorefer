# 09 — LLM Review Pack (GoRefer)

> **What this is.** A **ready-to-use external review kit.** Paste each prompt below into a separate model, attach docs 01–08, collect the responses, and consolidate the suggestions into a versioned decision log. The goal is an adversarial, multi-perspective stress-test of GoRefer **before** Sprint 1 code is frozen — from three distinct lenses (architecture, product/growth, UX) plus a mandatory reality-check on the three things that can quietly sink the project.
>
> **How to use in one line:** send Prompt → attach docs 01–08 → collect response → paste into the Review Matrix → consolidate to v1.1 → freeze.
>
> **Compiled:** 2026-07-04 (Cowork session). **Owner:** Abhay Kumar Maurya (PIFS, Zerodha Authorised Person).

---

## Section A — One-page project context (self-contained; a reviewer with zero history can start here)

**What GoRefer is.** GoRefer is a **referral-management platform** for a Zerodha Authorised Person business. It sits as an intelligence layer between WhatsApp (via WATI) and Zerodha (the broker). Its job: make it effortless for an existing Zerodha customer to refer a friend, **preserve the referral attribution** (so the referrer gets credited), capture the lead in our own system first, and hand a real human off to complete account opening. It starts Zerodha-only but is architected to expand to other brokers/partners (Groww, Upstox, insurance, mutual funds) — "same platform, different partner."

**Who runs it.** Passive Income Financial Solutions Pvt Ltd ("PIFS"), a Zerodha Authorised Person since 2016. Director: Abhay Kumar Maurya. A branch office in Prayagraj is run by Ashok Kumar Patel, who is the human that calls leads and assists account opening. Key identifiers: Zerodha partner code `c=ZMPHZC`; NSE AP registration `AP2516003693`; principal broker Zerodha Broking Ltd, SEBI reg `INZ000031633`.

**How a referral actually works.** A Zerodha signup link carries two codes: `c=ZMPHZC` (credits PIFS as the AP for ongoing brokerage) and `r=<client_id>` (credits the referring customer under Zerodha's Refer & Earn). The reward to the referrer is **300 Zerodha reward points + 10% of the referred client's brokerage** (eligibility: ≥3 successful referrals in the trailing 12 months). GoRefer generates each customer's short referral link (`gorefer.in/r/{client_id}`, carrying the raw Zerodha `client_id` — no token, ADR-001), which redirects to the correct pre-filled Zerodha URL — the raw Zerodha URL is never exposed.

**The verified, non-negotiable reality (from a live July-2026 test).** Zerodha's referral link lands (one hop) on a **lead-capture-only** form (mobile, name, email, account-type, **reCAPTCHA**, Continue) that ends at a "thanks, we'll contact you" screen — it does **not** proceed into full KYC/account opening. Full KYC is a separate step Zerodha drives afterward. The partner/referrer codes are pre-filled but **editable** on Zerodha's own page, so they can't be fully locked. The form is **reCAPTCHA-gated**, so it **must not be auto-submitted**. Attribution requires the account to open within 60 days, and breaks if the prospect already registered with Zerodha before using the link.

**The agreed design (capture-first, human-assisted).** (1) A **PIFS-branded** GoRefer form (NOT a Zerodha look-alike) captures the lead — the referrer can fill the friend's details or the friend fills their own; `c=` and `r=` are baked in and hidden. (2) **Save the lead to our system first** (Zoho CRM), so it's never lost; alert Ashok instantly. (3) **Three WhatsApp messages** fire via WATI (to Ashok, to the new person, and — if the referrer's phone is known — to the referrer). (4) **Ashok calls and helps** complete Zerodha account opening — a real human satisfies reCAPTCHA legitimately and preserves both mappings. (5) The "continue" link keeps `r=` so the referrer stays credited.

**Systems already owned.** Zoho CRM Plus (org `60019670093`), WATI WhatsApp Business API (tenant `105355`, number +91 70806 42020). Recommended redirect/capture layer: a Cloudflare Worker that logs clicks (there is no click tracking today) and forwards to the right Zerodha URL.

**Three things that can quietly kill this (reviewers must weigh these):** (1) the reCAPTCHA / "account-opened-only-from-Zoho" boundary — GoRefer can never auto-complete an account and must never fabricate account status; (2) a **~33% WATI delivery failure rate** that leaks the funnel at step zero; (3) **SEBI/NSE AP compliance** obligations — a mandatory disclosure block, a swappable "10%" claim that is live-but-revocable, and a hard rule against misrepresenting Zerodha's brand.

---

## Section B — The three copy-paste REVIEW PROMPTS

> Send each prompt to the named model in a fresh conversation. **Attach docs 01–08** (see Section C). Ask for structured output so it pastes cleanly into the Review Matrix (Section D). Each prompt is self-contained — a reviewer needs nothing but the prompt + the attached docs.

### Prompt 1 — CLAUDE as Principal Software Architect

```
You are a Principal Software Architect reviewing a referral-management platform
called GoRefer for a solo operator (one-person company). I have attached the full
spec set (docs 01–08). Your job is to CHALLENGE the design, not praise it.

Review and stress-test:
1. DATABASE — data model for customers, referral leads, click events, referral
   journey. The referral identifier is the raw Zerodha client_id in the URL path
   (ADR-001 — opaque tokens were considered and deliberately rejected because
   referrers are open-ended and cannot be pre-mapped); that decision is LOCKED, do
   not re-open it. Given it is locked: what risks in the raw-client_id approach
   (public exposure of the id, no revocation, mistyped ids, enumeration) should we
   harden, and how? Normalization, indexing, join keys (Mobile + Client ID across
   Zoho modules).
2. SCALABILITY — this starts Zerodha-only but must become provider-agnostic
   (multiple brokers/partners). Where will the design hardcode "Zerodha" and hurt
   later? Redirect service throughput and edge-friendliness.
3. APIs — are the WATI and Zoho integration contracts (doc 08) correct and
   complete? Failure modes, retries, idempotency, webhook gaps.
4. SECURITY — the referral-code-swap revenue leak, the reCAPTCHA boundary, a
   hardcoded WATI JWT, PII handling, lead-capture abuse/spam.
5. MAINTAINABILITY — for a ONE-PERSON team. What will be unmaintainable? What
   should be cut, simplified, or deferred?

Hard constraints you must respect and pressure-test (do not propose violating them):
- Zerodha's form is reCAPTCHA-gated and MUST NOT be auto-submitted.
- Account-opening & reward status come ONLY from Zoho; GoRefer never fabricates them.
- Every asset carries the SEBI/NSE AP compliance disclosure block.

Deliver: a prioritized list of concrete problems and fixes. For each, state
Severity (Critical/High/Medium/Low), the specific risk, and your recommended
change. Lead with the uncomfortable ones. Be specific, not generic.
```

### Prompt 2 — GROK as Startup Founder + Product Strategist

```
You are a serial startup Founder and Product Strategist reviewing GoRefer, a
referral-management platform built by a solo operator who is a Zerodha Authorised
Person in India. Spec set attached (docs 01–08). Challenge the business and product,
not the code.

Review and stress-test:
1. PRODUCT-MARKET FIT — is "make it effortless to refer + we call your friend"
   actually a product people want, or a feature? Who is the real buyer/user? What's
   the wedge? Is Zerodha-only too narrow, or is multi-partner premature scope creep?
2. REFERRAL PSYCHOLOGY — the design pushes "share your friend's name + mobile" as
   the recommended path over "share your own link." Is that the right incentive
   surface? What actually motivates an Indian retail investor to refer? Is 300
   points + 10% brokerage a compelling enough hook, and what happens to the whole
   value prop if the "10%" claim gets revoked by the regulator?
3. GROWTH LOOPS — where is the compounding loop? Does each referral generate more
   referrals, or is this a linear campaign? What's the viral coefficient story?
4. ENGAGEMENT & RETENTION — after one referral, why does a customer come back?
   Leaderboards, gamification — real retention or vanity?
5. BUSINESS RISKS — the ~33% WhatsApp delivery failure, regulatory revocation of
   the incentive, dependence on one human (Ashok) to close every account, channel
   concentration on WhatsApp/Meta.

Think like someone trying to build a one-person, high-leverage business. Where is
the 10x opportunity being missed? Where is effort being wasted on the wrong thing?
Deliver ranked, blunt recommendations with the reasoning and the risk for each.
```

### Prompt 3 — GEMINI as Principal UX Architect

```
You are a Principal UX Architect reviewing GoRefer, a referral-management platform
for a Zerodha Authorised Person in India. Most users arrive from WhatsApp on a
phone. Spec set attached (docs 01–08). Challenge the experience.

Review and stress-test:
1. UX & FLOW — the end-to-end journey: customer gets a WhatsApp campaign → taps a
   link → PIFS-branded landing page → submits friend's name+mobile (or friend fills
   own) → gets a callback. Where is friction, confusion, or drop-off? Is the
   "share friend's details vs share my link" choice clear or paralyzing?
2. NAVIGATION — the link scheme (gorefer.in/r/{client_id}, /open, /rewards, /help,
   /track, /assets). Is it intuitive and memorable?
3. MOBILE — this is mobile-first (WhatsApp origin). Tap targets, form length,
   one-tap share/open, load speed on Indian mobile networks.
4. DASHBOARDS — the customer referral dashboard and the admin panel (leads,
   statuses, analytics, leaderboard). Is the information hierarchy right? What's
   noise vs signal?
5. ACCESSIBILITY — contrast, font sizes (note: compliance requires min font 10 for
   the risk warning), screen-reader support, Hindi/English bilingual UX.
6. ONBOARDING — first-time referrer and first-time friend. How do we explain
   "we'll call you" without it feeling like a spam trap? Trust-building for a
   financial product.

Constraint to respect: the landing form must be clearly PIFS-branded and must NOT
resemble Zerodha's own signup page (regulatory misrepresentation rule).

Deliver prioritized UX findings. For each: the problem, who it hurts, and a
specific redesign recommendation. Include quick wins and structural changes
separately.
```

---

## Section C — Attach docs 01–08 when reviewing

**Every reviewer must receive the full spec set as attachments.** A prompt alone is not enough — the models need the actual specifications to review. Attach:

- **01–07** — the vision, PRD, architecture, data model, API, workflow, and UX docs (the ChatGPT source-of-truth and its derived specs).
- **08 — `08-Zoho-WATI-Integration.md`** — the integration contracts (WATI + Zoho), including the ~33% delivery-failure reality, the opt-in rule, and the compliance gate.

If a model can't accept all attachments at once, paste Section A (the one-page context) first, then attach docs in order, then send the prompt. **Do not** ask a model to review "from memory" of Section A alone — the value is in reviewing the real specs.

---

## Section D — Reality-check items reviewers MUST weigh

These three are non-negotiable. Any review that ignores them is incomplete — call it out and re-run.

1. **The reCAPTCHA / "account-opened-only-from-Zoho" boundary.** Zerodha's form is reCAPTCHA-gated and lead-capture-only; it cannot be auto-submitted, and full account opening is a separate human-assisted step. **GoRefer can never auto-complete an account and must never fabricate account-opening or reward status — that data comes only from Zoho.** Reviewers must not propose any "automate the signup" shortcut; they should pressure-test whether the human-in-the-loop (Ashok) design is robust and scalable.

2. **The ~33% WATI delivery failure.** One in three campaign messages currently fails to deliver (spiking to ~60% in bad windows), caused by no opt-in, all-Marketing template classification, and duplicate sends across 4 Zoho modules. **This leaks the funnel at step zero.** Reviewers must weigh whether GoRefer's launch is even viable before this is fixed (dedup + opt-in-aware audience), and whether the design makes it worse or better.

3. **SEBI/NSE AP compliance obligations.** Every asset must carry the AP disclosure block and market-risk warning, pass the NSE Code of Advertisement (NSE/COMP/55482) and the SEBI Feb-2026 social-media circular, and be run through the compliance skill before publishing. The "10% brokerage-share" claim is **live but revocable** (rests on an abeyance order) and must live in a single swappable place. The form must not misrepresent Zerodha's brand. Reviewers must treat compliance as a hard gate, not a nice-to-have.

---

## Section E — Review Matrix template + consolidation steps

### E1. The Review Matrix

Collect every suggestion from every model into one table. One row per distinct suggestion.

| # | Suggestion | Source | Category | Decision | Reason |
|---|-----------|--------|----------|----------|--------|
| 1 | *(the concrete suggestion)* | Claude / Grok / Gemini | Architecture / Product / UX / Compliance / Delivery | Accept / Reject / Defer / Modify | *(why — 1–2 lines)* |
| 2 | | | | | |
| 3 | | | | | |

- **Source** — which model raised it (a suggestion raised by ≥2 models independently is a strong signal; flag those).
- **Category** — Architecture, Product/Growth, UX, Compliance, Delivery/WATI, Data/Zoho.
- **Decision** — Accept / Reject / Defer (to a later sprint) / Modify.
- **Reason** — the rationale, so the decision is auditable later and not re-litigated.

### E2. Step-by-step process

1. **Send** each prompt (Section B) + docs 01–08 (Section C) to its model — Claude, Grok, Gemini — in three separate conversations.
2. **Collect** each model's full response verbatim; save each as `review-claude.md`, `review-grok.md`, `review-gemini.md` in the GoRefer folder.
3. **Paste** every suggestion into the Review Matrix (E1), one row each. De-duplicate near-identical suggestions but keep the Source list (note when multiple models agreed).
4. **Decide** each row (Accept / Reject / Defer / Modify) with a one-line reason. Prioritize any suggestion touching the three reality-check items (Section D).
5. **Consolidate** all Accepted/Modified suggestions into the specs — producing **v1.1** of the affected docs (01–08). Record the matrix itself as the decision log.
6. **Freeze.** Once v1.1 is consolidated and the matrix is complete, **freeze the specs** and hand to Claude Code for Sprint 1 implementation (doc 10). No further architecture changes without a new review cycle.

> **Rule of thumb:** if all three models independently flag the same problem, treat it as Critical and fix it before freeze. If only one model raises it and it conflicts with a locked decision (Build-Spec §5), default to the locked decision unless the reviewer surfaced genuinely new information.

---

*Session: Cowork, 2026-07-04. Context grounded in `GoRefer-Context-Brief.md`, `GoRefer-Build-Spec-Cowork-Decisions.md`, `GoRefer-Master-SourceOfTruth-from-ChatGPT.md`, and `08-Zoho-WATI-Integration.md`.*
