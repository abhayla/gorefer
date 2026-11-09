# S2-06 — Referral Daily Report (per-AP admin + GoRefer super-admin)

> **Status:** DESIGN — requirements being captured with the owner (started 2026-11-09). Nothing built.
> Decisions are recorded here the turn they are given (spec-first R4).

## Ask (owner, 2026-11-09)

A page where referrals are shown **date-wise in a table** with full per-referral detail and filters
(partner, date, number of referrals, …). An AP's admin sees only that AP; the GoRefer admin sees all APs.

## What exists (verified 2026-11-09)

- `/admin-panel/` dashboard: headline KPIs + funnel from `DailyMetric` (per day × program) — no per-day table.
- `/admin-panel/explorer/`: one row per referral link, lifetime counts, filters source / stage / client-id
  search — no date column, no date-range filter, no export.
- Journey detail + referrer profile pages.
- Access: one `is_staff` gate; no user↔tenant binding, no roles (doc 05 §5 roles are spec-only).

## Decisions

| ID | Decision | Basis |
|---|---|---|
| RDR-1 | "A Zerodha partner" = an **Authorised Person firm (AP) = tenant** (PIFS is AP #1). An AP admin sees only their AP; a GoRefer super-admin sees all APs. | Owner 2026-11-09 Q1; confirms ADR-036 (tenant = AP). |
| RDR-2 | Scope = **the date-wise report + two login roles** (super-admin = all APs; AP admin = own AP only). AP #2 onboarding and the ADR-041 migrations stay in the separate multi-AP mission. Today the super-admin sees 1 AP (PIFS). | Owner 2026-11-09 Q2; ADR-041, doc 13 §5. |
| RDR-3 | One row per day; **every funnel stage is its own column**: non-bot clicks, landing opens, leads, accounts opened (dated by the TRUE Zoho opening date, non-reversed). | Owner 2026-11-09 Q3; ADR-017, CLAUDE.md §4, `DailyMetric`. |
| RDR-4 | The GoRefer super-admin sees **full detail (name, mobile, IP, city) for every AP's referrals**, unmasked. An AP admin sees full detail for their own AP only. *Implication (engineer note):* AP onboarding terms must tell each AP that the platform operator can see their prospects' data (DPDP transparency); this is a later onboarding task, not this feature. | Owner 2026-11-09 Q4; spec previously silent (searched: super_admin, platform admin, cross-tenant). |
| RDR-5 | Mock-up **approved as-is** (artifact TfNLUXZ1QfMZtMSuXE5duM, 3 screens): daily table (split by AP for super-admin), one-day detail of every lead/account with full PII, AP-admin own-AP view, CSV export on both, filters = date range/presets, AP (super-admin only), referrer, source, channel, stage reached, min leads per day, group by day/week/month. A person appears on **every day they did something** (click, lead, account). | Owner 2026-11-09 Q5. |

| RDR-6 | "Clicks with no form" is built **exactly**: from deploy day, every new lead event stores the `visitor_id` of the browser that submitted the form, and the tab lists that day's counted clicks whose visitor has no lead. Days before the deploy can't be matched (the link was never stored), so they show **all clicks with a one-line note**, never a guess. | Owner 2026-11-09 Q6; ADR-018 (first-party `visitor_id` cookie); review finding M1 (lead event had no visitor id). |

**Engineering notes (information):** city on lead/account rows comes from the Prospect record; the channel
filter on people uses clicks on that person's referral link **within the selected period**, non-synthetic; the
channel list is built from `SHARE_CHANNEL_LABELS` (all configured channels + "none"); "Journey →" shows for the
super-admin only (the journey page is super-admin only). Known limit with one AP, revisit at AP #2: in the
all-APs view a client id present in two APs shares one name and counts once in "active referrers".

## Behaviour (as approved)

- **Daily table** — one row per IST day (or week / month), per AP when "split by AP" is on. Columns:
  clicks (non-bot, non-synthetic — same rule as the explorer), landing opens, leads (non-deleted `Lead`
  rows, by created date), accounts opened (non-reversed `Conversion`, by TRUE `account_opened_at`),
  active referrers (distinct referrer client ids with ≥1 counted click that period; total row = distinct
  over the whole range), lead rate = leads ÷ clicks. Total row at the bottom. Every column sorts.
- **Filters** — date presets (today, last 7, last 30, this month) + custom from/to (IST); AP (super-admin
  only, never rendered for an AP admin); referrer (client id or name contains); source (referral link /
  partner-direct / off-platform); channel (`Event.metadata["channel"]`: wa / tg / x / none); stage reached;
  "leads per day, at least N" (hides periods below N); group by day / week / month.
- **One-day detail** — every person who became a lead or had an account opened that day: time, AP,
  referrer (client id + name), person name, mobile, city, source · channel, what happened that day,
  furthest stage, Zoho status, link to the existing journey page. Second tab: clicks with no form that day
  (time, AP, referrer, channel, city, device; no name, because none exists).
- **CSV export** — of exactly the rows on screen with the active filters (daily table and day detail).

## Access (engineering decisions, recorded as information — not owner questions)

- **Structural gate (run-discipline B8):** a **super-admin** is a staff user with `is_superuser=True`
  (the bootstrap admin already is, `bootstrap_admin.py:39`, so nothing changes for the owner). An **AP admin**
  is a staff user with exactly one `StaffTenantBinding(user → tenant)` row (one-to-one). Staff with neither
  is **denied** (fail closed, never silently promoted). A superuser with a binding is treated as AP admin
  (the narrower scope wins). Pre-deploy check: count prod staff users that are not superusers and have no
  binding — they lose admin access on deploy.
- The new report pages scope **every** query by the user's binding (AP admin) or by the chosen AP filter
  (super-admin). An AP admin's scope ignores any `?ap=` parameter — it is never read from the request.
- **All existing admin pages** (dashboard, explorer, preferences, verifications, campaigns…) become
  **super-admin only**: they resolve the tenant from the domain, so an AP-bound user there could read
  another AP's data. The gate lives in the shared `_staff_required` decorator, so no page can be missed.
  When AP #2 is onboarded (multi-AP mission), those pages get their own per-AP scoping.
- AP admin accounts are created by the super-admin through the existing Django admin (`/django-admin/`);
  no new user-management screen (none was asked for).
- Not in scope: AP #2 onboarding, the ADR-041 partner-code move and `(tenant, mobile)` lead key — those
  stay the multi-AP mission's first migration.
