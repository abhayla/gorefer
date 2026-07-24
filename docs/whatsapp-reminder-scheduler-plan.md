# WhatsApp Reminder / Follow-up Scheduler — SUPERSEDED

> **This plan is superseded. The canonical, doc-13-aligned design is:**
> **[`docs/architecture/14-24h-Window-Followup-Engine.md`](./architecture/14-24h-Window-Followup-Engine.md)**
>
> That architecture doc corrects two errors in this earlier draft:
> 1. "Partner group" here meant partner *segments* — wrong. Per doc 13 (ADR-036) the ratified
>    "Partner Group" is the regulatory *category* (brokers/insurance/loans); the real per-partner
>    config unit is **AP = tenant**, resolved through the existing `apps/config` cascade.
> 2. This draft proposed building a `PartnerGroup` model now — doc 13 §5 forbids speculatively
>    building the hierarchy. Doc 14 keeps Phase 1 **tenant-scoped** (buildable now) and defers the
>    partner-group / partner tiers to the multi-AP mission (model-only).
>
> Kept only as the historical record of the design's evolution. Do not build from this file.
