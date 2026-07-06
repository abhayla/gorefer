# GoRefer Constitution

**Document 03 of the GoRefer Architecture Repository.**
**Owner:** Abhay Kumar Maurya / PIFS (AI-assisted). **Status:** Working draft (Constitution v1). **Last updated:** 2026-07-04.

> These are the non-negotiable engineering principles for GoRefer. **Every future feature, design decision, and pull request is checked against this document.** If a proposal violates a principle, either the proposal changes or the principle is amended by an explicit ADR — never silently. The principles are drawn from the captured Constitution v1 and the GoRefer product principles in the master source-of-truth doc, and from the decisions recorded in Document 02 (ADRs).

---

## 1. Build once, scale forever
Every architectural decision today must support future referral programs without a redesign. Sprint 1 enables only Zerodha, but nothing is built in a way that would have to be torn up to add Groww, insurance, mutual funds, or property. When in doubt, choose the option that generalises.

## 2. Platform, not project — provider-agnostic by default
No component is named or designed as Zerodha-only. `ReferralProgram` is acceptable; `ZerodhaReferral` is not, unless it is an explicit plugin/adapter. The platform stays provider-agnostic even while Sprint 1 supports a single partner. Adding a partner should be configuration (see Principle 3), not core-code surgery.

## 3. Configuration over code
Onboarding a future referral program should require configuration wherever possible, not application-code changes. Partner-specific values (codes, URLs, landing copy, reward wording) live in configuration and data, not hardcoded in logic. No hardcoded partner logic in the core.

## 4. Expose only today's capabilities — no "Coming Soon"
Never show a feature the user cannot use today. No "Coming Soon," placeholder menus, disabled buttons, or dead links. The UI reflects only what actually works now; unfinished capabilities sit behind feature flags until they are real. Architecture may be built for tomorrow, but the interface exposes only today.

## 5. Measure everything observable
Capture every observable business event — link created, link shared, link clicked, landing-page viewed, redirect initiated, lead created, and every future equivalent. If GoRefer can observe it, GoRefer records it. What is not measured cannot be improved.

## 6. Analytics are built from events, not summaries
All reporting is derived from the immutable event stream, never from pre-computed counters. A new metric is a new query over existing events, not a schema change or a backfill (ADR-004). "Collect everything now, visualise it later."

## 7. Events are immutable
Recorded events are append-only and never edited or deleted in place. Corrections are new events. This preserves the audit trail, keeps analytics trustworthy, and makes every referral journey a faithful history (ADR-007).

## 8. Never fabricate data
GoRefer reports only facts it can verify. It CAN verify click and redirect timestamps. It CANNOT independently verify whether Zerodha completed KYC or approved an account — those originate only from external systems (Zoho). Downstream status is always attributed to its source and never asserted by GoRefer on its own (ADR-013).

## 9. Clear system ownership — GoRefer owns referral intelligence, Zoho owns sales, WATI owns messaging
Business/referral logic lives in GoRefer; lead management and the sales pipeline live in Zoho CRM; WhatsApp messaging, templates, and campaigns live in WATI. GoRefer orchestrates the three. No system duplicates another's authority (ADR-006).

## 10. Never expose internal logic
Users never see Zerodha URLs, partner codes, or database IDs. Public referral links carry the customer's raw Zerodha `client_id` in the path (`gorefer.in/r/{client_id}`) — there is no opaque token and no token→id mapping DB; the partner code `ZMPHZC` is injected server-side and never appears in the shared link (ADR-001). People interact with GoRefer surfaces only; the plumbing stays hidden.

## 11. Mobile-first
Designed for the phone as the primary device, not merely responsive. Most referrals begin on WhatsApp on mobile, so every screen, share affordance, and flow is optimised for mobile first and adapted to desktop second (ADR-003).

## 12. Zero friction — one primary action per screen
Remove every possible click. Each screen answers exactly one question and makes the next step obvious. Prefer one-tap Share/Open over copy-pasting long links or scanning a QR on the same phone. GoRefer should feel like a wizard, not software. Always offer the user a choice of paths (share link / share friend's contact / contact an advisor), but keep one action primary.

## 13. Automation first; human assistance only where it adds value
Before any manual step, ask "can software do this?" — if yes, automate it. Humans are reserved for what genuinely needs them: trust, guidance, and edge cases (KYC doubts, first-time investors, complex queries). In the referral flow, automation captures and routes the lead; a human completes the Zerodha account opening on a call.

## 14. Every referral program plugs into the same architecture
One permanent referral link per user per program; every program uses the same journey model, event model, landing-experience pattern, and dashboard structure. Channel analytics come from share events, not from proliferating links (ADR-010). A new program reuses the machinery rather than adding a parallel one.

## 15. Security by default
Opaque/signed links where appropriate, no exposed client IDs, rate limiting, audit logs, encryption for sensitive data, and least privilege — built in from the start, not bolted on later. Authentication and data scoping are role-aware from day one (ADR-009, ADR-011).

## 16. Compliance is non-negotiable
Every public asset carries the SEBI/NSE AP disclosure block and the market-risk warning, and passes the `zerodha-ap-social-media-compliance` review before it ships. GoRefer forms must never clone or resemble Zerodha's page (misrepresentation risk under NSE/COMP/55482); they are clearly PIFS-branded. The revocable "10% of brokerage" claim lives in a single, swappable place. Compliance is enforced in the pipeline, not left to memory (ADR-014).

---

*Constitution v1. Amendments to any principle require an explicit ADR in Document 02 recording the reason. Referenced by Documents 01 (Foundation), 02 (ADRs), and every implementation guide.*
