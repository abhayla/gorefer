# Meta template categorization — UTILITY vs MARKETING (the rules, and what they cost us)

> **Read this BEFORE authoring or re-cutting any WhatsApp template.** It exists because we burned
> three submissions (v4, v5, v6 of the §6.1 referrer nudge) guessing at why Meta kept flipping
> UTILITY → MARKETING, when the answer was written down the whole time.
>
> **Source:** [Meta — Template categorization](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization)
> · [Utility templates](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/utility-templates/utility-templates)
> · [Marketing templates](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates)
> **Verified:** 2026-07-26. Meta changes these; re-read the source before trusting this file for a
> decision with money on it.

---

## 1. Why the category matters to us

| | UTILITY | MARKETING | AUTHENTICATION |
|---|---|---|---|
| Per-user cap (`131049`) | **no** | **yes** — the dominant cause of our ~43% delivery rate | no |
| Needs marketing opt-in | no | yes | no |
| Cost | low | ~7× utility | low |
| Quality throttling | rare | yes (we have hit it) | rare |

`131049` = *per-user marketing cap*. It is a **per-recipient** limit Meta enforces on marketing
templates: a given user can only receive so many marketing messages in a window, across all
businesses. No amount of retrying, warming, or re-sending defeats it. **The only real fix is to
stop sending marketing-category messages.** That is what makes categorization an engineering
concern and not a copywriting preference.

---

## 2. The actual test (quoted)

**Definitions:**

- **Utility templates** — *"Enable businesses to follow up on user actions or requests, since these
  messages are typically triggered by user actions."*
- **Marketing templates** — *"Enable businesses to achieve a wide range of goals, from generating
  awareness to driving sales and retargeting customers."*

**For UTILITY, a template must satisfy BOTH:**

1. Must be **non-promotional** — *"not containing any promotional or persuasive intent."*
2. Must be **specific to or requested by the user** — *"clearly related to their order, account,
   services, or transactions"* — **OR** essential/critical to the user.

**Explicit prohibition:** utility messages *"should not promote, recommend, upsell, or cross-sell
products; include offers; or attempt to secure renewals."*

**Automatic downgrade:** *"If you attempt to create or update a utility template with marketing
material, the template will automatically be re-categorized as a marketing template."* Since
**9 April 2025** this is the default: *"if you selected UTILITY as the template's category and
WhatsApp determined it should be MARKETING, the template is approved as MARKETING."* You do not get
a rejection you can argue with — you get a silent, working, expensive template.

---

## 3. Meta's own worked examples

**Qualifies as UTILITY:**

| Kind | Example |
|---|---|
| Order confirmation | *"Thank you! Your order {{order_number}} is confirmed. We will let you know once your package is on its way."* |
| Shipping update | *"Hooray! Your package from order {{order_number}} is on its way. Your tracking number is {{tracking_ID}}…"* |
| Account alert | *"Daily update for account ending in {{four_digit_number}}: Your available balance is {{amount}}."* |
| Billing reminder | *"Reminder: Your monthly payment for {{service}} will be billed on {{date}}…"* |
| Post-delivery feedback | *"We have delivered your order {{order_number}}! Please let us know if there was any issue…"* |
| Continue a conversation | *"Hi! I see you requested support via our {{online_chat}}…"* |

**Does NOT qualify — MARKETING:**

| Kind | Example | Note |
|---|---|---|
| **Retargeting** | *"You left {{items}} in your cart! Don't worry, we saved them. **Checkout now below.**"* | **Marketing EVEN IF user-requested** |
| Renewal push | *"Your subscription will expire on {{date}}! Renew today to save {{discount}}."* | "secure renewals" is named in the prohibition |
| Mixed content | an order update **with a promo attached** | one promotional line contaminates the whole template |
| Unclear content | body is only `{{1}}`, or *"Congratulations!"* | no discernible utility purpose |

