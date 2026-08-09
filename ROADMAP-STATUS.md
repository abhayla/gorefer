# GoRefer — Feature Roadmap & Status

> **As of 2026-08-09 (Tier-A train complete).** Grounded in `COORDINATION.md` (DA⇆Engineer log), `CLAUDE.md`, `CURRENT-STATE.md`, `review/Deferred-Features-Backlog.md`, `docs/sprint2/`, and the `main` git history. Status vocabulary: **Discussed** (spec'd only) · **Implemented** (code+tests merged, not yet in prod) · **Deployed** (on `main` and running at gorefer.in). **For live flag/deploy state, `CURRENT-STATE.md` is the maintained snapshot — this file's headline is refreshed on milestones only** (the stale 07-13 headline here corroborated the 2026-07-21 wrong-state incident; hence the split).

## Deploy headline

GoRefer is **LIVE in production AND live-integrated** at **https://gorefer.in** — Hostinger VPS `72.61.240.224`, Cloudflare proxied, live since 2026-07-09. Deployed SHA **`14eb2f7`** (2026-08-08 13:05 IST per `CURRENT-STATE.md`; `main` tip `e4fbeeb` — PR #124 hub copy + preview card — was reported merged-to-prod the same evening but is **not yet verified live from this ledger's session**; treat `CURRENT-STATE.md` + the verify-live commands as truth). All three integration flags (`ENABLE_WATI_SEND`, `ENABLE_ZOHO_WRITE`, `ENABLE_ZOHO_READ`) are **ON** via cascade overrides (never judge from `.env`). Referrer login (`ENABLE_CUSTOMER_LOGIN` + `ENABLE_OTP_LOGIN`), share intent (`ENABLE_SHARE_INTENT`), follow-ups (`followups_enabled`), records magic link (`ENABLE_RECORDS_LINK`), and the share hub (`ENABLE_SHARE_HUB`) are all **ON**. The Zoho conversion push pipe is LIVE end-to-end (Contacts workflow rule + HMAC signer, P0-A closed 2026-08-06) with the ~15-min reconciler as safety net. Daily instruments: the 21:00 IST WA engagement digest (T-032…034, via the shared Notifier gateway) and the 21:30 IST three-sided delivery+funnel report (O-6a/R-DRR, `Wati-Project/daily_report.py`).

---

## Sprint 1 — Foundation (the referral pipe)

| Feature | Status | Remarks |
|---|---|---|
| **M1 — Repo/skeleton, config + feature-flags, env-bootstrap admin** | Deployed | Django+Ninja+HTMX+Tailwind+Postgres; single-schema `tenant_id` isolation from day 1; seeded Zerodha/ZMPHZC program. |
| **M2 — `/r/{client_id}` redirect + lazy journey + click event** | Deployed | Validate→log click→302 with `c=ZMPHZC` injected server-side; `/open` partner-direct; bot-UA filtering. This is the core live pipe recording clicks. |
| **M3 — Branded landing + capture form + two buttons** | Deployed | PIFS-branded, saves lead first; Continue→Zerodha, Share→wa.me to WATI number; disclosure + consent baked in. |
| **M4 — Analytics / journey / funnel rollups** | Deployed | Read-only aggregation, daily/monthly rollups; unique/human counts labelled approximate; never fabricates conversions. |
| **M5 — WATI hooks (3 lead-time notifications)** | Deployed — flag ON (~17-Jul) | Live adapter, allowlist open. Terminal-status verification, dedup, opt-in aware. |
| **M6 — Zoho lead + status sync** | Deployed — flags ON (~17-Jul); webhook + HMAC live (18-Jul); **real push pipe live 2026-08-06 (P0-A)** | Status only ever from Zoho. The Contacts workflow rule + Deluge signer now push conversions within seconds; `zoho_reconcile_conversions` (~15-min sweep, 4919036) is the backstop. True-opening-date honoured (ADR-017). |
| **M7 — Admin dashboard / referral explorer / journey detail** | Deployed | Read-only KPIs from rollups, filters, conversion side-panel; PII masked. N+1 + pagination fixed by T-046. |
| **M8 — Hardening + independent verification endgame** | Deployed | Adversarial E2E vs the Acceptance Test Plan; compiled CSS + vendored HTMX; fresh-agent verification. |
| **M9 — Zoho-READ enrichment + Referral Profile + Variant C re-skin** | Deployed — READ flag ON (~17-Jul) | `/admin-panel/referrer/{client_id}/`; whole-app Variant C · Cobalt. |
| **M10 — Postgres-only hardening** | Deployed | Postgres sole engine dev/test/CI/prod with fail-fast guard. |

---

## Sprint 2 — Share amplification, login, follow-ups (WhatsApp/Wati-first)

### Shipped up to 2026-07-21 (as previously recorded)

| Feature | Status | Remarks |
|---|---|---|
| **M11 — OG preview card + `?s=` share-channel capture** | Deployed | WhatsApp preview card; share channel recorded then stripped; crawler ≠ click. Real generated preview card landed with PR #124 (see below). |
| **B1 — `/r/{channel}/{client_id}` channel-prefix links** | Deployed | e.g. `/r/wa/RJ4521`; legacy `?s=` retained. |
| **B2 — `/d/{slug}` disclosure page** | Deployed | Per-sub-broker, regulator-ordered, config-driven. Live at `/d/pifs`. |
| **B3 — Per-tenant landing mode (page vs direct)** | Deployed | PIFS runs **Direct** mode live; disclosure coupling enforced. |
| **B4 — `/api/wati/webhook` assisted capture → Zoho lead** | Deployed (fail-closed) | 401-before-schema; hardened further by T-048 (replay + stale-status protection). |
| **Q-M-PREF — Preferences / Settings screen** | Deployed | Every operator control wired to the ADR-022 config cascade. |
| **Q-M-OTP — pluggable OTP channel port** | Deployed — flag ON (21-Jul) | Live via M13; hashed/peppered/single-use/rate-limited; recipient only from on-file channel. |
| **M13 — Referrer login + identity binding + `/my/referrals` self view** | Deployed — LIVE 21-Jul (PR #20) | Google OAuth primary + WhatsApp-OTP fallback, Path-B evidence verification, admin Verifications queue. **Google OAuth path itself is still untested live** (owner deferred in D8); the OTP path is E2E-verified. |

### Shipped 2026-07-24 → 2026-08-08 (previously missing from this ledger)

| Feature | Status | Remarks |
|---|---|---|
| **M-WATI-1 — one-tap `/share/{channel}/{client_id}` endpoint** | Deployed — LIVE 24-Jul (`f7f8656`) | `ENABLE_SHARE_INTENT=true`; `GET /share/wa/{id}` → 302 → wa.me with pre-filled referral message. |
| **M-FUP-1 — WhatsApp follow-up engine (REQ-F01 un-frozen)** | Deployed — LIVE 24-Jul (`bbc32c8`), auto-trigger 25-Jul (`f0fa385`) | 24h-session-window nudges only; 7-step 3h→21h cadence; IST quiet hours 23:00–06:00; anti-burst min-gap (`6e3072d`); converted-suppression; windows opened by `poll_inbound_windows` (webhook is chatbot-suppressed). Zoho stays owner of lead status. |
| **Recipient-identity resolver + referral link in nudges** | Deployed — 25-Jul (`c050d19`) | Prospect nudges carry the credit-preserving `/r/wa/{referrer_client_id}` link (or `/open` fallback); referrer recipients suppressed from prospect copy. |
| **§6.1 referrer nudge (idle prospect → nudge the referrer)** | Deployed — activated 26-Jul (`7870052`) | Only when the referrer's phone is a known Customer; one per step; v5 UTILITY-attempt templates (Meta kept MARKETING — see CLAUDE.md §6c precedent). |
| **E2E hardening round (26-Jul)** | Deployed (`324a1b8`, `1be4c34`) | `first_click_at` stamping + backfill; nudge link canonicalized via `nudge_link_for()`; **P0 fixed:** OTP template config pointed at a never-existed name; OTP delivery-race fixed; guardrail-3 leak (`ZMPHZC` on `/my/referrals`) stripped at data level. |
| **D-series owner decisions (27-Jul)** | Deployed (`a452ebf`, `1501a3f`, `18981a0`) | D1 configurable `/open` destination; D2 crawler PIFS preview card; D4 lead fill-blanks + one-lead-per-mobile; D5 converted-suppression decoupled from `stop_on_reply`; D6/D7 template + junk-identity cleanup. Codified as CLAUDE.md §6d "message behaviour is configuration". |
| **Zoho conversion reconciler (webhook backstop)** | Deployed — 27-Jul (`4919036`) | `reconcile_conversions` scheduled sweep; born from the P0 "ingest was inert" incident (conversions land in Contacts, not Leads). |
| **Phase 0 — config-platform enforcement rails** | Deployed — 28-Jul (`a23a58e`; doc 16 ratified `8e9c4bb`) | ADR-042…044; rails E-1…E-6 + D-1 compliance rail; dead `ENABLE_ASSET_GENERATOR` flag removed; zero behavior change. |
| **Share-kit https preview fix** | Deployed — 28-Jul (`118ddfd`/`31fc244`) | Kit link carries full `https://` so WhatsApp previews the referral landing, not the Disclosures page. |
| **T-030 — admin-login redirect-loop fix** | Deployed — 30-Jul (`ca6a3d6`) | Non-staff referrer session no longer loops at `/admin-panel/login/`. |
| **T-031…T-034 — daily WA engagement report** | Deployed — 30-Jul (`d342831`) | `wa_engagement_report` command + 21:00 IST schedule; parser built against REAL captured Wati payloads; owner digest via the shared Notifier gateway. |
| **T-037 — qcluster timeout 60→600** | Deployed — 01-Aug (`431931f`) | The nightly digest had never survived its schedule (killed at 60s). Also carries the IST dirty-day rollup fix (`784a592`). |
| **T-039 — unattributed conversions in rollups + `first_click_at` backfill** | Deployed (via the 04-Aug train) | Rollups no longer drop conversions lacking attribution. |
| **Doc-17 vendor-boundary hardening W1–W3 (T-040…T-044)** | Deployed — 04-Aug (`f4f079f`) | ADR-045…048: `ports.py` protocols + factories, `services.py` facade, vendor webhook routers moved inside the boundary, **E-3 architecture gate now runs with an EMPTY baseline** (any new vendor leak fails CI). |
| **T-046 — dashboard N+1 + pagination** | Deployed — 06-Aug (`8f71be6`) | Explorer/leaderboard on queryset annotations; new cascade key `dashboard_explorer_page_size`. |
| **T-047 — CSRF + real session auth on staff Ninja routers** | Deployed — 06-Aug (`7eb1c82`) | Forged staff POSTs now 403; webhooks/public routes untouched. Closed the last gap from the 06-Aug security review. |
| **P0-A — Zoho Contacts push pipe (workflow rule + signer)** | LIVE — 06-Aug (Zoho-side) | Conversions push within seconds; live fire found + fixed a latent Deluge IST-as-GMT timestamp bug; nonce replay refused; true 2022 opening date honoured. |
| **T-048 — Wati webhook replay + stale-status protection** | Deployed (`e9ac3f5`, carried by the 08-Aug train) | 3 security hardenings on the inbound Wati surface. |
| **T-049 — tenant-scoping refactor** | Deployed — 08-Aug (carried by `e217489`) | 89 raw filters → `for_tenant()`; new CI rail E-7. |
| **T-051 — `/rr/{token}` WhatsApp magic-link records page** | Deployed — LIVE 08-Aug (`e217489`), `ENABLE_RECORDS_LINK=true` | Signed revocable token; masked read-only view (`Ab••••a` / `91••••••53` proven live); no-oracle 404 on bad tokens. |
| **T-052 — fail-closed token verification** | Deployed — 08-Aug (`998d6df`) | T-051 checker finding: token rotation failure now fails CLOSED. |
| **T-053 — `/hub/{token}` referral share hub** | Deployed — LIVE 08-Aug (`66fd520` + `e217489`), `ENABLE_SHARE_HUB=true` | Benefits + own link + WA/TG/FB/X/LinkedIn/copy/native-share. Every share spreads the CREDIT link `/r/wa/{client_id}` — the token appears once per page (sibling cross-link) and never in a share href. **This substantially delivers M12's channel-launcher scope.** |
| **T-054 — `POST /api/records-tokens/mint` + logged-in hub entry** | Deployed — 08-Aug (`e217489`) | Key-authed (`X-Records-Mint-Key`, env-only, fail-closed); "Share your link" entry on `/my/referrals`. No template send is wired to the mint API yet. |
| **T-055 — hub partner header + share hierarchy** | Deployed — 08-Aug (`214c900`) | Brand line top, ONE primary "Share on WhatsApp" CTA, Copy second, five channels demoted; DOM order test-locked; attribution wording = cascade key `share_hub_partner_attribution`. No partner logo (ADR-014). |
| **T-056 — hub brand resolves the PROGRAM, not the partner-company** | Deployed — 08-Aug (`14eb2f7`) | Fixed the live "PIFS via PIFS" defect: brand = `program.display_name` → `program.name` → `partner.name` → no element. Tests now seed the production shape; multi-program (Groww) rendering demonstrated. |
| **Hub copy + real link-preview card (PR #124)** | Implemented — merged 08-Aug (`e4fbeeb`); **deploy not verified from this session** | Compliance-reviewed share copy; OG card generated from the canonical compliance strings with a drift-guard test. Closes the "placeholder copy / reused OG image" gates from `e217489`. Verify `DEPLOYED_SHA` before treating as live. |

---

## Feature map by actor — required vs implemented vs pending

> Actors per `docs/foundation/01` §User Types, extended by what Sprint 2 actually built. **This section is the discussion agenda**; pending items carry a P-id so they can be discussed one at a time.

### 1. Referrer (existing customer who shares)

**Live today:** permanent link `/r/{client_id}` (+ channel variants `/r/wa/…`), one-tap share endpoint `/share/wa/{id}`, login (`/login/` OAuth + WhatsApp-OTP), self view `/my/referrals`, share hub `/hub/{token}` with 7 channels, records page `/rr/{token}`, thank-you message on lead capture (msg c, phone-resolvable only), §6.1 idle-prospect nudge to the referrer.

| P-id | Pending | Source / trigger |
|---|---|---|
| ~~P-01~~ | **DONE (T-058, 2026-08-09)** — congrats on conversion ingest; session leg live, template leg dormant until the owner sets `referrer_conversion_congrats_template_en` | Gap 5 closed |
| P-02 | **M14 poster / downloadable branded creative** | Spec'd Phase 4; prototype + compliance analysis started 08-Aug, nothing shipped |
| P-03 | **M12 remainder** — per-platform creatives + `?s=` per-platform attribution polish (channel launcher itself = done via T-053) | `S2-01`; Sprint 3 |
| ~~P-04~~ | **DONE for hub/records (T-061, 2026-08-09)** — ?lang=hi + 34 config twins, EN fallback; login surfaces deliberately excluded (OAuth/consent copy not ours) | Web-only per owner's HI-template deferral |
| P-05 | **SMS OTP fallback** (DF-OTP-SMS) | Referrers without WhatsApp |
| ~~P-06~~ | **DONE — display half (T-060, 2026-08-09)**; count-exclusion half stays deferred with DF-11's trigger | DF-11 row updated |
| ~~P-07~~ | **VERIFIED E2E 2026-08-09** — chooser → callback → real session on /my/referrals | Closed |

### 2. Prospect / referral visitor (the friend)

**Live today:** branded landing (or Direct mode), capture form (lead saved FIRST, consent + privacy), redirect with server-side `ZMPHZC`, warm WATI notice naming the referrer, follow-up cadence inside the 24h session window (quiet hours, min-gap, opt-out, converted-suppression), bot/preview filtering, `visitor_id` + human-confirmation beacon.

| P-id | Pending | Source / trigger |
|---|---|---|
| P-08 | **OTP verification on the capture form** (DF-6) | Junk/mistyped leads becoming a problem |
| ~~P-09~~ | **DONE (T-059, 2026-08-09)** — {program_brand} in all message copy, byte-identical for Zerodha, second program proven. Residual partner-#2 item: OG preview-card copy (page metadata, parked) | Blocker cleared |

### 3. Partner-direct visitor

**Live today:** `/open` → configurable destination (D1), `referrer=NONE / source=partner_direct` journey, explorer filters the population separately. Nothing pending.

### 4. Platform administrator / operator (Abhay)

**Live today:** admin dashboard + explorer + journey timeline + referral profile, Preferences screen (all message/behaviour knobs cascade-config per §6d/§6e), Verifications queue, follow-up CRUD API, daily WA engagement digest (21:00 IST via Notifier), three-sided daily report (21:30 IST), `golive_smoke`, `erase_pii` / scheduled `purge_expired_pii`, rate limiting, CSRF-hardened staff routers.

| P-id | Pending | Source / trigger |
|---|---|---|
| P-10 | **Full historical backfill since 2016** (DF-4) | Complete all-time dashboards; lazy per-referrer fetch is the current mechanism |
| P-11 | **Q-M-MENU — referrer 3-branch WhatsApp menu** | `S2-03`; mostly a Wati-dashboard flow build (the "Know More" menu flow covers part); only the B4 webhook hook exists in GoRefer |

### 5. Executive / ops human (Ashok)

**Live today:** instant WATI lead alert (msg a); works leads in Zoho (source of truth). **Never built:** the executive role tier (doc 05 Context 1 — roles/permissions/executive-scoped lead views). GoRefer auth is admin + referrer only.

| P-id | Pending | Source / trigger |
|---|---|---|
| P-12 | **Executive-scoped access** (least-privilege lead views in GoRefer) | Spec'd in doc 05; no demand yet — Zoho serves this today |

### 6. External systems (Zoho, Wati/Meta)

**Live today:** Zoho write (Model-2 upsert), read enrichment, HMAC-sealed conversion webhook + LIVE Contacts push rule + reconciler sweep; Wati send with terminal-status verification, inbound polling, webhook (replay-protected), template coverage matrix; delivery instrumented daily.

| P-id | Pending | Source / trigger |
|---|---|---|
| P-13 | **Delivery rate** (DF-WATI-REL) — ~42-43%, dominated by Meta per-user marketing cap 131049; §6f marketing-primary/utility-fallback strategy is the countermeasure | Ongoing; measured toward ≥90% by the daily report |
| P-14 | **Zoho polling as primary sync** (DF-1) — durable-automation variant: mint a broader-scope self-client token so workflow rules are API-manageable (needs owner MFA once) | Webhook unreliability / Zoho hardening |
| ~~P-15~~ | **DONE (T-057, 2026-08-09)** — `send_records_links` operator command (dry-run default, cap/dedupe/opt-out gates); first real send terminal-DELIVERED | Go-to-market unblocked |

### 7. Future partner / tenant #2 (readiness)

Architecture is provider-agnostic and now demonstrated (T-056 renders a second program correctly). Gated work, all trigger = onboarding tenant/partner #2: **P-09** (partner-scoped copy — the one live defect-class), DF-5 (per-partner page fields), DF-9 (pluggable lead sink), DF-10 (theming), DF-7 (schema isolation, only if a regulated tenant demands it).

### 8. Compliance / regulator (cross-cutting)

**Live today:** disclosure block + risk warning auto-injected on every page and baked into the generated OG card (PR #124, drift-guard-tested); compliance-locked cascade keys resolve from central only (D-1 rail); `/d/{slug}` disclosure page; single swappable `REFERRAL_INCENTIVE_CLAIM`; guardrail tests (never submit Zerodha, never fabricate status, no partner-code leak) in CI. Scheduled 12-month unconverted-PII purge is live (DF-PII-PURGE closed). Nothing pending beyond the standing per-asset review gate.

---

## Scale / hygiene backlog (no actor pressure today)

DF-3 edge runtime (≈1M clicks/month trigger), DF-8 events partitioning (tens of millions of rows), DF-PORTS-1 boundary eviction (second messaging vendor), the vacuous assertion in `test_empty_brand_name_renders_no_blank_element_in_the_header` (cleanup queued for the next hub PR). Full tracked backlog with triggers: **`review/Deferred-Features-Backlog.md`** (single source of truth; not duplicated here).

---

## Plan / what's next

1. **Verify the PR #124 deploy** (`DEPLOYED_SHA` vs `e4fbeeb`) and update `CURRENT-STATE.md` — the last ledger item that is merged-but-unconfirmed.
2. **Feature-by-feature owner discussion** off the actor map above (P-01…P-15) — decide build order; the natural front-runners are P-15 (distribute the hub links — the whole magic-link surface is live but nothing sends it yet), P-01 (conversion congrats nudge), and P-09 (partner-scoped copy, mandatory before any partner #2 conversation).
3. **Delivery-rate watch** (P-13) stays the standing ops instrument — every messaging feature rides on it.
