# GoRefer — Independent Test Brief (Track C)

> **For the independent tester** (a fresh verification subagent — must NOT be the Engineer who built the code, and must NOT be the DA). Run AFTER each Track B piece deploys. Verify against the acceptance criteria in `S2-03` §11 and the guardrails in `CLAUDE.md`. Report PASS/FAIL per item with evidence (the actual response/row observed), and never mark PASS on partial/assumed results.
>
> Compiled 2026-07-09 (DA). Ties to the EXECUTION PLAN in COORDINATION.md.

## Verification ORDER (standard, set 2026-07-09 — pre-deploy gates prod)
Independent verification **gates** the prod deploy; it does not follow it. For each mission:
1. **Pre-deploy independent code+test review (the gate):** run by a **separate Claude Code session** — a third party, NOT the builder (Engineer) and NOT the DA. It has its own working shell on the real machine, so it **checks out the branch itself, reads the diff, and RUNS the full test suite**, then reviews correctness / compliance coupling / security / acceptance-coverage and posts GO/NO-GO to COORDINATION.md **before** anything hits prod. (This is why it's a session, not a DA in-session subagent: the DA's sandbox is down `HYPERVISOR_VIRT_DISABLED`, so a DA subagent cannot run tests or read a non-main branch.)
2. **Deploy branch to prod** only on the pre-deploy GO (branch, not merged; main = rollback).
3. **Post-deploy black-box** live confirmation — run by a **DA in-session subagent** (web-only: web_fetch/browser against gorefer.in). Good for live HTTP behaviour; cannot run tests or log in to admin screens (those parts are covered by step 1 + the human admin action).
4. **Merge** on the post-deploy GO.
> Split rationale: code/test review needs a real shell → separate session; live HTTP black-box needs only web → DA subagent. Don't use a DA subagent for code/test review while the DA sandbox is down.

## Ground rules
- Verify on the **live prod host** (`gorefer.in` via the Cloudflare edge) and/or the box's test suite — state which for each item.
- Do not trust HTTP 200 = done; check the actual body/row/status.
- Independence: do not read the Engineer's self-reported STATUS as proof — re-observe.

## B1 — `/r/{channel}/{client_id}` channel-path route
- [ ] `GET https://gorefer.in/r/wa/RJ4521` → records a click with `channel=wa` (channel came from the PATH, not `?s=`).
- [ ] `.../continue` (or the redirect) → 302 `Location` is exactly `…/api/lead/?c=ZMPHZC&r=RJ4521` — **no `wa`, no `s=`, no partner code leak** in the client-facing body.
- [ ] Legacy `/r/RJ4521?s=wa` still works (back-compat).
- [ ] Unknown channel in path → recorded as `other`/handled, never errors.

## B2 — `/d/{slug}` disclosure page (e.g. `/d/pifs`)
- [ ] `GET https://gorefer.in/d/pifs` → 200, renders the sub-broker's disclosure block(s): Zerodha SEBI/NSE identification (`INZ000031633`, AP `AP2516003693`) + verbatim market-risk warning.
- [ ] Multi-partner (when configured): blocks appear in regulator order (SEBI/NSE → IRDAI → RBI); a lapsed partner's block is absent.
- [ ] **No PII** on the page; **no `ZMPHZC`/raw Zerodha URL** leak.
- [ ] Preview crawlers excluded from human-click counts (page is disclosure, not a click surface).

## B3 — `LANDING_MODE = page|direct`
- [ ] Tenant set to `page` → `/r/{id}` renders the landing page (today's behavior).
- [ ] Tenant set to `direct` → `/r/{id}` logs the click on-commit **then** 302s straight to Zerodha (skip landing), `?s`/channel stripped from the Location.
- [ ] Coupling: `direct` + no live `/d/{slug}` → config forces `MESSAGE_DISCLOSURE_LEVEL=full` (assert the combo `direct`+`light`+no-`/d/` is refused).

## B4 — assisted-referral webhook → Zoho lead
- [ ] `POST /api/wati/webhook` with an assisted capture `{name, mobile, email?, referrer client_id}` → creates **exactly one** Zoho lead (behind `ENABLE_ZOHO_WRITE`; log-only when off).
- [ ] Lead carries `source=whatsapp_assisted` + a **consent flag**; a duplicate post does NOT double-create.
- [ ] **Never** stores a password; PII stays out of the immutable event log.

## C2 — Compliance re-audit (run the `zerodha-ap-social-media-compliance` skill)
- [ ] Final template `gorefer_zerodha_referral_2026_07_09` body/buttons/disclosure → verdict + fixes.
- [ ] `/d/pifs` page → §4.1/§4.2 present; no superlatives; no incentive-for-account-opening.

## C3 — Live WhatsApp E2E (on this machine, Wati + WhatsApp Web + GoRefer)
- [ ] Send the approved template to the safe test number (99999 00001) → 3 buttons render.
- [ ] **Refer & earn** (URL) → opens `gorefer.in/r/wa/{client_id}` → tracked click `channel=wa` + landing/redirect per `LANDING_MODE`.
- [ ] **Share on WhatsApp** (QR) → the kit + forward-nudge arrive (the already-live flow).
- [ ] **Refer directly** (QR) → capture Name+Mobile → one Zoho lead with consent flag.
- [ ] No keyword collision: "Refer directly" routes to Direct Zerodha Referral, NOT Share (confirms the bare-"Refer" removal held).
- [ ] Terminal delivery verified (not just HTTP 200).

## Report format
Per item: `PASS/FAIL — evidence`. End with a one-line go/no-go and any FAILs itemised for the Engineer to fix (log each FAIL as a QUESTION/STATUS in COORDINATION.md).