**The retargeting row is the one that cost us three submissions.** Note what it means: a message
about an *incomplete transaction* that hands the user a link to *complete or promote* it is
marketing **by definition**, regardless of tone, and regardless of the user having asked for it.

---

## 4. Case study — the §6.1 referrer nudge, v4 → v7

The nudge tells referrer A that prospect B has not finished opening their account.

| Ver | What changed | Meta's verdict |
|---|---|---|
| v3 | original | MARKETING — and **failed at Meta** with *"restricted for higher quality messaging"* (a quality restriction, distinct from `131049`) |
| v4 | dropped *"You earn on every successful account opening."* | **MARKETING** |
| v5 | same shape; link switched to the canonical `/r/wa/{id}` form | **MARKETING** (approved, still capped) |
| v6 | dropped the CTA *"A quick personal reminder from you often helps them complete it. Share your link again"* | **MARKETING** |
| **v7** | **removed the referral LINK entirely**; pure status update on the referrer's own record | **UTILITY** ✅ |

**Why v4–v6 could never work.** All three were structurally Meta's cart-abandonment example —
*incomplete transaction + here is the link* — with a referral in place of a cart. Each revision
trimmed adjectives **around** the disqualifying element while leaving the element itself in place.
The **referral link is a cross-sell asset**: it exists to acquire a new customer, which the
prohibition names directly. Tone was never the variable.

**Second, subtler failure against condition (2).** The message is about **someone else's**
transaction. Condition 2 requires the message be specific to *the recipient's* order/account. v7
passes because it is reframed as *"an update on **your referral record**"* — a record the referrer
does own — rather than *"your friend hasn't finished, go push them."*

**v7 (holding UTILITY, EN + HI):**

```
Hi {{1}}, an update on your referral record with PIFS.

Referral: {{2}}
Status: account opening not yet complete

Our team is assisting them directly. We will message you again when this status changes.

Investments in the securities market are subject to market risks.
*Disclosures*: https://gorefer.in/d/pifs
```

**The cost, stated honestly:** v7 has **2 variables, not 3** — no `nudge_link_for()` link. The
referrer is informed but not handed a link. That is not an oversight; it is the price of condition
(1). ~~A template cannot both hand over a referral link and be UTILITY.~~ **SUPERSEDED next day —
true for the BODY only. §4b: a referral link in a URL *button* pointing at the share endpoint held
UTILITY in English.**

---

## 4b. The button exception — the v9 label matrix (2026-07-27)

With the v7 body held byte-identical, the button was made the only variable. All variants submitted
and read at **APPROVED** (a pending-state category predicts nothing — identical designs showed
opposite pending categories per language and settled differently):

| Button label | EN | HI |
|---|---|---|
| *(no button — v7/v10 control)* | UTILITY | UTILITY |
| Share Referral Link (v9a) | **UTILITY** | MARKETING |
| My Referral Link (v9b) | **UTILITY** | MARKETING |
| Share on WhatsApp (v9d) | **UTILITY** | MARKETING |
| Refer (v9e) | **UTILITY** | UTILITY* |
| Refer & Earn (v9c) | MARKETING | MARKETING |

Three rules this establishes:

1. **Placement + destination decide, not the link itself.** A referral link in the BODY, or a button
   to the *acquisition* endpoint (`/r/wa/{id}` → Zerodha signup), is the cart-abandonment pattern —
   MARKETING. A button to the **share endpoint** (`gorefer.in/share/wa/{id}` → opens the sender's own
   WhatsApp share sheet) survives UTILITY in English. Functionally the button must be `/share/wa/`
   anyway: the tapper is the referrer, who already has an account.
2. **"Earn" is the one fatal word** — v9c flipped in both languages, the only variant to do so.
3. **Hindi flips on the URL button itself**, label-independent (even "WhatsApp पर शेयर करें", which
   contains no referral or reward wording). Hindi *quick-reply* buttons have held UTILITY
   (`referrer_update_hin_2026_07_19_v2`). Ship per-language: EN with the URL button, HI without (or
   quick-reply-only), via the per-language config keys.

