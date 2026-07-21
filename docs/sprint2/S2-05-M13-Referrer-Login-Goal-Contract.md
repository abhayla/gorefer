# S2-05 — M13 Referrer Login: Goal Contract

> **Status:** ACTIVE mission contract. Owner-decided via live Q&A (Abhay, 2026-07-21, Engineer
> session); this document is the record of those decisions and the binding scope for the
> `mission-13-referrer-login` branch. Grounded in **ADR-027** (OAuth + Client-ID binding),
> **ADR-035** (ownership model + OTP port), **ADR-026** (one role-scoped profile template),
> **ADR-022/023** (config cascade, tenant boundary), **ADR-012** (login on the public site),
> **ADR-020** (DPDP). Opens the Sprint-2 customer-login gate foreseen in ROADMAP "Plan" #2.

## 1. Owner decisions (Q&A, 2026-07-21)

| # | Question | Decision |
|---|---|---|
| 1 | Scope | **Full: Phase 0 + M13 login build** (template, Q-M-OTP-2, login UI, binding, self view; flags flip at go-live) |
| 2 | Login front-door | **Both: Google OAuth primary, OTP fallback** (ADR-027 + ADR-035 together) |
| 3 | Unknown referrer (not in Zoho) | **Path B in full**: evidence upload → admin verification queue → on approval upserted (local Customer + Zoho Contact) so future logins are Path A; screenshot purged after decision |
| 4 | Self view | **ADR-026 reuse as locked**: existing Referral Profile template, role-scoped — own record only, `PII_MASK_FOR_CUSTOMER_VIEW` on, admin chrome hidden, prominent share action |
| 5 | Google OAuth credentials | **Owner creates** the OAuth client (Engineer supplies exact steps + redirect URI); Engineer wires from env |
| 6 | OTP AUTHENTICATION template | **Draft shown to owner first**; submit to Meta only on explicit go |

## 2. Goals (what "done" delivers)

- **G1 — Phase 0a (Q-M-OTP-2):** `apps/otp/recipient._from_zoho` wired to the live M9 Zoho READ
  adapter (`ClientId → Mobile/Phone`, normalized), gated by the resolved `ENABLE_ZOHO_READ`
  flag. Demo fixtures carry on-file channels so the flow works offline. Closes backlog Q-M-OTP-2.
- **G2 — Phase 0b (OTP template):** `gr_platform_gorefer_login_otp_en_2026_07_21`
  (AUTHENTICATION, copy-code button, no marketing) authored per the design skill and staged in
  `wati-templates.json` — **HOLD until the owner's review-go**, then submitted + tracked to
  APPROVED + live-verified. The template name is config (`OTP_WHATSAPP_TEMPLATE`), so approval
  requires only a config/env value change, no deploy.
- **G3 — OTP login door (Path A):** referrer enters Client ID → GoRefer resolves the **on-file**
  channel (Customer → Zoho; never a typed number) → `OtpService.issue` → verify → session bound
  to `(tenant_id, client_id)`. Unknown channel → Path B offered. Rate-limited; codes single-use,
  hashed (existing engine).
- **G4 — Google OAuth door (primary):** "Continue with Google" → server-side OAuth 2.0
  authorization-code flow (state + PKCE; userinfo over TLS; **no third-party JS/resources on
  our pages** — the third-party-origin guardrail test keeps passing). First login: bind screen
  (Client ID + mobile) → **auto-bind iff the Google email OR the entered mobile matches the
  on-file record** (Customer/Zoho, both normalized — ADR-027); mismatch → pending-verification
  request in the admin queue. Subsequent logins: straight to My Referrals.
- **G5 — Path B evidence flow:** screenshot upload (Zerodha console showing Client ID +
  registered name), stored **erasably in the DB** (size/type-capped, never in the event log,
  never publicly served) → admin queue (approve/reject on the admin panel) → on approve: local
  `Customer` row created (future Path A works) + Zoho Contact upsert via the write adapter
  (behind `ENABLE_ZOHO_WRITE`; log-only otherwise) → **evidence bytes purged on decision**
  (DPDP/ADR-020). Rejected → purged likewise.
- **G6 — My Referrals self view:** `/my/referrals` renders the **same** `referrer_profile`
  template with `role=referrer`: locked to the session's own client_id, PII masked
  (`PII_MASK_FOR_CUSTOMER_VIEW`), admin chrome/nav hidden, copy-link + WhatsApp-share actions
  prominent. Admin view unchanged (full detail).
- **G7 — Gating & no dead UI:** every new URL/menu item exists **only** when
  `ENABLE_CUSTOMER_LOGIN` is on (URL-level include, like the admin panel); the OTP door
  additionally honours `ENABLE_OTP_LOGIN`. Home page "Login" appears only when the flag is on
  (ADR-012). Flags stay env-owned (frozen at import), OFF by default; **the settings screen
  still exposes only the 3 integration flags** (unchanged this mission).

## 3. Hard guardrails (tested)

1. **OTP is never sent to a user-typed number** — the request accepts only a Client ID; any
   submitted phone field is ignored/rejected (ADR-035).
2. **Own-record scoping** — a referrer session can render only its bound client_id; any other
   id is 404/redirect, asserted by test.
3. **Masking** — self view masks mobile/IP; admin view stays full (existing test extended).
4. **Existing guardrails keep passing** — redirect-never-POSTs, status-only-from-Zoho,
   no partner code / raw Zerodha URL in any client-facing response (new pages included),
   no third-party origin on public pages (Google reached only via a 302, never a loaded asset).
5. **PII discipline** — evidence + mobile live on erasable records; nothing new enters the
   immutable event log; compliance footer auto-injects on every new page (context processor).

## 4. Out of scope (unchanged decisions)

- SMS OTP provider (DF-OTP-SMS) — stub stays; capture-form OTP (DF-6); multi-platform share
  launcher (M12/Sprint 3); doc-13 multi-AP machinery (ADR-036…041 — model-only; binding stays
  `(tenant_id, client_id)`-shaped, which ADR-041's one-client_id-one-tenant-per-partner rule
  later depends on); exposing the two login flags on the settings screen.

## 5. Owner dependencies (block go-live, not build)

| # | Action | Needed for |
|---|---|---|
| D1 | Create the Google OAuth client (steps provided in the mission report) → `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` into prod `.env` (secret never in a repo file) | OAuth door live |
| D2 | Review the OTP template draft → give the submission go | OTP door live (Meta approval) |
| D3 | Flip `ENABLE_CUSTOMER_LOGIN=true` (+ `ENABLE_OTP_LOGIN=true` once D2's template is APPROVED) on prod | Feature visible |

## 6. Definition of Done

Spec-conformant (ADRs above); migrations forward-only; full suite + new tests green (Postgres);
ruff clean; Tailwind rebuilt + committed; `.env.example` updated (GOOGLE_OAUTH_*); Zoho contract
doc updated with the READ-field addition + Contact upsert (CI gate); demo mode works end-to-end
with all integration flags off; PR opened with a STATUS entry in `COORDINATION.md`; deploy dark
(flags off) after merge; go-live per §5.
