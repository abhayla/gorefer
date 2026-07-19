# Parallel Execution Plan — Zerodha go-live (break the serial bottleneck)

> **Why this exists (2026-07-15):** progress is serial — nearly everything funnels through ONE Claude Code session + Abhay's one-at-a-time Zoho UI pastes, while the DA mostly advises. The work isn't slow; the serialization is. This splits it into independent lanes that run at the same time. Companion: `Zerodha-GoRefer-GoLive-Roadmap.md` (phases), `COORDINATION.md`.

## The bottleneck, named
1. One Engineer (Claude Code) session does all authoring + running.
2. Abhay hand-relays prompts and pastes Deluge one rule at a time (round-trips).
3. The DA (Cowork) advises but doesn't take executable load off the Engineer.

## Three levers to parallelize
1. **Spin a SECOND Claude Code session** dedicated to the GoRefer Django app (Lane D). Different codebase → zero conflict with the Wati/Zoho session.
2. **DA (Cowork) takes all MCP-doable work** — Zoho config/records/fields writes, COQL + Wati verification, monitoring, template drafting, doc sync — off the Engineer's plate.
3. **Batch Abhay's UI actions** — collect all pending pastes / disabled-copies / schedule edits into ONE Zoho sitting instead of per-step round-trips.

## The lanes (run simultaneously)
| Lane | Tasks | Owner | Gate / blocked by |
|---|---|---|---|
| **A — Finish queue coverage** | Author + paste **leads** + **2 OfficeVisitors** note-writers (disabled copies); replicate the real Wati **send block** to contacts/leads/welcome/officevisitor gatekeepers | Engineer #1 authors → Abhay **batch-pastes** | none (independent of going live on the ready 3) |
| **B — Exact-time schedules** | Reconfigure referrers/contacts/leads Schedules → **daily 10:30 / 12:00 / 19:00**; confirm org tz = IST | Abhay (UI) | none — **do now** |
| **C — Go-live the ready 3** | Confirm welcome live-send delivers → flip `dry_run=false` + widen allowlist for **Referrer + Contact + Welcome** (partial go-live; don't wait for leads/officevisitor) | Engineer #1 + Abhay decision | welcome send-block verified |
| **D — GoRefer P3 (Django)** | Sandbox-verify `ENABLE_ZOHO_READ` (DONE, green). **Build WRITE-on Model 2**: live Zoho write adapter as an UPSERT keyed on normalized mobile (never blind-create), journey-id stamped on the lead; behind `ENABLE_ZOHO_WRITE`. Flags: `ENABLE_WATI_SEND` → `ZOHO_WRITE` → `ZOHO_READ` (**WRITE now ON by design — supersedes DF-9, Abhay+DA 2026-07-15**) | **Engineer #2 (2nd session)** | READ done; WRITE-upsert is a build; prod flip waits on P1 + Zoho Mobile-dedup rule |
| **E — Monitoring + baseline** | Extend `wati-referral-send-monitor` to watch queue health (stuck PENDING, fail-code mix); capture before/after delivery snapshots | **DA (me)** | none — now |
| **F — UTILITY templates** | Submit the UTILITY welcome templates to Meta (long lead ~days); config-swap `rule_template_map` on approval | DA draft → Engineer submit → Meta | none — **submit now, bakes in background** |

## Dependency reality (why these don't collide)
- A, B, E, F have **no dependency on each other** → fully parallel today.
- C needs only the welcome send-block verified (a small piece of A) — not the leads/officevisitor conversions. So the **ready 3 can go live while A finishes the rest.**
- D is a **different codebase** (Django) → a second session works it with zero conflict; only the final *flip* waits on P1 being stable (a day or two), not on P1 being 100% converted.

## Parked (do NOT parallelize now — post-go-live)
Astra AI agent · activation journey / nudge engine · welcome quick-reply buttons + Wati reply flow · `build-wati-automation` rollout. Reintroducing these now re-splits focus off go-live.

## Immediate starts (today, at the same time)
- **Abhay:** Lane B (schedules) now; batch Lane A pastes when Engineer #1 hands the `.dg` files.
- **Engineer #1 (Wati/Zoho session):** Lane A authoring + Lane C send-block verify.
- **Engineer #2 (new GoRefer session):** Lane D.
- **DA (me):** Lane E now + Lane F draft/route.
