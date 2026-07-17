# PROPOSAL — the 3 lead-capture WATI templates (for Abhay's review)

> **Status: DRAFT for review — NOTHING submitted to Meta.** These are the 3 transactional
> notifications GoRefer fires on every lead capture (Family A in `WATI-TEMPLATE-INVENTORY.md`), which
> currently DON'T EXIST in Wati. Reviewed end-to-end per `WATI-TEMPLATE-CREATION-RULE.md`.
>
> Applying Abhay's guidance (2026-07-17): **Ashok alert = no compliance**; **prospect welcome +
> referrer-used = add the disclosure line at the end** (matching the approved templates:
> `*Disclosures*: https://gorefer.in/d/pifs`), **keep everything else the same**.
>
> **Names follow `WATI-TEMPLATE-NAMING-CONVENTION.md`** (`gr_<group>_<partner>_<purpose>_[lang]_<date>`).
> For these: `gr_brokers_zerodha_<purpose>_[hin]_2026_07_17`. The code (`notify.py`) must read these
> from config (not the old hardcoded `gorefer_office_new_lead` constants) — see §On your go-ahead.

---

## Design decisions that span all three (per the RULE)

- **Category: all UTILITY.** These MUST arrive (an office alert / a welcome / a notice). UTILITY is
  uncapped; MARKETING (131049 cap) would silently drop — wrong choice for transactional messages.
- **Buttons: NONE, by design (recommendation).** These are one-way *notifications*, not conversation
  entry points. A quick reply is only useful if a route listens for it (RULE §6); wiring routes here
  adds the legacy-bot coexistence + attribution risks for no lead-flow benefit. The prospect's next
  step is a phone call from Ashok (already the flow), not a WhatsApp button. **Open for your call** —
  if you want e.g. a "Call me" quick reply on the prospect message, we design its route too (see §Open).
- **Language: English first; Hindi parity recommended.** Below I give the English body for each and a
  Hindi companion for the prospect + referrer messages (the two a customer sees). The office alert is
  internal (Ashok) → English only is fine. Each Hindi template is a separate name + approval.
- **Variables:** named meanings listed; the code (`notify.py`) currently sends the office one with 3
  positional vars and the prospect with 2 — noted per template so counts match.
- **Delivery:** verified via `getMessages` terminal status (the adapter already does this); never off
  the ack.

---

## 1. `gr_brokers_zerodha_office_new_lead_2026_07_17` — Office/Ashok alert · UTILITY · **NO disclosure** (internal)

**Audience:** PIFS's own office line (Ashok). Internal staff → no client disclosure needed (RULE §4).
**Trigger:** a lead is captured. **Category:** UTILITY. **Buttons:** none. **Language:** EN only (internal).

**Body (unchanged from manifest):**
```
New GoRefer lead: {{1}} (mobile {{2}}), referred by client {{3}}. Please call to help them open their Zerodha account.
```
**Variables:** `{{1}}` = prospect_name (sample "Rahul Sharma") · `{{2}}` = prospect_mobile ("9876543210")
· `{{3}}` = referrer_client_id ("RJ4521"). Matches the 3 the code sends.

**Flow after receipt:** none — Ashok reads it and calls the prospect. No buttons, no routes.

---

## 2. `gr_brokers_zerodha_prospect_welcome_2026_07_17` (+ `_hin_`) — Prospect welcome · UTILITY · **WITH disclosure** (client-facing)

**Audience:** the person who just submitted the form. **Trigger:** lead captured. **Category:** UTILITY.
**Buttons:** none (recommended). **Language:** EN + Hindi.

**Body (English — manifest body, with your disclosure line added at the end; everything else same):**
```
Hi {{1}}, {{2}} referred you to PIFS to open a free Zerodha demat & trading account. Our representative will call to help you complete it.

Investments in the securities market are subject to market risks.

*Disclosures*: https://gorefer.in/d/pifs
```
**Variables:** `{{1}}` = prospect_name ("Rahul") · `{{2}}` = referrer_display ("Ramesh Kumar"). Matches
the 2 the code sends.
*(Change vs current manifest: only the `*Disclosures*: https://gorefer.in/d/pifs` line appended, and the
market-risk sentence put on its own line. Wording otherwise identical.)*

