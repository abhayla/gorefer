# GoRefer — Tech-Stack Evaluation Prompt (for external LLM review)

> Copy everything below the line into ChatGPT / Gemini / Grok. It is self-contained.

---

You are a pragmatic principal engineer advising a **solo, non-full-time founder**. Recommend the best technology stack (backend framework, frontend approach, and how they fit together) for the project below. Weigh **solo-maintainability, build velocity, performance, and fit for the multi-tenant SaaS future** above novelty. Give a clear recommendation with honest trade-offs, and name your second choice.

## What the product is
**GoRefer** is a Referral Management & Referral Intelligence platform. Users manage, share, and track referral links from partner businesses through one system, and GoRefer records the full referral lifecycle (create → share → click → landing → redirect → lead → account/reward) as an **immutable event stream**. It does **not** own any referral program — it integrates with programs run by partners. Sprint 1 enables exactly ONE program (an Indian stock-broker referral), but the architecture must be **provider-agnostic** (future partners: other brokers, insurance, mutual funds, loans) via configuration, not a rebuild.

## Core functional requirements (Sprint 1)
1. **Redirect service (hottest path):** `GET /r/{id}` → validate the id → lazily create referrer+journey+click on first click → log a click event → HTTP 302 to a partner signup URL with a partner code injected server-side. Must be low-latency; must never block on slow writes; must never auto-submit the partner form.
2. **Branded, mobile-first landing/capture page** (most traffic arrives from WhatsApp on cheap Android phones on slow networks — page must be light and fast). A short lead-capture form (name, email, mobile) that saves the lead first, then redirects.
3. **Event-sourced analytics:** every observable event stored as an immutable row; all reporting derived from the event stream; daily/monthly rollup tables via background workers.
4. **Admin dashboard:** funnel analytics, top-referrer leaderboard, lead list + statuses, sync-freshness indicators. Internal, low-traffic, CRUD-heavy.
5. **Integrations (adapters behind interfaces):** a CRM (Zoho) as the single source of truth for conversions (webhook + polling), and a WhatsApp Business API (WATI) for notifications. Both behind feature flags.
6. **Compliance rendering:** a mandatory legal disclosure + risk-warning block auto-injected into every page and asset, non-removable (regulated financial context).
7. **Config-over-code:** a 3-tier config cascade (platform default → org/admin → user) governs values like display fields, incentive text, partner settings.
8. **Admin-only auth in Sprint 1** (single admin, bootstrapped from env); customer login is later.

## Future requirements (design for, don't build yet)
- **Multi-tenant SaaS:** other independent partners (agents/distributors) each use GoRefer to manage their own referral networks — hard cross-tenant data isolation, per-tenant config/branding/compliance, a pricing model.
- **Customer-facing "My Referrals" dashboard** (Sprint 2+): potentially richer/interactive per-user UI.
- More partner programs via config; possibly a poster/PDF asset generator; possibly a mobile app much later; multi-language (Hindi/English).

## Hard constraints & decisions already locked
- **Database: PostgreSQL** (locked).
- **Runtime: a single, central application + one database — NO edge/distributed/serverless-edge** (locked for the current scale; edge deliberately deferred). Reliability via managed DB + backups + standby + health check.
- **Solo founder who is fluent in Python** (writes data/scraping scripts, Zoho Deluge, shell) and must be able to read, debug, and extend the whole codebase alone. Minimizing the number of languages/runtimes is a strong plus.
- **Config-over-code, provider-agnostic naming** (no partner name hardcoded in files/tables/routes), typed contracts preferred (the CRM payloads have strict field semantics that must not be confused).
- API-first (every feature exposes an API before a UI).

## Performance / scale criteria (be realistic — do not over-engineer)
- **Today:** ~250–1,000 referral clicks/day (stated minimum 250). Peak burst if a full broadcast clicks within one minute ≈ **~4 requests/second**.
- **Event volume:** ~6 event rows per journey → ~0.5–3 million rows/year.
- **Growth headroom:** should comfortably handle ~100× (up to ~25,000 clicks/day) without a re-architecture; beyond ~1M clicks/month, revisiting edge is acceptable.
- **Redirect latency** should be low (tens of ms server-side) but the redirect immediately hands off to a third-party site, so shaving the last 20–50ms is not worth architectural complexity.
- Postgres at this volume runs at a tiny fraction of capacity; raw throughput does **not** force the choice.

## Candidate stacks to evaluate (add others if better)
- **Python + Django** (Django templates / DRF; built-in admin, auth, ORM, migrations; multi-tenancy libraries).
- **Python + FastAPI** (async, API-first, Pydantic typing; thin server-rendered UI via Jinja + HTMX + Tailwind).
- **Node/TypeScript** (NestJS/Express backend + React/Next.js frontend; one language front+back).
- **Next.js full-stack** (React + API routes + Prisma).
- **Go** (Gin/Echo) for the backend.
- **Ruby on Rails / Laravel** (batteries-included rapid app dev).

## What to deliver
1. A **recommended stack** (backend framework + frontend approach) with a crisp justification tied to the criteria above.
2. **Your second choice** and exactly when you'd pick it instead.
3. A short **trade-off table** across the candidates (maintainability-for-a-solo-Python-dev, build velocity for Sprint 1, performance/fit for the redirect + event volume, multi-tenant SaaS fit, richness for a future customer dashboard, typing/contract safety, ecosystem/hosting fit with a central Postgres app).
4. Any **risks or gotchas** with your recommendation and how to mitigate them.
5. A recommendation on **server-rendered (templates + HTMX) vs a React/SPA frontend** for Sprint 1, given the mobile-first, slow-network, forms-plus-internal-dashboard reality — and how to keep the door open to a richer customer SPA later.

Be direct. Assume the founder will actually maintain this alone. Do not recommend microservices, Kubernetes, or edge unless you can justify it at ~4 req/s.
