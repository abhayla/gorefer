# GoRefer — Documentation Repository

**Owner:** Abhay Kumar Maurya / Passive Income Financial Solutions Private Limited (PIFS) — AI-assisted.
**Status:** Working draft.
**Last updated:** 2026-07-04.

---

## What GoRefer is

GoRefer is a referral-management and referral-intelligence platform for PIFS, a Zerodha Authorised Person (NSE AP `AP2516003693`, partner code `c=ZMPHZC`). It sits between WhatsApp/WATI and Zerodha's public signup flow: it mints a short, opaque, trackable referral link for every customer, captures each lead in PIFS's own systems *before* handing a real human off to Zerodha's reCAPTCHA-gated form, records every observable event (share, click, landing-page view, redirect) as immutable data, and enriches the referral journey with lead and account status pulled from Zoho CRM. Zerodha remains the underlying broker; GoRefer is the orchestration and intelligence layer. It is built as a scalable product from day one — Sprint 1 exposes only the Zerodha flow, but the architecture is provider-agnostic so future partners (Groww, insurance, mutual funds, property) plug into the same design without a redesign.

---

## Document list

| # | Document | Purpose |
|---|----------|---------|
| 00 | **README** (this file) | Repository index and how to use it |
| 01 | **GoRefer Foundation Specification** | Product/business vision, principles, functional & non-functional requirements, user journeys, scope |
| 02 | **Architecture Decision Records (ADRs)** | Every significant decision (ADR-001..ADR-014) with context, alternatives, decision, reasoning, consequences |
| 03 | **GoRefer Constitution** | The non-negotiable engineering principles every future feature must follow |
| 04 | **System Architecture** | Components, orchestration model, request/redirect flow, deployment topology |
| 05 | **Database Design** | PostgreSQL schema — referrals, tokens, journeys, events, configuration |
| 06 | **API Specification** | Endpoint contracts, request/response shapes, stable REQ/endpoint IDs |
| 07 | **UI/UX Specification** | Wizard-style screens, mobile-first flows, one-action-per-screen wireframes |
| 08 | **Zoho–WATI Integration** | Lead sync, phone resolution, template dispatch, opt-out handling |
| 09 | **LLM Review Pack** | Machine-readable context for AI design review (Claude/Grok/Gemini) |
| 10 | **Claude Code Implementation Guide** | How Claude Code should build against these specs (CLAUDE.md, DoD, standards) |

Documents 00–03 exist in this working draft. Documents 04–10 are planned skeletons from the original starter pack and are assembled incrementally as design freezes.

---

## Source of truth

The raw decision log this repository is **derived from** is [`GoRefer-Master-SourceOfTruth-from-ChatGPT.md`](./GoRefer-Master-SourceOfTruth-from-ChatGPT.md) — the origin vision captured across 37 "Additions" including ADR-001..ADR-012. Two companion capture docs refine and ground it against live testing:

- [`GoRefer-Build-Spec-Cowork-Decisions.md`](./GoRefer-Build-Spec-Cowork-Decisions.md) — the 2026-07-04 Cowork session: locked decisions, the verified Zerodha link behaviour, and the mandatory compliance layer the origin doc omitted.
- [`GoRefer-Context-Brief.md`](./GoRefer-Context-Brief.md) — the consolidated, sourced brief of everything already decided vs genuinely open.

Where this repository and the master capture doc disagree, the ADRs in Document 02 record the reconciliation explicitly (see especially ADR-001 and ADR-013).

---

## How to use this repo

1. **Start with 01 (Foundation Specification)** for vision, scope, and requirements — the "what and why."
2. **Read 03 (Constitution)** before proposing or building any feature — these principles are non-negotiable and every design is checked against them.
3. **Consult 02 (ADRs)** before revisiting any settled decision. Each ADR records the reasoning and consequences, so a future change can be weighed against the original intent rather than relitigated from scratch.
4. **Use 04–08** for implementation detail once a design area is frozen.
5. **Run the compliance gate** (Abhay's `zerodha-ap-social-media-compliance` skill) on every public asset before it ships — this is a hard requirement, not advisory (see ADR-014).
6. **Never fabricate data.** GoRefer reports only events it can verify; account-opening and reward status come solely from Zoho (see ADR-013).

Requirements carry stable IDs (REQ-001…) and decisions carry ADR IDs (ADR-001…) so that Claude Code and future AI tools can navigate and implement consistently.