**Body (Hindi companion — `gr_brokers_zerodha_prospect_welcome_hin_2026_07_17`):**
```
नमस्कार {{1}} जी, {{2}} ने आपको PIFS के माध्यम से एक मुफ़्त Zerodha डीमैट और ट्रेडिंग अकाउंट खोलने के लिए रेफ़र किया है। हमारा प्रतिनिधि आपको इसे पूरा करने में मदद के लिए कॉल करेगा।

प्रतिभूति बाज़ार में निवेश बाज़ार जोखिमों के अधीन है।

*खुलासा (disclosure)*: https://gorefer.in/d/pifs
```
**Flow after receipt:** none (no buttons). Next step = Ashok's call.

---

## 3. `gr_brokers_zerodha_referrer_used_2026_07_17` (+ `_hin_`) — "Someone used your link" · UTILITY · **WITH disclosure** (client-facing)

**Audience:** the referrer (only if GoRefer knows their phone). **Trigger:** their link produced a lead.
**Category:** UTILITY. **Buttons:** none (recommended). **Language:** EN + Hindi.

**Body (English — manifest body, with your disclosure line added; everything else same):**
```
Good news! Someone just used your PIFS referral link to start opening a Zerodha account. We'll keep you posted. Reward status is shown in your Zerodha Console.

*Disclosures*: https://gorefer.in/d/pifs
```
**Variables:** none (matches the code). *(Change vs current manifest: only the disclosure line appended.)*

**Body (Hindi companion — `gr_brokers_zerodha_referrer_used_hin_2026_07_17`):**
```
खुशखबरी! किसी ने अभी-अभी आपके PIFS रेफ़रल लिंक का उपयोग करके Zerodha अकाउंट खोलना शुरू किया है। हम आपको अपडेट करते रहेंगे। रिवॉर्ड की स्थिति आपके Zerodha Console में दिखती है।

*खुलासा (disclosure)*: https://gorefer.in/d/pifs
```
**Flow after receipt:** none (no buttons).

---

## Summary table

| Template (`gr_brokers_zerodha_…_2026_07_17`) | Audience | Category | Disclosure | Buttons | Languages | Vars |
|---|---|---|---|---|---|---|
| `…_office_new_lead_…` | Ashok (internal) | UTILITY | ❌ no | none | EN | 3 |
| `…_prospect_welcome_…` (+ `_hin_`) | prospect | UTILITY | ✅ yes | none | EN + HI | 2 |
| `…_referrer_used_…` (+ `_hin_`) | referrer | UTILITY | ✅ yes | none | EN + HI | 0 |

## Open questions for Abhay (before I submit)
1. **Buttons on the prospect message?** Recommend NONE (it's a notice; the call is the next step). If
   you want a **"Call me"** or **"WhatsApp us"** quick reply, I'll design its route (keyword-action →
   which bot/agent, and the exact reply) and the Hindi route too — per the RULE, a quick reply without a
   route does nothing.
2. **Hindi rollout now or later?** I can submit EN-only first (fastest to a working loop) and add Hindi
   as a fast follow, or submit all 5 together. Which?
3. **Referrer-used disclosure:** confirmed you want the disclosure line on this internal-ish "your link
   was used" notice too — done above. (It mentions rewards, so the disclosure is reasonable.)
4. **`/d/pifs` §4.8 line:** the earlier audit flagged adding "Brokerage will not exceed the SEBI
   prescribed limit." to `/d/pifs`; you decided it's not required (10% share is referrer revenue-share,
   not a client rate). No change unless you say so.

## On your go-ahead
Once you approve the copy: I finalize these into the manifest (`wati-templates.json`), run the
`zerodha-ap-social-media-compliance` review on the client-facing ones, then submit via
`wati-template-create-and-track` and track each to APPROVED. Then re-point `notify.py` to read the
names from config (not hardcoded), redeploy, and the live loop's WhatsApp leg delivers.
