---
name: e2e-live-verify
description: Run the full autonomous end-to-end verification of GoRefer against LIVE production — click → record, template send → terminal Wati status, session-nudge cadence, Zoho lead write, and the three guardrails. Use when asked to "test end to end", "run the E2E", "verify prod", "full round of testing", or after any deploy touching redirect / Wati / Zoho / followups.
---

# GoRefer — live end-to-end verification

Verifies the real production system at `gorefer.in`, not a test double. Every leg is checked
**at the destination** (Wati's own record, the prod DB), never at the point of dispatch.

**Acceptance bar (owner-set, 2026-07-26):** a message counts as PASS at **`sent`**. Meta may block
delivery (per-user cap `131049` is common — delivery rate has run ~43%), and that is not a GoRefer
defect. `delivered` / `read` are bonus.

## Preflight (do this first — 2 min)

```bash
# 1. SSH — the key is NOT the default id_rsa. Bare `ssh root@...` FAILS with publickey.
ssh -i ~/.ssh/firekaro_v6_vps root@<PROD-VPS> "hostname; cat /var/www/gorefer/DEPLOYED_SHA; systemctl is-active gorefer gorefer-qcluster"

# 2. Effective flags — NEVER read .env, it lies (says false while overrides are ON)
ssh -i ~/.ssh/firekaro_v6_vps root@<PROD-VPS> 'cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c "
from apps.config.integration_flags import resolve_flag
print([(f, resolve_flag(f)) for f in [\"ENABLE_WATI_SEND\",\"ENABLE_ZOHO_WRITE\",\"ENABLE_ZOHO_READ\"]])"'
```

Sanctioned test recipients (`GLOBAL.env:WATI_TEST_RECIPIENTS`): `919999900000`, `919999900000`.
**Never send to any other number.**

Use a **fresh throwaway client_id** each run (`E2E<DDMM>`) so real referrer stats stay clean.

## Phase A — HTTP + guardrails (fully autonomous, no human, no side effects beyond a test id)

```bash
ID=E2E0726
curl -s -o /dev/null -w "A1 %{http_code} %{redirect_url}\n" -A "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile" "https://gorefer.in/r/wa/$ID"
curl -s -o /dev/null -w "A2 %{http_code} %{redirect_url}\n" -A "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile" "https://gorefer.in/open"
curl -s -o /dev/null -w "A3 %{http_code} %{redirect_url}\n" -A "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile" "https://gorefer.in/share/wa/$ID"
curl -s -o /dev/null -w "A4 %{http_code} %{redirect_url}\n" -A "facebookexternalhit/1.1" "https://gorefer.in/r/wa/E2EBOT01"
for p in "/" "/d/pifs"; do curl -s "https://gorefer.in$p" | grep -c 'ZMPHZC\|signup.zerodha.com'; done   # must be 0
```

| # | Assert |
|---|---|
| A1 | 302 → `signup.zerodha.com/api/lead/?c=ZMPHZC&r={ID}`; identity + `click` event created |
| A2 | 302 with **no `r=`**; a `Referral` with `source=partner_direct` and `referral_identity=None` (ADR-015) |
| A3 | 302 → `wa.me`; `share_intent` event, `source='wati'` |
| A4 | **Bot id must NOT exist in DB.** A 302 is still returned — that is current behaviour, only the *record* is suppressed |
| A5 | Zero `ZMPHZC` / raw Zerodha URL in any client-facing HTML (guardrail 3) |

## Phase B — capture loop + template send + Zoho (autonomous; HAS side effects)

```bash
ssh -i ~/.ssh/firekaro_v6_vps root@<PROD-VPS> 'cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py golive_smoke \
  --referrer E2E0726 --mobile 7767009136 --name "E2E TEST <DD><Mon> DELETE" --email e2e-test-<date>@example.invalid --json'
```

Writes a **real Lead into Zoho CRM** (source of truth). Requires owner approval each run.
Record the returned `zoho_lead_id` and hand it back for deletion.

Then **poll for terminal status** — `queued`/`accepted` are promises, not results.
`wati_reconcile_pending` runs **every 15 min**; wait for it rather than declaring a bug.

```
Notification.objects.filter(referral_id=<journey_id>).values_list("recipient_role","status","meta_error_code","failure_classification")
```
PASS when office/prospect reach `sent`/`delivered`/`read`. `referrer` legitimately `skipped` when
the referrer has no phone on file.

Cross-check the destination via Wati MCP `wati_get_messages` → `statusString` + `failedDetail`.

## Phase C — session-nudge cadence (needs ONE human action)

The 24h WhatsApp session window can only be opened by a **real inbound from a human phone**.
No API simulates this. Forcing `last_inbound_at` in the DB does NOT work — Meta still rejects the
session send, so you would be testing the failure path and calling it green.

1. Ask the owner to send "Hi" to the WATI business number **+91 70806 42020**.
2. `followup_inbound_poll` (every 5 min) opens the window autonomously — verify `FollowupWindow.last_inbound_at` updates.
   (The Wati inbound webhook is chatbot-suppressed; polling is the designed path, not a workaround.)
3. Assert **7** `ScheduledFollowup` rows enqueue with `status='scheduled'`.
4. To avoid waiting 3h, advance ONE step's `fire_at` to now and run `fire_due_followups()`.
   Legitimate: the window is genuinely open, only the timer is accelerated. Leave the other 6 to run naturally.

```python
sf = ScheduledFollowup.objects.get(id=<first>)
services.window_is_open(services.get_window(sf.tenant, sf.mobile))   # must be True
services.in_quiet_hours(timezone.now(), sf.tenant_id)                # must be False (quiet 23:00-06:00 IST)
services.within_min_gap(sf.tenant, sf.mobile, timezone.now(), sf.tenant_id)  # must be False (90 min anti-burst)
sf.fire_at = timezone.now(); sf.save(update_fields=["fire_at"])
fire_due_followups()
```

## Phase D — close the owner's loop

Extract the referral link **from the delivered WhatsApp body** (via `wati_get_messages`), click it,
and assert a NEW `click` event lands on that referral. This is the leg the owner cares most about.

## Gotchas that cost time — read before writing any shell query

| Wrong | Right |
|---|---|
| `Referrer` | `ReferralIdentity` (holds `client_id`) / `Referral` (the journey) |
| `Event.occurred_at` | `Event.timestamp` |
| `FollowupRule.is_active` | `.enabled` |
| `ScheduledFollowup.step_key` | `.rule__step_key`; time field is `.fire_at`, not `scheduled_for` |
| filtering `status="pending"` | initial status is **`scheduled`** — "pending: 0" is NOT a missing cadence |
| `Schedule.last_run` | field doesn't exist; use `next_run` |
| reading `.env` for flags | `resolve_flag()` — DB override beats env |

- **Landing mode is `direct`** → `/r/` 302s straight to Zerodha, no landing page, so the JS beacon
  never fires and `is_confirmed_human` is **structurally 0**. The daily report's "0 confirmed" is
  expected, not a regression. Only a page-mode tenant can produce confirmed-human clicks.
- `dedupe_key` = `tenant|mobile|step|window_open_ts`, so a returning prospect **does** get a fresh
  cadence. Do not report this as a repeat-visitor bug.
- Wati's `sendTemplateMessage` ack carries **no message id**, so `provider_message_id` stays empty;
  terminal status is matched by recipient+template+time by the reconciler.

## Cleanup checklist

- [ ] Report the Zoho `zoho_lead_id` for owner deletion.
- [ ] Note the throwaway `E2E*` identities left in prod (harmless, but they inflate identity counts).
- [ ] Append a STATUS entry to `COORDINATION.md`; update `CURRENT-STATE.md` if any state changed.
