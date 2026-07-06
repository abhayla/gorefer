# GoRefer

> **Building GoRefer?** Start with [`CLAUDE.md`](./CLAUDE.md) — the operating manual and entry point for Claude Code. It maps the docs, states the non-negotiable guardrails, and defines the Sprint 1 build order.
rals through multi-channel campaigns (WhatsApp/WATI + Zoho CRM), with AP compliance built in. This repository holds the **Sprint 1** design — a deliberately extensible foundation — authored with AI assistance. The documents below are the single source of truth; the raw ChatGPT/working material that seeded them is preserved under `_source-archive/`.

## Document Map

| Area | Document | Path |
|------|----------|------|
| Foundation | Foundation Specification | [docs/foundation/01-GoRefer-Foundation-Specification.md](docs/foundation/01-GoRefer-Foundation-Specification.md) |
| Foundation | Constitution | [docs/foundation/03-GoRefer-Constitution.md](docs/foundation/03-GoRefer-Constitution.md) |
| Architecture | Architecture Decisions (ADR) | [docs/architecture/02-Architecture-Decisions-ADR.md](docs/architecture/02-Architecture-Decisions-ADR.md) |
| Architecture | System Architecture | [docs/architecture/04-System-Architecture.md](docs/architecture/04-System-Architecture.md) |
| Database | Database Design | [docs/database/05-Database-Design.md](docs/database/05-Database-Design.md) |
| API | API Specification | [docs/api/06-API-Specification.md](docs/api/06-API-Specification.md) |
| UI/UX | UI/UX Specification | [docs/ui-ux/07-UI-UX-Specification.md](docs/ui-ux/07-UI-UX-Specification.md) |
| Integrations | Zoho + WATI Integration | [docs/integrations/08-Zoho-WATI-Integration.md](docs/integrations/08-Zoho-WATI-Integration.md) |
| Workflow | Referral Workflow & Edge Cases | [docs/workflow/11-Referral-Workflow-and-Edge-Cases.md](docs/workflow/11-Referral-Workflow-and-Edge-Cases.md) |
| Workflow | Resolved Gaps & Edge-Case Decisions | [docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md](docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md) |
| Review | LLM Review Pack | [review/09-LLM-Review-Pack.md](review/09-LLM-Review-Pack.md) |
| Review | Review Bundle (full concatenation) | [review/GoRefer-Review-Bundle.md](review/GoRefer-Review-Bundle.md) |
| Implementation | Claude Code Implementation Guide | [implementation/10-Claude-Code-Implementation-Guide.md](implementation/10-Claude-Code-Implementation-Guide.md) |
| Decision | Framework/Stack Decision & Synthesis (basis of ADR-024) | [review/Framework-Decision-Synthesis.md](review/Framework-Decision-Synthesis.md) |
| Design | UI Mockups (landing, dashboard, components, journey, etc.) | [mockups/](mockups/) |
| Source | Original ChatGPT/source & superseded drafts | [_source-archive/](_source-archive/) |

## How to use for external LLM review

To have another LLM review the design, feed it [review/GoRefer-Review-Bundle.md](review/GoRefer-Review-Bundle.md) (the full concatenated spec) as context, then apply the questions and rubric in [review/09-LLM-Review-Pack.md](review/09-LLM-Review-Pack.md).

## Notes

The numbered documents (01–12) cross-reference each other by their number and name (e.g. "see 05-Database-Design"). Those references are unchanged; every target is listed with its new path in the table above. `_source-archive/` holds raw and superseded material (ChatGPT transcripts, context/build/resume briefs, master source-of-truth, and the previous `00-README.md`) kept for provenance — not part of the active spec.
