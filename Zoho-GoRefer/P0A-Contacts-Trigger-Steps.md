# P0-A fix — move the account-opened doorbell to the Contacts door (Abhay's steps)

**The problem in one line:** Zoho's trigger watches **Leads**, but a converting lead
*becomes a Contact*, so the "account opened" webhook has never fired for a real conversion
(14 days of logs: zero POSTs from Zoho). The 15-minute reconciler sweep has been covering
for it. This runbook installs the trigger on the **Contacts** module — where the event
actually happens. Total time: **~7 minutes**, all inside Zoho CRM Setup.

**Safe to do anytime:** GoRefer's webhook is idempotent — if the new trigger and the
reconciler both report the same opening, the second one is recognized as a duplicate and
ignored. Nothing can double-credit. The old Leads rule can stay on or off; it fires on a
module where the event never occurs, so it is harmless either way.

**Already done for you:** the secret Variable (`gorefer_webhook_secret`) exists and is set
(live since 18-Jul). The function code is written and standards-checked. GoRefer's side
needs zero changes.

---

## Step 1 — Create the Contacts signer function (~3 min)

1. **Setup → Developer Space → Functions → + New Function**
2. Fill in:
   - **Function Name / Display Name:** `gorefer_webhook_signer_contacts`
   - **Category:** `Automation` (so a Workflow can attach it)
3. Paste the ENTIRE contents of the canonical file, replacing everything in the editor:

   > **`D:\Abhay\VibeCoding\5Wealths\Zoho-Project\deluge\gorefer_webhook_signer_contacts.dg`**
   > (VPS copy: `C:\Abhay\5Wealths\Zoho-Project\deluge\...` — same file)

   The file starts with `void automation.gorefer_webhook_signer_contacts(string contactId)`
   — the editor derives the ONE argument (`contactId`, String) from that signature. If it
   asks you to define arguments manually: one argument, **Name** `contactId`, **Type** String.
4. **Save.**

*Field names are pre-verified against your real Contacts layout (same map the live
reconciler uses): `ClientId` (no underscore), `Referrer_Client_Id`, `Account_Opened_On`,
`Account_Status`, `Full_Name`. You should not need to edit anything.*

## Step 2 — Create the Contacts workflow rule (~3 min)

1. **Setup → Automation → Workflow Rules → + Create Rule**
   - **Module:** `Contacts`
   - **Rule Name:** `GoRefer — account opened (Contacts)`
2. **When:** `On a record action` → check **Create** AND **Edit**
   (conversion creates/updates the Contact; both paths must ring the bell).
3. **Condition:** `Account_Opened_On` **is not empty**
   (fires only once the opening date is stamped — the true "account opened" signal, and the
   exact field the reconciler keys on).
4. **Instant Actions → Function** → pick **`gorefer_webhook_signer_contacts`**.
5. Map the argument: **`contactId`** = the record's **Contact Id** (`${Contacts.Contact Id}`
   in the merge-field picker).
6. **Save** and toggle the rule **Active**.

## Step 3 — One-click live test (~1 min)

Open any existing Contact that already has `Account_Opened_On` filled (one of July's six
openings), make a harmless edit (e.g. re-save without changes, or touch a note field), and
**Save**. That fires the rule.

Then just message me: **"P0-A rule is active, test contact saved"** — I'll verify at
GoRefer's end (nginx log shows the POST from Zoho, ingest response `applied:false
duplicate` for an already-known opening = the pipe works and idempotency held) and confirm
back. If you tell me which contact you touched, I'll quote the exact log line.

---

### What this changes operationally

- **Before:** conversions reach GoRefer only via the 15-min reconciler sweep (pull).
- **After:** Zoho pushes within seconds of the opening; the reconciler stays on as the
  safety net (it also catches anything that happened while the rule was off).
- The old Leads rule + `gorefer_webhook_signer` function: leave as-is or deactivate at
  your leisure — dead weight, not a risk.