**Header images (verified against Meta's docs 2026-07-27):** UTILITY templates support an optional
header of any type, including image — but the same page warns a utility template *"with marketing
material… will automatically be re-categorized."* A benefits/offer poster is marketing material
relocated, the same move as v4→v6. Neutral branded imagery: fine. Benefit claims in the image: treat
as MARKETING.

**Where the benefits DO go:** the session window. A quick-reply tap opens the 24h window, where
messages have no category, no cap, and no cost — the full pitch (10% brokerage share, 300 points,
rich media) is delivered there, one tap behind the template. This is the standing pattern (owner
rules 2026-07-27, `CLAUDE.md` §6f): links in buttons, benefits in session, template body purely the
recipient's own record.

---

## 5. Authoring checklist — run before every submission

- [ ] **Is the subject the recipient's OWN order / account / transaction?** If it is about a third
      party, reframe it around the recipient's record of that relationship, or accept MARKETING.
- [ ] **Is there a link that acquires, promotes, or re-solicits in the BODY?** A referral link, a
      signup link, a "checkout" link in the body ⇒ MARKETING. A *tracking* or *status* reference is
      fine. A referral link in a **URL button → `/share/wa/{id}`** with an Earn-free label holds
      UTILITY in English (§4b); Hindi gets no URL button.
- [ ] **Any CTA urging action?** "Share again", "Renew today", "Don't miss", "Checkout now" ⇒ MARKETING.
- [ ] **Any reward / earnings / discount / offer mention?** ⇒ MARKETING.
- [ ] **Is it the cart-abandonment shape** (*something is incomplete + here's how to finish it*)? ⇒
      MARKETING, even if the user asked for it.
- [ ] **Mixed content?** One promotional line makes the whole template MARKETING. There is no partial credit.
- [ ] **Body does not END with a variable** (hard Meta rule — outright rejection, not re-categorization).
- [ ] **Positional `{{1}}…{{n}}`; `customParams` order matches** the positions; every sample realistic.
- [ ] Compliance block (market-risk + `Disclosures: https://gorefer.in/d/pifs`) is a **regulatory
      disclosure, not promotional** — it does not endanger UTILITY. v7 carries it and held UTILITY.

---

## 6. Rules of engagement (do not skip — these have teeth)

1. **Category honesty is enforced, and abuse is penalized.** Meta: *"for any business detected to be
   abusing the template categorization system, Meta will no longer provide the 24-hour notice if a
   utility template should be marketing, and will update the category with no advance notice."*
   **Do not churn resubmissions hoping one sticks.** Three flips is already a pattern on WABA 105355.
2. **A UTILITY submission that comes back MARKETING is APPROVED, not rejected.** It will send, and it
   will be capped and billed at the marketing rate. **Always read back the `category` field after
   submitting** — `ok:true` tells you nothing about the category you got.
3. **Appeals exist:** a category change can be reviewed *"up to 60 days from the date the category
   was updated."* Use it only where the copy genuinely meets the test — an appeal on marketing copy
   is what "detected abuse" looks like.
4. **The map is SSOT** (`CLAUDE.md` §6c): update the HTML conversation map → submit to Meta → update
   the map again with the verdict. This file is the *reasoning*; the map is the *state*.
5. **Session messages have NO category and NO cap.** Inside the 24h customer-service window, a
   free-form message is neither utility nor marketing. Our 7-step follow-up cadence is already
   `channel=session` for exactly this reason. **If copy cannot pass the UTILITY test, the next
   question is not "how do I word it better" but "can this be a session message instead?"**

---

## 7. The generalizable lesson

Three rejections from a vendor system is evidence **the rule has not been read**, not evidence the
rule is unsatisfiable. The failure mode here was inferring policy from the *shape of the failures*
and iterating on adjectives, instead of opening the canonical source and checking the artifact
clause by clause. The policy named the disqualifier explicitly — *retargeting*, *cross-sell* — and
one read produced a passing template on the first attempt after three failures.
