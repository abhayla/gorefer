# GoRefer go-live — the flip runbook (Zerodha)

> **State:** code-complete + deployed to prod (`fe00d81`), all integration flags OFF. Go-live = 3 checkbox flips in **Settings → Integrations**, done by Abhay. This is the operator runbook: what each flip does, how it's verified live (DA runs the Zoho/Wati-side check via MCP; Abhay does the UI/form side), expected result, and rollback. **Precondition:** independent verification = GO.

## Order (safest first) — flip ONE, verify, then the next

### Flip 1 — `ENABLE_ZOHO_READ`  (read-only, no confirm-gate)
- **Does:** GoRefer reads account/reward status from Zoho to enrich the Referral Profile. Reads only — cannot send or write anything.
- **Verify:** open a Referral Profile for a real Client ID in the admin (e.g. `EKU497`) → it should show real `Account_Opened_On` / status instead of "— not on file —". **DA-side (MCP):** already proven green live (Ram Chandra Gupta / EKU497 → 2026-07-09); I'll confirm the `ConfigGlobal` override row is written and READ resolves ON.
- **Rollback:** untick. Zero side effects (nothing was written anywhere).

### Flip 2 — `ENABLE_ZOHO_WRITE`  (confirm-gate: "writing real leads")
- **Does:** a lead captured on the GoRefer landing form is upserted into Zoho Leads (`duplicate_check_fields=[Mobile]`, bare-10-digit) with the journey-reference stamped. Never blind-creates → never twins.
- **Verify:** Abhay submits ONE test capture on a landing page (name + a test mobile). **DA-side (MCP):** I query Zoho Leads for that mobile → confirm exactly one lead, `GoRefer_Reference` stamped, `action=insert` (or `update` if it already existed). Re-submit the same → confirms `update`, no twin.
- **Rollback:** untick. Existing leads remain; no further writes. (Upsert means even a re-run can't duplicate.)

### Flip 3 — `ENABLE_WATI_SEND`  (confirm-gate: "real WhatsApp")
- **Does:** GoRefer sends its own 3 capture notifications (Ashok / new person / referrer-if-phone-known) when a lead is captured. Low volume — only GoRefer-form captures, separate from the Zoho-side Send Queue already running.
- **Verify:** the test capture from Flip 2 should trigger the notification(s). **DA-side (MCP/Wati):** I read the **terminal** delivery status for the notified number (delivered/read, not just "accepted") + confirm the dedup/opt-in logic held.
- **Rollback:** untick — instant kill switch (un-gated OFF, by design).

## After all three — end-to-end smoke
A real referral link → `/r/{client_id}` 302 → landing → capture → **lead upserted in Zoho** → **notifications sent + delivered** → (on account open) **status read back** → **dashboard shows the journey**. That closed loop = **GoRefer fully functional for Zerodha.**

## Rollback (whole go-live)
Any flag: untick in Settings → resolves to env default (OFF) on the next request, no redeploy. The OFF toggle is deliberately un-gated so stopping a live problem never waits on a dialog.

## Pre-staged verification queries (DA runs these the instant you flip)

**Test-capture recipe:** open a real referral link (e.g. `gorefer.in/r/EKU497`) → fill the landing form with name "GoLive Test" + **your own number `7972672473`** → submit. Using your number means you personally receive the notification AND I can verify both the Zoho write and the Wati send.

**After Flip 2 (`ENABLE_ZOHO_WRITE`) — I run (Zoho COQL):**
```
SELECT id, Last_Name, Mobile, GoRefer_Reference, Referrer_Client_Id, Created_Time
FROM Leads WHERE Mobile = '7972672473' ORDER BY Created_Time DESC LIMIT 3
```
Expect: exactly ONE lead for that mobile (an existing one is UPDATED, not duplicated), `GoRefer_Reference` stamped, `Referrer_Client_Id = EKU497`, Mobile stored bare-10-digit. Re-submit the form → still one row (proves upsert `action=update`, no twin).

**After Flip 3 (`ENABLE_WATI_SEND`) — I run (Wati):**
```
wati_get_messages(917972672473)      # the prospect notification (your number)
wati_get_messages(<Ashok's number>)  # the Ashok notification
```
Expect: the top message is the GoRefer capture notification, **terminal status delivered/read** (not just "accepted"), and dedup/opt-in held (no double-send).

**Flip 1 (`ENABLE_ZOHO_READ`)** — GoRefer-internal enrichment; nothing new lands in Zoho for MCP to see. You verify on the Referral Profile page (real `Account_Opened_On`/status appears). The Zoho-read contract was already proven green live (`EKU497` → 2026-07-09).

## Not required for this go-live (tracked separately)
- **DF-2 HMAC seal:** keep `ENABLE_ZOHO_WEBHOOK_HMAC` OFF until the Zoho-side Deluge signer is deployed (contract in `docs/deploy/DEPLOY-TARGET.md`; routed to the Zoho session). The basic keyed webhook works meanwhile.
- **DF-PII-PURGE:** automated 12-mo purge is a Sprint-2 ticket; manual erasure is in place.
