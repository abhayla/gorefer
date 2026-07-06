# GoRefer — Master Source-of-Truth (compiled from the ChatGPT discussion)

> **What this is:** The single, consolidated source-of-truth for the GoRefer Zerodha Referral Growth System, compiled from a ChatGPT discussion. It merges two artifacts — a copy-pasted discussion and a shared-link conversation transcript — into one coherent, de-duplicated document. All unique content from both sources is preserved; overlapping passages (URL scheme, workflow diagrams, message templates) are kept once.
>
> **Date of consolidation:** 2026-07-04
>
> **Source files (both in `C:\Abhay\5Wealths\GoRefer`):**
> 1. `ChatGPT-Discussion-formatted.md` — the richer artifact; contains the detailed 14-section GoRefer product/technical blueprint plus the "Response 1 / Response 2" comparison.
> 2. `GoRefer-ChatGPT-Full-Formatted.md` — the share-link conversation transcript (share URL `https://chatgpt.com/share/6a489986-add8-83ee-9971-403b921314be`); contains the original user prompts, the ASCII workflow diagrams, the URL-strategy table, message-template blockquotes, and the "One Thing I'd Change" recommendation.
>
> **Fidelity note:** This document is faithful to the ChatGPT source material. No outside design decisions or opinions have been injected. Where the two sources genuinely conflict, the conflict is flagged inline with a `> NOTE: source conflict` callout rather than silently resolved.

---

## Table of Contents

1. [Overview & Core Concept](#1-overview--core-concept)
2. [Original Source Material (User Inputs)](#2-original-source-material-user-inputs)
3. [Workflow Diagrams](#3-workflow-diagrams)
4. [Multi-Channel Referral Growth System](#4-multi-channel-referral-growth-system)
5. [URL Strategy & Link Cloaking](#5-url-strategy--link-cloaking)
6. [Detailed Product & Technical Specification (14 Sections)](#6-detailed-product--technical-specification-14-sections)
7. [Most Important Change / Design Priority](#7-most-important-change--design-priority)
8. [Appendix: Response 1 vs Response 2](#appendix-response-1-vs-response-2)

---

## 1. Overview & Core Concept

GoRefer should be treated as a **Referral Growth Platform**, not just a WhatsApp campaign. Every touchpoint has one goal:

> Increase Zerodha referrals by making it effortless for existing customers to refer friends while preserving referral attribution and maximizing conversion rates.

The key insight from the discussion is that there are **two separate workflows**, and the opportunity is to combine them:

1. **Zerodha's official referral workflow** — the customer generates a link, shares it, and the friend opens an account.
2. **The enhanced (team-assisted) workflow** — the AP team helps the friend with account opening.

The biggest bottleneck **isn't getting referrals — it's preserving the referral mapping while making the process effortless.** GoRefer solves this by sitting as a **referral management layer** between WATI and Zerodha: it knows the customer ID, generates the referral link, stores friend details, assigns an executive, tracks progress, and records outcomes. Zerodha remains the underlying brokerage platform. This separation makes the system reusable across future referral programs (insurance, mutual funds, loans, other brokers).

---

## 2. Original Source Material (User Inputs)

### 2.1 The original request

> Refer attached image for New Zerodha Account opening. Now on similar lines, create image for Zerodha account referral. Update the scanner to open this link: `https://signup.zerodha.com/api/lead?c=ZMPHZC`
>
> Do not proceed until you have more than 95% confidence of my ask. Ask me questions until you get that confidence. Ask one question at a time.

### 2.2 The referral message text / asset (`zerodha-refer.svg`)

> **You already have an account in Zerodha.**
>
> Now Refer your friends to earn rewards!
>
> 1. **10% brokerage share** — earn 10% of the brokerage that every eligible referred account generates.
> 2. **300 reward points** — receive 300 reward points per account opened.
>
> **Eligibility** — at least 3 successful referrals in the past 12 months.
>
> **Follow these steps to refer:**
>
> 1. Click Referral Link to refer friend
> 2. Reply to this message and share friend's Name and Mobile
> 3. We will contact and help in Free and Fast account opening
> 4. Once account opened, you start getting referral benefits
>
> **Links:**
> - Referral Link — `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}`
> - Open Zerodha Account — `https://signup.zerodha.com/?c=ZMPHZC`
> - View Referral and Rewards — `https://console.zerodha.com/refer`

### 2.3 Official Zerodha rules (step by step)

**Step 1** — Customer has a Zerodha account. Example: Client ID `AB1234`.

**Step 2** — Customer generates a referral link. Example: `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB1234`

**Step 3** — Customer shares this link, via WhatsApp, SMS, Email, Facebook, LinkedIn, or Copy Link.

**Step 4** — Friend clicks the link. This creates the referral mapping.

**Step 5** — Friend completes account opening. Important:
- Account must be opened within **60 days** of referral.
- If the prospect had already registered on Zerodha **before** using the referral link, the referral mapping won't apply.

**Step 6** — Friend starts trading. Now 300 reward points are credited, and brokerage sharing starts (subject to eligibility).

> Source reference cited in the transcript: [Zerodha Support — How do I refer Zerodha to my friends or family?](https://support.zerodha.com/category/console/profile/account/articles/how-do-i-refer-zerodha-to-my-friends-or-family)

The brokerage-sharing benefit requires meeting Zerodha's eligibility conditions (such as maintaining at least three successful referrals in the past 12 months).

---

## 3. Workflow Diagrams

### 3.1 Workflow 1 — Official Zerodha Referral Workflow

```
Existing Zerodha Customer
        │
        ▼
Generates Referral Link
        │
        ▼
Shares Link
        │
        ▼
Friend Clicks Link
        │
        ▼
Friend Opens Account
(within 60 days)
        │
        ▼
Referral Mapping
        │
        ▼
Friend Starts Trading
        │
        ▼
Referrer Earns:
• 300 Reward Points
• 10% Brokerage Share*
```

\* The brokerage-sharing benefit requires meeting Zerodha's eligibility conditions (such as maintaining at least three successful referrals in the past 12 months).

### 3.2 Where customers struggle

```
Generate Link
     ↓
Share Link
     ↓
Explain Zerodha
     ↓
Explain KYC
     ↓
Help Friend
     ↓
Follow Up
     ↓
Check Status
```

**Most customers don't want to do all this.** This is the friction GoRefer removes.

### 3.3 Workflow 2 — Enhanced (team-assisted) workflow

```
Customer
      │
      ▼
Receives WhatsApp Campaign
      │
      ▼
Option 1
Share Friend's Details
      │
      ▼
Your Team
      │
      ▼
Calls Friend
      │
      ▼
Explains Zerodha
      │
      ▼
Assists KYC
      │
      ▼
Account Opens
```

**Critical step — the referral link:** You must ensure the friend's account is opened through the customer's own referral link so the referral is attributed correctly. The team must use or share the customer's personalized referral URL **before** the prospect completes account opening. If someone registers directly on Zerodha first and only later uses the referral link, the referral won't be mapped.

### 3.4 The ideal workflow

```
Customer receives WhatsApp
        │
        ▼
Replies:
  Friend Name
  Friend Mobile
        │
        ▼
Your CRM
        │
        ▼
Automatically generates
  Referral Link
        │
        ▼
Your executive calls friend
        │
        ▼
Sends THAT customer's referral link
        │
        ▼
Friend opens account
        │
        ▼
Referral mapped correctly
        │
        ▼
Customer earns rewards
```

This keeps the customer's effort minimal while preserving referral attribution.

### 3.5 Bot + executive automation (Meta API + WATI)

```
Campaign
   ↓
Customer replies
   ↓
Bot asks: Friend Name?
   ↓
Friend Mobile?
   ↓
Bot stores CRM
   ↓
Executive assigned
   ↓
Executive gets:
  Customer Name
  Customer Client ID
  Referral Link
  Friend Details
   ↓
Call initiated
```

At that point, the executive already has everything needed before making the first call.

### 3.6 GoRefer as the layer between WATI and Zerodha

```
WATI
   │
   ▼
GoRefer
   │
   ├── Knows Customer ID
   ├── Generates Referral Link
   ├── Stores Friend Details
   ├── Assigns Executive
   ├── Tracks Progress
   └── Records Outcomes
           │
           ▼
        Zerodha
```

This architecture gives: one place to manage referrals; visibility into the referral pipeline; reduced manual work; and the ability to extend the same platform later to insurance, mutual funds, loans, and other products. GoRefer becomes the **referral management layer**; Zerodha remains the underlying brokerage platform.

---

## 4. Multi-Channel Referral Growth System

### 4.1 System-level branching diagram

```
Referral Growth System

                   Existing Zerodha Customer
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
 WhatsApp Campaign      WhatsApp Status      Social Media Posts
        │                     │                     │
        └───────────────► Referral Landing Page ◄──┘
                              │
                              ▼
                 Customer chooses referral method
                 ├── Share friend's details
                 └── Share personalized referral link
                              │
                              ▼
                    Friend opens Zerodha account
                              │
                              ▼
                 Referral mapped to customer
                              │
                              ▼
               Customer earns Zerodha rewards
```

### 4.2 WATI / Meta WhatsApp Template

Targets existing Zerodha customers.

- **Header:** Referral poster (premium image)
- **Body:** Personalize with customer name; mention the rewards; recommend the easiest option (share friend's details); also include the customer's personalized referral link.
- **CTA:** Should encourage replies rather than just clicks.

Example variables:

- `{{1}}` = Customer Name
- `{{2}}` = Customer Referral Link
- `{{3}}` = Partner Link (your AP account-opening link)

### 4.3 WhatsApp Status (customer posts)

Status doesn't support clickable links, so the objective changes. Instead of "Scan QR", use:

```
🎁 Earn Zerodha Referral Rewards!

Get:
✔ 10% Brokerage Share*
✔ 300 Reward Points

Interested?
Message me.
```

Then include the customer's referral link and the AP link:

```
My Referral Link
https://z.gorefer.in/{{client_id}}

Need Help?
https://z.gorefer.in/open
```

### 4.4 WhatsApp Status Image

Avoid lots of text. Visual hierarchy:

```
Refer Friends
Earn Rewards
10% Brokerage
300 Reward Points

My Referral Link
z.gorefer.in/AB123

Need Help?
Open through
z.gorefer.in/open
```

Much better than QR codes.

### 4.5 Facebook Post (clickable URLs supported)

```
🎁 Already planning to invest?

Open your FREE Zerodha account using my referral link.

My Referral Link:
{{Customer Referral Link}}

Need help?
Open through our partner:
{{Partner Link}}
```

### 4.6 Instagram (captions not clickable)

```
Referral Link
👇
z.gorefer.in/AB123
```

or "Link in Bio" — the bio points to `gorefer.in`.

### 4.7 LinkedIn (professional tone)

```
Investing soon?

I'd appreciate it if you used my Zerodha referral link.
{{Customer Referral Link}}

If you need assistance with account opening, here's a partner who can help:
{{Partner Link}}
```

### 4.8 Twitter / X (concise)

```
Thinking of opening a Zerodha account?

Use my referral link:
{{Customer Link}}

Need assistance?
{{Partner Link}}
```

### 4.9 Email Template

- **Subject:** Earn Zerodha Referral Rewards
- **Body:** Explain benefits.
- **Large button:** Share Referral Link
- **Secondary button:** Need Help Opening Account?

### 4.10 Referral Landing Page

Customer shares a referral URL; the friend lands on a page that displays:

```
Open Zerodha Account
Continue
```

Below that:

```
Need Assistance?
We'll help you complete KYC.
Contact Us
```

The page then redirects to `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB123`.

### 4.11 Partner Link (both links always present)

The user's requirement: both the customer link and the partner link should always be present.

- **Customer Link (My Referral Link):** `https://z.gorefer.in/{{client_id}}` — Purpose: Customer earns rewards.
- **Partner Link (Need Assistance?):** `https://z.gorefer.in/open` — Purpose: Lead comes to your team; you help with documentation; eventually redirect using the customer's referral link whenever appropriate so the customer receives referral credit.

---

## 5. URL Strategy & Link Cloaking

### 5.1 Recommended URL strategy

| Purpose | URL |
| --- | --- |
| Customer Referral | `z.gorefer.in/{{client_id}}` |
| Partner Account Opening | `z.gorefer.in/open` |
| Referral Benefits | `z.gorefer.in/rewards` |
| Referral FAQ | `z.gorefer.in/help` |
| Track Rewards | `z.gorefer.in/track` |

### 5.2 The one thing to change — never expose Zerodha URLs

Do **not** expose Zerodha URLs anywhere.

- Instead of `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}`, customers always see `https://z.gorefer.in/{{client_id}}`.
- Instead of `https://signup.zerodha.com/?c=ZMPHZC`, they see `https://z.gorefer.in/open`.

The server then redirects to the appropriate Zerodha URL. Advantages: cleaner, more memorable links; ability to track clicks and campaign performance; freedom to change the destination later without updating every template or poster; consistent branding across WhatsApp, social media, emails, and printed materials. This also scales naturally when adding other referral programs under `gorefer.in`.

> **NOTE: source conflict — customer referral URL scheme.** The multi-channel/URL-strategy sections use the customer's **raw `client_id`** in the public link (`z.gorefer.in/{client_id}`, e.g. `z.gorefer.in/AB123`), whereas the detailed 14-section spec (Sections 3, 5, 6) uses an **opaque token** (`z.gorefer.in/r/{token}`, e.g. `z.gorefer.in/r/A7K29P`) that internally maps token → client_id. The token scheme is the later, more security-conscious design (it hides the raw client_id); the raw-client_id scheme is simpler and appears in the earlier message-template examples. This is unresolved in the source — pick one before implementation.

---

## 6. Detailed Product & Technical Specification (14 Sections)

> This is the implementation-ready blueprint (ChatGPT "Response 2"), detailed enough for Claude Code to implement the complete system end-to-end: backend, frontend, WATI integration, redirects, analytics, dynamic posters, and the referral funnel.

### 6.1 Business Objective

**Primary Goal:** Increase successful Zerodha account openings through referrals.

**Secondary Goals:** Maximize referral attribution; reduce customer effort; increase WhatsApp sharing; track the entire funnel; create a reusable platform for future partners.

### 6.2 Key Actors

**Actor A — Existing Zerodha Customer**
Has: `client_id`, `name`, `mobile`, `email`.
Can: refer friends; share referral link; share status; share social posts; submit friend details.
Receives: 300 Reward Points; 10% Brokerage Share (eligible customers).

**Actor B — Friend / Prospect**
May: open account directly; request callback; need assistance.

**Actor C — Your Team**
Can: call prospects; assist KYC; track progress; trigger reminders.

**Actor D — Admin**
Can: create campaigns; view analytics; monitor funnel.

### 6.3 Domain Architecture

- **Primary Domain:** `gorefer.in`
- **Zerodha Subdomain:** `z.gorefer.in`

**URL Structure:**

- Customer Referral Page — `z.gorefer.in/r/{token}` (example: `z.gorefer.in/r/A7K29P`)
- Open Account — `z.gorefer.in/open`
- Referral Benefits — `z.gorefer.in/rewards`
- FAQ — `z.gorefer.in/help`
- Track Referral — `z.gorefer.in/track`
- Generate Referral Assets — `z.gorefer.in/assets`

### 6.4 Data Model

**Customer**

```
Customer
---------
id
client_id
name
mobile
email
token
status
created_at
updated_at
```

Example: `client_id = AB1234`, `token = A7K29P`

**Referral Lead**

```
ReferralLead
------------
id
customer_id
friend_name
friend_mobile
friend_email
source
status
created_at
updated_at
```

Source values: `whatsapp_campaign`, `whatsapp_status`, `facebook`, `instagram`, `linkedin`, `direct_link`, `manual`.

**Click Tracking**

```
Click
-----
id
customer_id
url
ip
device
browser
utm_source
utm_campaign
created_at
```

**Referral Journey**

```
ReferralJourney
---------------
id
lead_id
step
timestamp
metadata
```

### 6.5 Referral Link System

**DO NOT expose:** `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB1234`

**Instead:** `https://z.gorefer.in/r/A7K29P`

System mapping:

```
A7K29P
   ↓
AB1234
   ↓
https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB1234
```

Benefits: Analytics, Tracking, Branding, Security.

### 6.6 Landing Page Flow

Customer shares `z.gorefer.in/r/A7K29P`. Friend clicks.

**PAGE 1**

- Headline: **Open Your FREE Zerodha Account**
- Benefits: ₹0 Account Opening; Fast Digital KYC; Trusted by Millions; Powerful Trading Platforms
- CTA: **Open Account**
- Secondary CTA: **Need Help?**

**OPEN ACCOUNT** → Redirect: `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB1234`

**NEED HELP** → Form:
- Name
- Mobile
- City

Lead stored.

> **NOTE: source conflict — lead-capture fields.** The landing-page "Need Help" form (Section 6.6) captures **Name / Mobile / City** (three fields), while the WhatsApp bot flow (Section 6.8) captures only **Name / Mobile** (two fields). The sources do not reconcile whether "City" is required on both paths — decide the canonical lead schema before implementation.

### 6.7 WhatsApp Campaign System

**Template 1 — Awareness**

```
Hi {{name}}

🎁 Earn Rewards by Referring Friends & Family

Reply "REFER" to learn more.
```

Buttons: Refer Now · Learn More

**Template 2 — Action**

```
Hi {{name}}

Earn:
  10% Brokerage Share
  300 Reward Points

Option 1: Share Friend Name + Mobile
Option 2: Share your referral link

{{referral_link}}
```

### 6.8 WhatsApp Bot Flow

```
User clicks: Refer Now
   ↓
Bot: Friend Name?
User: Rahul Sharma
   ↓
Bot: Friend Mobile?
User: 9876543210
   ↓
Bot: Thank you. Our team will contact Rahul.
   ↓
Lead created.
```

### 6.9 WhatsApp Status System

**Challenge:** Status doesn't support dynamic links.

**Solution:** Generate personalized status assets.

**Asset Generator**

- Input: `client_id`, `name`
- Output: PNG containing — Refer Friends; Earn Rewards; 10% Brokerage; 300 Reward Points; My Referral Link: `z.gorefer.in/r/A7K29P`
- Button: **Download Status**

### 6.10 Social Sharing System

Generate:

**Facebook Post**

```
Thinking of opening a Zerodha account?

Use my referral link:
{{link}}

Need help?
{{partner_link}}
```

- **LinkedIn** — Professional variant.
- **Instagram** — Caption variant.
- **Twitter** — Short variant.

### 6.11 Referral Asset Generator

Customer visits `z.gorefer.in/assets`. Generate:

- **Asset A** — WhatsApp Status (1080×1920)
- **Asset B** — Instagram Story (1080×1920)
- **Asset C** — Instagram Post (1080×1080)
- **Asset D** — Facebook Post (1200×630)
- **Asset E** — Referral PDF (Interactive PDF)

Interactive PDF contains buttons: Open Account; Refer Friend; Track Rewards; Contact Support.

### 6.12 Analytics

**Campaign:** Delivered; Read; Clicked; Replied.

**Referral:** Links Shared; Clicks; Leads; Accounts Opened; Reward Earned.

**Customer:** Leaderboard — Top Referrers.

### 6.13 Admin Panel

- **Customers** — Search by `client_id`, `mobile`, `name`.
- **Referral Leads** — Status: New; Contacted; Interested; KYC Started; Account Opened; Rejected.
- **Campaigns** — Create: WhatsApp, Email, SMS.
- **Assets** — Generate.
- **Analytics.**

### 6.14 Future-Ready Architecture

Today: `z.gorefer.in`

Tomorrow:
- `groww.gorefer.in`
- `upstox.gorefer.in`
- `insurance.gorefer.in`
- `mf.gorefer.in`

Same platform. Different partner.

---

## 7. Most Important Change / Design Priority

Don't make the referral workflow depend on customers understanding referral links. The platform should always push users toward:

> ⭐ **Recommended:** Share Friend Name + Mobile

because that produces the highest conversion rate.

The personalized referral link should remain available everywhere (WhatsApp, Status, Facebook, Instagram, PDF, Landing Pages), but it should be the **secondary path**. The team-assisted onboarding flow will almost certainly convert better than expecting customers to educate and follow up with their friends themselves.

---

## Appendix: Response 1 vs Response 2

During the discussion, ChatGPT presented an A/B response comparison ("You're giving feedback on a new version of ChatGPT. Which response do you prefer?").

**Response 1 (marked preferred by the user):** A framing statement — "Since you plan to hand this to Claude Code for end-to-end implementation, I'll give you a detailed product + technical specification for the Zerodha Referral Growth System using WATI + Meta WhatsApp API + `gorefer.in`. This is written as an implementation-ready blueprint." The user marked: *"I prefer this response."*

**Response 2 (the detailed GoRefer platform specification):** The full 14-section blueprint reproduced above in Section 6. Despite Response 1 being marked "preferred," Response 2 is the artifact that actually contains the detailed spec, so its content is retained here in full as the implementation blueprint.

---
## Later ChatGPT Additions (2026-07-04)

### Addition 1 — Recommended Project Structure & Model Role Division
Recommended repo structure:
```
GoRefer/
├── docs/  (PRD.md, Functional_Spec.md, Technical_Architecture.md, Database_Design.md, API_Specification.md, WATI_Templates.md, Referral_Workflows.md, UI_UX_Guidelines.md, Testing_Checklist.md)
├── tasks/ (Phase_1.md, Phase_2.md, Backlog.md)
├── CLAUDE.md
└── README.md
```
Role division proposed by ChatGPT: ChatGPT = product manager / solution architect / UX reviewer / API designer / marketing strategist / testing & code-review guidance ("technical co-founder producing implementation-ready specs"). Claude Code = software engineer (implementation, refactoring, testing, debugging, code generation) — the "implementation engine." Rationale: scales as GoRefer grows beyond Zerodha.

### Addition 2 — "Referral Intelligence Layer" architecture stance
Do NOT make z.gorefer.in merely a redirect service — make it a "Referral Intelligence Layer" that every click, poster download, WhatsApp campaign, social share, reminder, and account-opening journey passes through FIRST. Benefits: complete analytics, campaign attribution, CRM integration, automated follow-ups, dynamic content generation, and a reusable platform for insurance/mutual funds/loans/other partners. "Zerodha becomes one destination; GoRefer manages the entire referral lifecycle." Also: a personalized-poster route (e.g. z.gorefer.in/poster) where GoRefer knows the customer from the token and auto-generates poster + referral link + QR + customer name + reward details — a different poster per customer, no manual work.

### Addition 3 — Referral OS vision, 15-phase build plan, task-granularity model
Working model: Founder (Abhay) → CPO + Solution Architect + QA (ChatGPT) → CTO + Engineering (Claude Code). ChatGPT can't talk to Claude Code directly; ~95% automated — ChatGPT writes specs into git (docs/ + tasks/), Claude Code implements, Abhay reviews/approves/pastes summaries back.
Referral OS vision: the referral engine knows nothing about Zerodha; it only knows Referral → Token → Campaign → Partner → Destination → Analytics → Reward Rules. Zerodha is just the first "plugin"; future: Groww, Angel, Upstox, Insurance, Loans, Mutual Funds, Credit Cards.
15-phase plan:
```
Phase 0  Architecture (no code): Vision, PRD, Architecture, UX, Database, APIs, Referral/WATI/Social/Analytics workflows
Phase 1  Repository: gorefer/ (backend/ frontend/ mobile/ docs/ infra/ scripts/)
Phase 2  Authentication: Users, Partners, Admins, Executives
Phase 3  Referral Engine: generate token -> store Client ID + Partner + Campaign -> z.gorefer.in/r/{token}
Phase 4  Redirect Engine: open link -> analytics -> CRM -> landing page -> redirect
Phase 5  Landing Pages: dynamic, customer-specific
Phase 6  Poster Generator: PNG, PDF, QR, referral link
Phase 7  WhatsApp: WATI, Meta, templates, automation
Phase 8  CRM: lead assignment, executives, pipeline
Phase 9  Analytics: every click/redirect/account/poster
Phase 10 Admin Portal: dashboard, campaigns, users, referral status, executives
Phase 11 Social Sharing: FB, IG, LinkedIn, Twitter, WhatsApp
Phase 12 Gamification: leaderboard, badges, milestones
Phase 13 Notifications: email, WhatsApp, SMS, push
Phase 14 AI: auto-writes messages, status, captions, poster text, campaigns
```
Task-granularity: issue small precise tasks, each like "Task 0001 — Implement Referral Token Generator" with Problem Statement, Why, UI, UX, API, Database, Edge Cases, Acceptance Criteria, Test Cases, Security, Performance, Claude Prompt. One task at a time, review, move on.
Scale estimate before coding: ~40–60 architecture docs, ~150–250 implementation tasks, full DB schema, REST/OpenAPI spec, wireframes, state diagrams, security model, deployment architecture, WATI + Meta integration, referral engine, analytics engine. Design fully first so Claude Code implements almost mechanically.

### Addition 4 — Vertical Slice Agile, Sprint Structure, Design Authority & the GoRefer Constitution
Vertical Slice Agile: Sprint 1 is NOT "Zerodha Referral" — it is "Referral Engine v1 (using Zerodha as the only implementation)." Avoid hardcoding "Zerodha" (DB/APIs/UI/analytics/posters/QR/WhatsApp/reports). From Day 1 create ONE concept: "Referral Program." Sprint 1 has exactly one program (Name: Zerodha, Partner Code: ZMPHZC); architecture already provider-agnostic. Build vertical slices, not horizontal layers — every sprint ships something usable and deployable end-to-end.
Sprint structure:
```
Sprint 0  Architecture (no code): Product Vision, PRD, User Stories, Database Design, API Design, Wireframes, Folder Structure, Coding Standards, Definition of Done, Security Model
Sprint 1  Complete referral flow end-to-end: customer -> referral link -> share -> friend opens account -> analytics recorded -> redirect to Zerodha
Sprint 2  Customer Dashboard: referral links, QR code, click count, generate poster
Sprint 3  WhatsApp Automation: WATI, Meta, templates, dynamic variables, personalized messages
Sprint 4  Landing Pages: Benefits / Need Help? / FAQ before continue
Sprint 5  CRM: leads, executives, assignment, status
Sprint 6  Social Media Kit: auto-generate FB, IG, WhatsApp Status, LinkedIn
Sprint 7  Analytics: funnels, conversions, campaign performance
Sprint 8  Admin Panel
```
Product-thinking pipeline per sprint: Epic → Features → User Stories → Acceptance Criteria → API → Database → Frontend → Backend → Tests → Deployment → Documentation.
Design Authority: Abhay = Product Owner (business priorities, approves scope); ChatGPT = Product Architect & Design Authority (vision, architecture, UX, APIs, backlog quality, reviews); Claude Code = Engineering (implements to spec). Claude Code never invents features; suggestions come back for review. Prevents architectural drift.
GoRefer Constitution (create before Sprint 0, ~10–15 pages, non-negotiable, checked against every design decision): every referral link must be trackable; no hardcoded partner logic; every user action measurable; every page mobile-first; all links shareable; all marketing assets generated dynamically; manual work eliminated wherever feasible; every feature exposes APIs before UI; platform remains provider-agnostic even if Sprint 1 only supports Zerodha.

### Addition 5 — Sprint 0 Foundation: Deliverables, GoRefer Constitution v1, Agile Cadence, Sprint 1 Goal, Decision Log (ADR), and Master PRD
**Sprint 0 – Foundation.** Objective: design everything once, build incrementally. Goal: when Claude Code starts coding it should almost never ask "what should I do?" — only "how do I implement this?"

**Sprint 0 Deliverables (in order; all owned by ChatGPT):**

```
1.  GoRefer Constitution
2.  Product Vision
3.  Product Requirements Document (PRD)
4.  User Personas
5.  Complete User Journey
6.  Functional Requirements
7.  Non-Functional Requirements
8.  Database Design
9.  API Specification
10. Backend Architecture
11. Frontend Architecture
12. WATI Integration
13. Meta API Integration
14. Analytics Framework
15. Security Model
16. Sprint Backlog (Phase 1)
```

**GoRefer Constitution v1 (12 principles):**

```
1.  Mobile First — designed for mobile, not merely responsive (most referrals start on WhatsApp).
2.  Zero Friction — remove every possible click; no "download PDF", no copying long links, no scanning a QR on the same phone; prefer one-tap Share/Open.
3.  Track Everything — record every important event (link created, link opened, landing page viewed, WhatsApp button clicked, QR scanned, redirect completed, account opened, referral rewarded). If we can't measure it, we can't improve it.
4.  Never Expose Internal Logic — users never see Zerodha URLs, partner codes, internal IDs, or database IDs; they only interact with GoRefer.
5.  Automation First — before any manual step, ask "can software do this?"; if yes, automate.
6.  Human Assistance Only When It Adds Value — automation handles repetitive work; humans handle trust, guidance, edge cases (KYC doubts, first-time investors, complex queries).
7.  Every Asset Is Dynamic — no static posters, QR codes, or hardcoded links; everything generated dynamically.
8.  Platform, Not Project — although Sprint 1 supports only Zerodha, no component is named/designed as Zerodha-only (ReferralProgram OK, ZerodhaReferral NOT unless it's a plugin/adapter).
9.  Security by Default — signed links where appropriate, no exposed client IDs, rate limiting, audit logs, encryption for sensitive data, least privilege. Built in, not added later.
10. User Always Has a Choice — offer multiple paths (share referral link / share friend's contact / contact advisor).
11. Build Once, Reuse Everywhere — every feature exposed as a service (e.g. Poster Generator serves WhatsApp, Email, Facebook, Admin portal, API); no duplicate implementations.
12. AI Is an Assistant, Not a Requirement — AI enhances (marketing copy, personalization, suggestions) but the core referral workflow must work even if AI services are unavailable.
```

**Agile process (strict cadence):** 1. Design (ChatGPT produces spec) → 2. Review (Abhay approves/changes) → 3. Implement (Claude Code builds exactly what's approved) → 4. Verify (ChatGPT reviews implementation vs spec) → 5. Refine (improvements go into the next sprint, not ad hoc).

**Sprint 1 Goal (vertical slice)** — at end of Sprint 1 a real customer can: (1) receive a WhatsApp campaign, (2) get their personalized referral link, (3) share it with a friend, (4) friend opens the GoRefer link, (5) GoRefer records analytics, (6) friend is redirected to Zerodha with correct partner + referral info, (7) system tracks the referral journey. A complete working product even without dashboards/advanced automation.

**Decision Log (Architecture Decision Records / ADR).** Record every important architectural decision with ID, Decision, Reason. Examples:

```
ADR-001 — Use opaque referral tokens instead of exposing client IDs — better security and flexibility.
ADR-002 — All external links go through GoRefer before redirecting — enables analytics and future enhancements.
ADR-003 — Mobile-first UI — majority of traffic originates from WhatsApp.
```

**Next deliverable recommended by ChatGPT:** a master PRD of ~80–120 pages that defines the product comprehensively (no assumptions, no vague requirements, clear acceptance criteria, edge cases identified, UX flows documented, APIs and data models aligned with business goals) so Claude Code can implement Sprint 1 with minimal ambiguity.

### Addition 6 — Domain-Model-First Approach, Development Lifecycle, Core Objects, Roles, and the "Engines not Pages" Module Design
**Reframing:** think like building a SaaS product, not a website. CHANGE from the earlier proposal: do NOT write the PRD first. Instead define the Domain Model first (like Stripe, Linear, Notion, Shopify). Once the domain is correct, the PRD is easier and Claude Code produces better code.

**GoRefer Development Lifecycle (coding is only step 8):**
```
Business Idea -> Business Domain -> Domain Model -> User Journeys -> PRD -> Architecture -> Sprint Planning -> Claude Implementation -> QA -> Production
```

**Step 1 — Business Domain.** GoRefer is a "Referral AUTOMATION Platform" (not merely a referral platform / link generator). That one word is the North Star. It automates: Referral Links, Landing Pages, Posters, WhatsApp, CRM, Analytics, Follow-ups, Campaigns.

**Step 2 — Core Domain Objects (10):**
1. Referral Program (Zerodha is just ONE program; future: Groww, Angel One, Insurance, Loans)
2. Partner (Passive Income Financial Solutions Pvt Ltd; partner code ZMPHZC)
3. Customer (existing Zerodha client; e.g. Client ID AB1234)
4. Prospect (future customer, not yet onboarded)
5. Referral (the act: Customer invites Prospect)
6. Campaign (WhatsApp / Facebook / Status / Email campaign)
7. Landing Page (every referral lands somewhere, not necessarily Zerodha immediately)
8. Conversion (Prospect opened account -> converted)
9. Reward (300 points, 10% brokerage)
10. Analytics Event (click, QR, poster, status, redirect, conversion — everything)
Note: WhatsApp / Facebook / Instagram are NOT domain objects — they are merely Channels.

**Step 3 — User Roles (6):** Super Admin (owns platform), Partner Admin (Abhay), Executive (calls leads), Customer (existing Zerodha client), Prospect (potential client), Visitor (someone browsing).

**Step 4 — The biggest mistake to avoid.** Wrong model: Customer -> Referral Link -> Done. Correct model: the real product is a set of journeys — Referral Journey -> Prospect Journey -> Conversion Journey -> Reward Journey. The link is merely Step 2, not the product.

**Step 5 — Product Modules (10 "Engines"; each could become an API):**
```
Module 1  Referral Engine
Module 2  Campaign Engine
Module 3  Landing Engine
Module 4  Poster Engine
Module 5  CRM Engine
Module 6  Analytics Engine
Module 7  Reward Engine
Module 8  Admin Engine
Module 9  Notification Engine
Module 10 AI Engine
```

**Sprint 1 scope per engine (implement only enough to support Zerodha):**
- Referral Engine: ✅ generate referral URLs; ❌ multi-level referrals; ❌ referral trees
- Campaign Engine: ✅ WATI; ❌ SMS; ❌ Email
- Landing Engine: ✅ Zerodha; ❌ Groww
- Reward Engine: ✅ display Zerodha reward info; ❌ calculate rewards ourselves (Zerodha remains source of truth)
- Analytics: ✅ click tracking; ✅ redirect tracking; ❌ advanced dashboards

**"Engines, not pages" philosophy.** Claude Code builds engines, not pages. Example: the Poster Engine knows NOTHING about Zerodha — it receives Title, Subtitle, Referral Link, QR, Logo, Theme, CTA and generates a poster. The same engine later generates Zerodha / insurance / mutual-fund posters with no code changes, just different data. Same applies to Landing Engine, Campaign Engine, Notification Engine. This separation keeps the product maintainable as it grows.

**Next deliverable recommended by ChatGPT: "GoRefer Domain Model & System Architecture"**, including:
1. Complete Entity Relationship Diagram (ERD)
2. Database schema (all tables and relationships)
3. Module boundaries and responsibilities
4. Event-driven architecture (events emitted and consumed)
5. End-to-end referral lifecycle
6. API boundaries between modules
7. Folder structure for the codebase
8. Technology stack recommendations
9. Security architecture
10. Sprint 1 implementation map
This becomes the foundation for every sprint; from it derive the PRD, backlog, APIs, and tasks.

### Addition 7 — GoRefer Sprint 0 Document (Vision, Metrics, Personas, Journeys, Events, Modules, Token, URLs, State Machine, Referral Kit, MLP)

**PART 1 — Vision & Mission.**
- Vision: "Build India's most intelligent Referral Automation Platform that enables businesses and customers to create, distribute, track, automate and optimize referral campaigns across every digital channel." (Deliberately does NOT mention Zerodha, WhatsApp, or Financial Services.)
- Mission (Sprint 1): "Make it ridiculously easy for an existing Zerodha customer to refer friends while maximizing conversion and minimizing manual effort."

**PART 2 — Success Metrics (North Star).**
North Star metric: Successful Referred Account Openings. Supporting KPIs:
- Acquisition: Campaign Sent, Delivered, Opened, CTR
- Referral: Referral Link Generated, Shared, Opened
- Conversion: Landing Viewed, Redirect, Zerodha Signup Started, Zerodha Signup Completed
- Revenue: Reward Points, Brokerage Share
- Platform: Poster Downloads, WhatsApp Shares, Social Shares, QR Scans

**PART 3 — User Personas (5; note: NO developer persona — we don't build for developers):**
1. Existing Zerodha Customer — goal: earn referral rewards; pain: "I don't want to explain Zerodha to everyone"; needs: one click.
2. Friend — goal: open account quickly; pain: "I don't know how"; needs: help.
3. Executive — goal: convert referrals; pain: leads scattered; needs: CRM.
4. Partner Admin (Abhay) — goal: increase referrals; needs: analytics.
5. Super Admin — goal: manage platform.

**PART 4 — User Journey Mapping (journeys, not screens; nobody's journey begins with "Generate QR"):**
```
Journey A (Customer):  Receives WhatsApp -> Interested -> Clicks -> Gets Referral Link -> Shares -> Friend Opens -> Reward
Journey B (Friend):    Receives Referral -> Curious -> Landing Page -> Trust -> Open Account -> KYC -> Account Created
Journey C (Executive): New Lead -> Assigned -> Call -> Guide -> Follow-up -> Converted
Journey D (Partner):   Dashboard -> Campaign -> Analytics -> Optimize -> More Referrals
```

**PART 5 — Domain Events (everything is a business event; makes analytics almost free):**
CustomerRegistered, ReferralLinkCreated, ReferralLinkOpened, LandingViewed, WhatsAppClicked, PosterDownloaded, ReferralShared, LeadCreated, ExecutiveAssigned, ExecutiveCalled, SignupStarted, SignupCompleted, ReferralConfirmed, RewardReceived.

**PART 6 — System Modules (each independent):**
```
Module A  Identity: Users, Partners, Roles
Module B  Referral Engine: Generate, Resolve, Track, Expire
Module C  Campaign Engine: WhatsApp, Status, Facebook, Instagram, LinkedIn
Module D  Poster Engine: Image, PDF, QR, Dynamic
Module E  Landing Engine: Landing Pages, Redirects, FAQs, CTA
Module F  Analytics: Funnels, Clicks, Conversions, Campaigns
Module G  CRM: Leads, Executives, Assignments
Module H  Notification Engine: WhatsApp, SMS, Email, Push
Module I  Admin: Everything
```

**PART 7 — Referral Token Design.** Do NOT use URLs like `...?r=AB1234`. Instead `z.gorefer.in/r/8DKPXM`, where internally 8DKPXM -> AB1234 -> Partner -> Campaign -> Program -> Created -> Expiry. Benefits: more secure, looks professional, shorter, can revoke, analytics, multi-program ready. (NOTE: this token design is ChatGPT's recommendation and conflicts with Abhay's later Cowork preference for raw client_id / no token — see GoRefer-Build-Spec-Cowork-Decisions.md; identifier scheme is a live open decision.)

**PART 8 — URL Strategy (conventions; expose no Zerodha internals):**
```
gorefer.in                  Public landing
z.gorefer.in                Zerodha
z.gorefer.in/r/XXXXXX       Referral
z.gorefer.in/open           Open account
z.gorefer.in/rewards        Rewards
z.gorefer.in/help           Help
z.gorefer.in/poster         Poster
z.gorefer.in/status         WhatsApp Status
z.gorefer.in/share          Social Sharing
```

**PART 9 — Referral State Machine (every state change emits an event, stored forever):**
```
Created -> Shared -> Opened -> Landing Viewed -> Signup Started -> Signup Completed -> Confirmed -> Rewarded
```

**PART 10 — Automation-First philosophy.** For every feature ask "can software do it?" Auto-generate: QR, poster, WhatsApp Status, Facebook post, LinkedIn post, Instagram caption, WhatsApp message, and even reminder messages.

**PART 11 — The Hidden Product.** GoRefer is not really a referral platform — it is a Content Automation Engine around referrals. One button generates an entire "Referral Kit": personalized referral poster, WhatsApp status image, Facebook post, LinkedIn post, Instagram caption, WhatsApp forward message, email template, QR code, and referral landing page. Considered one of GoRefer's biggest differentiators.

**PART 12 — Sprint 1 Redefinition (MVP -> MLP).** Sprint 1 should deliver a Minimum LOVABLE Product, not just an MVP. By end of Sprint 1 an existing Zerodha customer can: (1) receive a WATI campaign, (2) open a personalized GoRefer link, (3) view a branded landing page, (4) copy or share their referral link, (5) download a personalized referral kit (poster, QR, ready-made messages), (6) share on WhatsApp or social media, (7) have every click tracked, (8) redirect prospects to Zerodha with correct partner + referral attribution. Rationale: referral products live or die by UX — if sharing isn't delightful and effortless, users won't do it.

**Next deliverable ChatGPT intends to produce:** "GoRefer Data Model & Database Design v1", followed by: complete ERD; every table with fields/indexes/relationships; event model; API contracts; folder structure; microservice/module boundaries; technology-stack justification; Claude Code implementation roadmap. Going forward ChatGPT will keep making architectural decisions unless a decision affects business strategy, compliance obligations, or branding.

### Addition 8 — GoRefer Sprint 0, Document 2: Domain Model & System Architecture v1
Answers: "If we deleted all the code tomorrow, what are the core business objects that define GoRefer?"

**1. Core Business Entities (8):**
- Entity 1 — Referral Program: a company/product whose referrals GoRefer manages (Sprint 1: Zerodha; future: Groww, Upstox, Angel One, Mutual Funds, Insurance, Loans). Attributes: Program Name, Display Name, Status, Logo, Theme, Brand Color, Landing Page Template, Redirect Strategy, Reward Description, Terms & Conditions, Active/Inactive. NO Zerodha-specific fields.
- Entity 2 — Partner: the business using GoRefer (Sprint 1: Passive Income Financial Solutions Pvt Ltd, partner code ZMPHZC; future: many). Attributes: Name, Code, Logo, Contact Numbers, WhatsApp, Email, Website, Address, Social Links.
- Entity 3 — Customer: existing Zerodha client. Attributes: Client ID, Name, Mobile, Email, Referral Eligibility, Referral Count, Reward Points, Status. IMPORTANT: Customer is NOT a GoRefer user — he is an external customer.
- Entity 4 — Prospect: someone who may open an account. Fields: Name, Mobile, Email, Source, Campaign, Current Stage, Assigned Executive.
- Entity 5 — Referral (the heart): connects Customer -> Prospect -> Program -> Partner -> Campaign -> Landing Page -> Reward. Fields: Referral Token, Status, Created Date, Opened Date, Shared Count, Click Count, Conversion Date. Everything revolves around Referral.
- Entity 6 — Campaign (independent): WhatsApp/Facebook/Instagram/Email/Status. Attributes: Campaign Name, Channel, Template, Start Date, End Date, Target Audience.
- Entity 7 — Landing Experience (NOT "Landing Page" — may later be a WhatsApp Flow, Mini App, PWA, or Native App). Fields: Theme, CTA, Content Blocks, FAQ, Video, Buttons.
- Entity 8 — Marketing Asset (a "hidden" entity): Poster, QR, PDF, Status Image, Instagram Story, Facebook Post, Email, WhatsApp Template — generated dynamically instead of hardcoded.

**2. Entity Relationships:**
```
Program -> Partner -> Customer -> Referral -> Prospect -> Conversion -> Reward
```
Campaigns, Marketing Assets, Analytics, and CRM all connect to / eventually touch Referral.

**3. Database Philosophy:** not 40 huge tables — small, focused, independent tables. Example: the Customer table should never store Analytics; analytics belongs elsewhere.

**4. Event-Driven Design:** store business events, not counters. Instead of Referral.clicks++ store ReferralLinkOpened; instead of a poster download count store PosterDownloaded; instead of WhatsAppShared=true store WhatsAppMessageShared. Every action -> a business event. Why: later you can answer questions you never imagined (which landing page/campaign/executive/poster performs best) without changing the database.

**5. Module Communication:** modules do NOT call each other directly. Referral Created -> Event Bus -> Analytics / CRM / Notifications / Reports. Loose coupling.

**6. The Referral Token:** not AB1234 (bad). Instead e.g. R9KF2L — random, short, secure, non-sequential, case-sensitive. When clicked: R9KF2L -> Database -> Customer -> Partner -> Program -> Campaign -> Redirect. (NOTE: still conflicts with Abhay's Cowork raw-client_id/no-token preference — identifier scheme remains a live open decision; see GoRefer-Build-Spec-Cowork-Decisions.md.)

**7. The Redirect Engine (its own service):**
```
Incoming Request -> Validate Token -> Check Status -> Check Expiry -> Identify Program -> Log Analytics -> Generate Event -> Build Destination URL -> Redirect
```
The Redirect Engine knows nothing about Zerodha; the Program Plugin supplies the destination (e.g. https://signup...). Tomorrow Groww = a different plugin.

**8. Marketing Asset Engine:** input (Referral Token, Customer, Program, Theme, Campaign) -> output (Poster, QR, Status, Facebook, Instagram, LinkedIn, Email, PDF), all generated automatically.

**9. Campaign Engine:** should never know "WhatsApp." Instead: Channel, Message, Variables, CTA, Media — with WhatsApp/Facebook/Email as connectors.

**10. CRM Philosophy:** every lead has a complete timeline:
```
Campaign Sent -> Opened -> Clicked -> Landing -> WhatsApp -> Executive Assigned -> Call -> Follow-up -> Account Opened
```
Everything visible.

**11. Analytics Philosophy:** not reports — questions. Analytics should answer business questions: what % of customers share their referral, what % use WhatsApp vs Status, which poster converts, which campaign gives best ROI, which executive converts fastest, which city converts best, which landing page performs best.

**12. ADR-001 — Every referral has its own Landing Experience** (not merely a redirect). Example: friend opening z.gorefer.in/r/R9KF2L sees "Hi! Your friend Rahul invited you. Open your FREE Zerodha Account. Benefits ★★★★★ Need help? Open Now." Benefits: builds trust, explains value proposition, gives analytics, lets you offer assistance, allows A/B testing, feels professional. Redirect to Zerodha only after the user chooses to continue. This is the shift from "URL shortener" to "conversion platform."

**Next deliverable ChatGPT intends:** "GoRefer Database Design (Production Grade)" — every table, column, data type, primary key, foreign key, index, constraint, soft-delete strategy, audit fields, event tables, analytics tables, CRM tables, marketing tables, and multi-program future-proofing, so Claude Code can build the backend DB with almost no architectural ambiguity (and it becomes the source of truth for API design).

### Addition 9 — Autonomous Operating Model & Governance Rules
**Autonomous Mode.** ChatGPT continues designing without asking anything unless a decision only the Product Owner (Abhay) can make. When it must pause it uses this exact format: a "⛔ Product Owner Decision Required" block with: Why I'm pausing (one paragraph), Options (Option A with Pros/Cons/Recommendation, Option B with Pros/Cons), Decision Needed, "After you decide I'll continue with: 1,2,3,4", and Estimated work (approx X more documents). Otherwise it will not stop — no "should I continue?", no unnecessary confirmations; behaves like a Chief Product Officer.

**New Rule 1 — Project Status** maintained each step: Project, Phase, Progress (percent bar), Current Document, Next, Blocked, Waiting For Product Owner.

**New Rule 2 — Decision Register (ADRs):** ADR-001 Opaque Referral Tokens — Approved; ADR-002 Landing Experience before Redirect — Approved; ADR-003 Mobile First — Approved. (So Abhay never has to remember prior decisions.) [Capture note: ADR-001 "opaque tokens Approved" is ChatGPT's stance and conflicts with Abhay's Cowork raw-client_id preference — identifier scheme still a live open decision.]

**New Rule 3 — Technical Debt Register:** for anything intentionally postponed, record Why, Risk, When to revisit. Example TD-001 Advanced Analytics Dashboard — reason: not needed in Sprint 1 — review: Sprint 5.

**New Rule 4 (most important) — Product Backlog like Jira:** every feature decomposed Epic -> Feature -> Story -> Task -> Subtask -> Acceptance Criteria -> Definition of Done. Claude Code never receives vague prompts, only engineering work items.

**New Rule 5 — Continuous optimization:** if a better architecture is found mid-way, never silently change it; instead produce an Architecture Review (Current Design, Problem, Proposed Improvement, Migration Impact, Recommendation).

**Next autonomous sequence (10 docs):** production DB design; event model; API specification; service architecture; frontend architecture; WATI + Meta integration; Referral Engine spec; Landing Experience spec; Marketing Asset Engine; Sprint 1 backlog.

### Addition 10 — Production Database Design v1
Golden Rule: every table has only ONE responsibility (Customer table must not also hold Referral/Campaign/Analytics/Rewards). Database split into 12 bounded contexts:
```
1  Identity            users, roles, permissions, user_sessions, audit_logs   (Sprint 1: only Admins & Executives; customers do NOT log in)
2  Referral Programs   programs, program_settings, program_redirect_rules      (Sprint 1: Zerodha = one row)
3  Partners            partners, partner_contacts, partner_branding, partner_domains  (PIFS, code ZMPHZC)
4  Customers           customers (minimal only)
5  Referral Tokens     referral_tokens (the heart)
6  Referrals           referrals (distinct from tokens)
7  Prospects           prospects
8  Campaigns           campaigns
9  Marketing Assets    marketing_assets (one table for all asset types)
10 Landing Experiences landing_experiences
11 CRM                 leads, lead_notes, lead_assignments, lead_status_history, executive_calls
12 Analytics           events, sessions, devices, campaign_stats, daily_metrics
```
- customers fields: id, program_id, partner_id, client_id, mobile, email, first_name, last_name, eligibility_status, last_sync, status, created_at, updated_at. NO PAN / Aadhaar / KYC / brokerage — GoRefer must not become another customer master (minimizes security & compliance risk).
- referral_tokens fields: id, token, customer_id, campaign_id, landing_page_id, program_id, partner_id, status, created_at, expires_at, revoked_at. Indexes: token (unique), customer_id, campaign_id, status.
- referrals fields: id, token_id, prospect_id, status, conversion_status, reward_status, created_at, completed_at. (One token may generate multiple referrals in future.)
- prospects fields: id, mobile, email, name, city, state, lead_source, created_at.
- campaigns fields: id, program_id, channel, name, template, status, starts_at, ends_at. Channels include WhatsApp, Status, Facebook, Instagram, LinkedIn, Email, QR, Poster, Direct Link (QR treated as a marketing channel to get analytics).
- marketing_assets fields: id, asset_type, theme, language, version, template, generated_by, created_at. Asset types: Poster, QR, Status, Story, Email, Banner, Flyer, future Video — no schema changes.
- landing_experiences fields: id, program_id, theme, headline, subheadline, cta, faq, status. Future: video, testimonials, calculator without redesign.
- Events table (likely largest) fields: id, event_type, user_type, user_id, referral_id, campaign_id, session_id, device_id, country, state, city, ip, user_agent, timestamp, metadata (JSON). Metadata stores anything without schema changes.
- Soft delete: deleted_at, deleted_by, delete_reason on every important table.
- Audit: created_by, updated_by, version (version enables optimistic locking).
- Search: dedicated search indexes for Customers, Prospects, Leads, Campaigns.
- Naming: tables plural (customers, campaigns, referrals); columns snake_case (created_at, partner_id); PK = id; FKs = customer_id, campaign_id, program_id.
- **Database Philosophy:** GoRefer stores WORKFLOW data, not business OWNERSHIP data. It tracks referral tokens, campaigns, landing pages, marketing assets, analytics, lead assignments. It does NOT become the system of record for customer KYC, trading activity, reward calculations, brokerage, or investment holdings — those remain with Zerodha (or future partners).
- **ADR-004 (Approved):** GoRefer uses an Event-Driven Analytics Model instead of counter-based analytics. Reasons: unlimited reporting flexibility, easier debugging, better audit trail, supports future AI insights.
- Technical Debt Register: none yet.
- Autonomous improvement identified: a "Referral Profile" per customer (optional public display name, profile photo, personalized welcome message, preferred contact method, personalized landing theme, social links, language preference) — e.g. friend sees "Hi! I'm Abhay. I've been using Zerodha and would like to invite you...". NOT Sprint 1 — added to backlog as a Sprint 4 candidate (high conversion potential, not required for launch).
- Next deliverable: Event Architecture & Business Workflow Design.

### Addition 11 — Course Correction: Experience-First (Conversion Blueprint before Architecture)
ChatGPT flags that it OVERCORRECTED into enterprise architecture (DB tables, modules) too early — wrong order for a startup / solo founder. Correct approach: work backwards from "A real Zerodha customer receives a WhatsApp message today and successfully refers a friend today" — NOT from the database. Once the experience is perfect, the database almost designs itself.

Design the platform in LAYERS:
```
Layer 1 (current) Customer Experience: what the customer receives / clicks / sees / shares; what the friend sees; where GoRefer helps; where Zerodha takes over; where we assist manually; what gets automated. (Most important layer.)
Layer 2 Product Design: pages, components, buttons, copy, posters, WhatsApp templates, landing pages, CRM screens
Layer 3 System Design: APIs, database, events, backend
Layer 4 Claude Code: implements exactly what was designed
```
We are really building THREE products at once: Product 1 = Customer Experience ("I want to refer my friend"); Product 2 = Partner Operations ("I want to acquire more customers"); Product 3 = Automation Platform (WATI, Analytics, Posters, CRM, AI, Reports). ChatGPT jumped too quickly to Product 3; Product 1 must be finished first.

Next phase = "The Perfect Referral Journey" designed minute-by-minute (example: 10:00 AM customer receives WhatsApp campaign -> reads first line -> doesn't click -> system waits 3 days -> reminder sent -> clicks -> landing page -> personalized greeting -> chooses "Refer a Friend" -> shares on WhatsApp -> friend clicks -> friend has questions -> clicks "Chat with Advisor" -> executive notified -> executive calls -> account opened -> customer gets congratulations -> reward tracking starts). Challenge every step: can we remove it / automate it / let AI do it / increase conversion / reduce friction? The output is a "Conversion Blueprint." Only after that will Claude Code build. Reframe: you're not building software, you're building a machine that consistently generates referrals; the software is just the implementation.

### Addition 12 — Agile Micro-Sprint Workflow (Sprint 1 broken into 1.1–1.10)
Course correction #2: Agile means design JUST ENOUGH, then build a working increment — not 100-page docs before coding. New process loop, each cycle ending in a deployable working product:
```
1. Design (1–3 hours of work)  ->  2. Claude implements  ->  3. You test  ->  4. ChatGPT reviews  ->  5. Next sprint
```
Sprint 1 Goal (revised): "An existing Zerodha customer can receive a WhatsApp message, get their personalized referral link, share it, and their friend is redirected to Zerodha while GoRefer tracks the journey." If that works, Sprint 1 is a success.
Sprint 1 divided into 10 micro-sprints:
```
1.1 (Day 1)  Create repository, CI/CD, project structure, environment config      -> Deliverable: empty app running locally
1.2          Referral token generation, resolution, secure redirect               -> Deliverable: z.gorefer.in/r/{token} works
1.3          Landing page: branding, CTA, redirect button                         -> Deliverable: first user-facing page
1.4          Analytics: click tracking, device tracking, campaign tracking
1.5          WATI webhook: generate personalized referral link, send response
1.6          Poster generation, QR generation, WhatsApp-ready image
1.7          Share Kit: WhatsApp, Facebook, LinkedIn, copy link
1.8          CRM: lead capture, executive assignment
1.9          Admin dashboard
1.10         Polish, testing, deployment
```
End of Sprint 1 = a usable product, not a prototype.
Living backlog: for every micro-sprint ChatGPT produces Business objective, User story, UI wireframe (textual), API contract, Acceptance criteria, Test cases, and a Claude implementation prompt. Claude implements exactly ONE micro-sprint at a time.
Recommended ongoing workflow:
```
You -> ChatGPT (Product Owner + Architect) creates ONE implementation-ready task -> Claude Code implements ONLY that task -> You test -> ChatGPT reviews -> repeat
```
No giant specifications, no analysis paralysis, no waiting — continuous delivery.

### Addition 13 — Project OS: CLAUDE.md + /docs + /tasks, and the "GoRefer Development OS"
Goal: don't make Abhay a messenger between himself and Claude Code (doesn't scale). Build a "Project OS" where Claude Code always knows what to do next.
**Option 1 (ChatGPT's recommendation, 5 stars): CLAUDE.md + /docs + /tasks git repo:**
```
gorefer/
├── CLAUDE.md                 <-- Claude always reads this first
├── README.md
├── docs/
│   ├── Vision.md
│   ├── PRD.md
│   ├── Architecture.md
│   ├── API.md
│   ├── Database.md
│   ├── Decisions.md
│   └── CodingStandards.md
├── tasks/
│   ├── backlog.md
│   ├── sprint-1/  (001-referral-engine.md, 002-landing-page.md, 003-wati.md, ...)
│   └── completed/
├── reviews/
│   ├── code-review.md
│   └── architecture-review.md
└── implementation-status.md
```
Workflow: ChatGPT creates task -> Claude Code reads task -> implements -> updates implementation-status.md -> Abhay commits. Almost no copy-pasting.
**Option 2 (good for starting): One Master Prompt** — pasted once: "You are the lead engineer for GoRefer. Read CLAUDE.md, implement Task 001, follow coding standards, update implementation-status.md, don't proceed to Task 002 until Task 001 passes." Claude then continues on the repo.
**Option 3 (professional): GitHub Issues** — every task is a GitHub Issue (acceptance criteria, API, tests); Claude works from Issues.
**Recommended stance:** Claude Code is your software ENGINEER, not architect. Claude never decides what to build; every task comes from Abhay + ChatGPT. Task format example — Task ID: S1-003; Title: Implement Referral Redirect Service; Business Goal: track referral clicks and redirect users to Zerodha; Requirements; Acceptance Criteria; API; Tests. Claude implements exactly that.
**GoRefer Development OS** (for a multi-month project): Product Backlog, Sprint Backlog, Architecture Decisions (ADR), Documentation, Claude Instructions, QA Checklist, Release Notes, Roadmap. Roles: Abhay = business decisions; ChatGPT = product/architecture/backlog/QA; Claude = implementation.
**First foundational artifact: CLAUDE.md** — a master operating manual (not a normal README) defining: project vision; non-negotiable engineering principles; coding standards; folder structure; how to approach tasks; what Claude is allowed to decide; what must be escalated; Definition of Done; testing expectations; documentation requirements. Create CLAUDE.md before assigning any development task.

### Addition 14 — CPO Reframe: "Zerodha Referral Success" over "GoRefer", 80% Cut, 5 Engines, Mission-Based Execution, Locked Roadmap, Mission 001
Abhay is taking the Chief Product Officer role and will decide: what to build next, what not to build yet, what can wait, what Claude implements, when to pivot. The founder only steps in for business-only decisions.

**Reframe (important):** the objective is NOT "Build GoRefer" — it is "Build a machine that increases Zerodha referrals." GoRefer is merely the software that powers it. Think "Zerodha Referral Success," not "GoRefer."

**Sprint 1 redefined (nothing else matters):**
```
Receive WhatsApp Campaign -> Click -> Get Personalized Referral Kit -> Share -> Friend Clicks -> Friend Opens Account -> Customer Gets Referral
```
If this works, Sprint 1 is complete.

**Cutting ~80% of the earlier plan — all POSTPONED:** Admin Dashboard, CRM, Advanced Analytics, AI, Gamification, Multi-Program, Partner Management, Complex Database, Huge APIs.

**Build ONLY these 5 engines:**
- Engine 1 — Referral Link Generator: input Client ID -> output personalized referral link.
- Engine 2 — Referral Landing Page: customer clicks -> beautiful page (benefits, help, CTA) -> redirect.
- Engine 3 — Referral Kit Generator: one click -> Poster, WhatsApp Status, ready message, referral link, QR.
- Engine 4 — Analytics: ONLY Link Created, Link Opened, Redirected. Nothing else.
- Engine 5 — WATI Integration: customer receives dynamic message -> clicks -> gets Referral Kit.

**Mission-based execution.** Claude does not "build a project" — it completes Missions: Mission 1 Repository, Mission 2 Landing Page, Mission 3 Referral Engine, Mission 4 Poster Engine, Mission 5 WATI. Each mission -> merged -> deploy -> next.
Per mission ChatGPT produces: Business Goal, User Story, Screen Design, API, Acceptance Criteria, Definition of Done, Claude Prompt — plus Folder to modify, Files to create, Tests, Documentation, Commit message, Rollback plan (so Claude builds production software, not throwaway code).

**Locked roadmap:**
```
Phase 1 (current) Acquire Zerodha referrals    -> Deliverable: a customer can successfully refer a friend
Phase 2           Increase referral conversion  -> optimize landing page, posters, messages, WhatsApp Status, follow-ups
Phase 3           Reduce manual work            -> automation: WATI, CRM, AI, notifications
Phase 4           Become partner-independent    -> add Groww, Upstox, Insurance, Mutual Funds
Phase 5           Referral OS                   -> businesses sign up, GoRefer becomes SaaS
```

**Role change:** ChatGPT acts as Product & Engineering Manager (not documentation writer). After each Claude mission it will: (1) review the implementation, (2) identify architectural issues, (3) prioritize the next highest-impact mission, (4) write the next implementation task. ChatGPT owns the roadmap so Abhay never has to ask "what should we build next?"

**Mission 001 (LOCKED):** "Build the smallest possible GoRefer platform that delivers a personalized referral experience for Zerodha customers." Includes: a minimal web application; personalized referral links; referral landing page; redirect to Zerodha with the correct referral parameters; WATI-ready integration points; basic analytics (clicks and redirects); production-ready deployment. After Mission 001 is complete and tested with real users, immediately move to Mission 002: Referral Kit Generator (personalized posters, WhatsApp Status images, share messages, QR codes) — the feature most likely to increase referrals. Every subsequent mission is chosen by its impact on successful Zerodha referrals, not architectural completeness.

### Addition 15 — Domain & URL Architecture Decision (ADR-005): Single-Domain Token Routing (revises the earlier z.gorefer.in subdomain scheme)
GoRefer is built for Zerodha first but will extend to more referral programs (Groww, Upstox, insurance, mutual funds, properties, credit cards, home loans, LIC, HDFC Ergo, ICICI Lombard, NoBroker, MagicBricks, etc. — see Phase 4). The domain architecture must support that from day one.

**Decision on the domain question (subdomain vs path):** do NOT use `zerodha.gorefer.in` (subdomain) as the primary architecture. Use a single-domain, token-routed structure. (This REVISES the `z.gorefer.in` subdomain scheme recorded in earlier Additions 7 and 8.)

**Canonical URL structure:**
```
gorefer.in/{partner}          Public marketing/info page   e.g. gorefer.in/zerodha, /groww, /upstox, /insurance, /mutual-funds, /properties
gorefer.in/{partner}/r/{token}  Program-scoped referral      e.g. gorefer.in/zerodha/r/8DKPXM
gorefer.in/r/{token}           Cleaner referral (preferred) — the token itself knows the program
```

**Preferred: hide the program from referral links entirely** — use `gorefer.in/r/8DKPXM`. On click, GoRefer looks up: Token -> Program (e.g. Zerodha) -> Partner (ZMPHZC) -> Customer (AB1234) -> Campaign (WhatsApp). The user never sees any of it. The SAME engine then serves referral links for Zerodha, Groww, Insurance, Properties, Home Loans with NO routing changes.

**Why not subdomains:** with many partners you'd accumulate zerodha./groww./upstox./lic./hdfc./properties.gorefer.in — at ~100 partners, managing subdomains (DNS, SSL) becomes unnecessary complexity.

**Architecture shape:**
```
GoRefer
├── Programs (Partners): Zerodha, Groww, Upstox, Insurance, Properties, ...
└── Shared Engines: Referral Engine, Poster Engine, Campaign Engine, Analytics, CRM
The platform stays the same; only the program/partner changes.
```

**Where `/{partner}` still exists:** `gorefer.in/zerodha` remains, but ONLY as the marketing homepage (benefits, FAQs, account opening, referral info, contact details). `gorefer.in/r/XXXX` is the actual referral journey.

**Terminology change:** rename "Programs" -> "Partners" (external organizations whose referral journeys GoRefer manages: Zerodha, Groww, LIC, ICICI Prudential, HDFC Ergo, NoBroker, MagicBricks). Internally distinguish: Partner (the external company/service), Campaign (a specific marketing initiative), Referral Journey (the user flow for a referral).

**ADR-005 (Proposed — awaiting Abhay's approval):** Use a single-domain architecture with token-based routing. Canonical referral URLs: `gorefer.in/r/{token}` (referral journey) and `gorefer.in/{partner}` (public/marketing page). Reasoning: simpler infrastructure, easier SSL/DNS management, cleaner analytics, easier future expansion, no dependency on subdomains, better UX with shorter links. Status: PROPOSED, awaiting approval. (Note: this is a foundational decision to lock before Claude writes code, since migrating URL structures later is painful.)

### Addition 16 — ADR-005 APPROVED; Customer Reframe (Partner is the customer); Customer Referral Dashboard; "Wizard not Software"; QR De-emphasis; "Create My Referral Kit"; New Vision = Referral Kit Generator
**ADR-005 — APPROVED & LOCKED (2026-07-04)** (supersedes the "Proposed" status in Addition 15). Canonical URLs: marketing page `gorefer.in/zerodha`; referral journey `gorefer.in/r/{token}`; future `gorefer.in/groww`, `gorefer.in/insurance`, `gorefer.in/properties`. The referral token determines the destination.

**Customer reframe (important).** GoRefer's real customer is NOT the existing Zerodha customer — it is the Referral Partner (Passive Income Financial Solutions / Abhay and his executives). The existing Zerodha customer is "your user's user." This means GoRefer has TWO products:
- Product A (Sprint 1) — a Referral Acquisition Platform used by PIFS + executives; purpose: acquire more Zerodha accounts.
- Product B (future SaaS) — a generic Referral Platform used by anyone.
So Sprint 1 should optimize Abhay's business, NOT build a generic SaaS. Subtle but important shift.

**Key insight — the plain referral journey is only ~50% of the opportunity.** Many customers think "I'll share it later" and then never do; that's where referrals die. GoRefer must solve this.

**Customer Referral Dashboard (NOT an admin dashboard).** When the customer opens GoRefer, the first screen is a customer dashboard with exactly one purpose: help the customer refer someone in under 30 seconds. Example:
```
👋 Hi Abhay!
You can earn:
  ✅ 10% brokerage share
  ✅ 300 reward points
──────────────
Refer using:
  [ WhatsApp ]  [ WhatsApp Status ]  [ Facebook ]  [ Instagram ]  [ Copy Link ]
──────────────
OR  Know someone interested? Share their contact:
  [ Name ]  [ Mobile ]  [ Submit ]      (We'll assist them personally.)
──────────────
Referral Progress:  Friends Referred 2 / 3   — Refer 1 more to unlock rewards.
```
No menus, no settings, no dashboard clutter — just one objective.

**Principle — GoRefer should feel like a WIZARD, not software.** Every screen answers ONE question:
```
Screen 1  How do you want to refer?
Screen 2  Great! Here's your personalized content.
Screen 3  Need help referring someone?
Screen 4  Congratulations!
```

**QR de-emphasis.** People rarely scan a QR on the same phone, so stop treating QR as primary. Device-detect and prioritize the most useful action: Desktop shows Referral Link + QR (both); Mobile shows Referral Link + Share button, no QR emphasis. Removes unnecessary friction.

**WATI CTA change.** Instead of "Click here to get your referral link," use "🎁 Create My Referral Kit" — feels valuable, not "just a link." On click, GoRefer automatically generates: personalized referral link, WhatsApp message, WhatsApp Status image, poster, Facebook text, Instagram caption — everything, in one click. A major differentiator.

**NEW product vision.** GoRefer is not a referral website — it is a "Referral Kit Generator." The referral link is just one component of the kit. This shift makes users far more likely to actually share.

**Next (no input required): Mission 001 engineering package** — instead of another architecture doc, ChatGPT will produce the first implementation-ready package for Claude Code: project structure, technology stack, folder organization, development standards, Mission 001 implementation tasks, acceptance criteria, testing checklist, deployment approach. After Mission 001, Abhay will have a working GoRefer app he can open in a browser, connect to WATI, and test with real Zerodha customers. Every subsequent mission improves referral conversion, not just technical features.

### Addition 17 — Single Source of Truth in Git (Project Brain / Project Memory / Project Builder)
Where does project knowledge live today? Nowhere permanent — it exists only in the ChatGPT chat context, which is lost if the conversation gets too long or a new chat starts. That is not acceptable for GoRefer. Move it to a single source of truth in Git.

**Proposed repository structure:**
```
GoRefer/
├── docs/
│   ├── 000_Project_Vision.md
│   ├── 001_Constitution.md
│   ├── 002_ADRs.md
│   ├── 003_Roadmap.md
│   ├── 004_PRD.md
│   └── ...
├── tasks/
│   ├── backlog.md
│   ├── sprint-01/
│   └── ...
├── CLAUDE.md
└── README.md
```
Workflow: ChatGPT updates the documentation -> Claude Code reads it before implementing anything -> Abhay always has the latest project state in Git.

**Living documents to maintain:**
- Architecture Decision Register:
  - ADR-001 — Opaque referral tokens ✅
  - ADR-002 — Landing experience before redirect ✅
  - ADR-003 — Mobile-first design ✅
  - ADR-004 — Event-driven analytics ✅
  - ADR-005 — gorefer.in/r/{token} URL strategy ✅
  (Capture note: ADR-001 "opaque tokens" is marked approved here by ChatGPT, but still conflicts with Abhay's Cowork raw-client_id / no-token preference — unresolved.)
- Product Backlog: every feature discussed becomes a tracked backlog item with a status.
- Roadmap: every sprint, milestone, and future idea (Groww, insurance, properties, etc.) recorded so nothing is lost.

**Recommendation:** project knowledge should NOT live in ChatGPT — it should live in the Git repository, because Git is permanent, version-controlled, readable by Claude Code, shareable with future developers, and independent of any AI model. So six months later "Why did we choose gorefer.in/r/{token} instead of subdomains?" is already answered in ADR-005.

**Roles:** ChatGPT = Project Brain (creates and evolves the documentation); Git repository = Project Memory (stores all decisions and specs); Claude Code = Project Builder (implements from that documentation). The lasting value of GoRefer is not just the code but the accumulated knowledge and decisions explaining why the code is the way it is — that knowledge should live alongside the code.

### Addition 18 — Data Storage Architecture (ADR-006): PostgreSQL + Zoho CRM + WATI, GoRefer as Orchestrator

Question: where does GoRefer store referral data — a Postgres DB, WATI only, or WATI + Zoho CRM? (Context: WATI is already connected to Zoho CRM.) Answer: use all three, each for what it is best at. Do NOT use WATI or Zoho CRM as the primary database for referral relationships.

Reason: for a journey like Abhay shares link -> Rahul clicks -> doesn't open -> returns after 15 days -> clicks again -> chats on WhatsApp -> executive calls -> account opens -> reward earned: WATI only knows messages sent/received; Zoho only knows "Rahul is a lead"; NEITHER understands the referral RELATIONSHIP between Abhay and Rahul. That relationship is GoRefer's core value.

**Responsibilities:**

- GoRefer (PostgreSQL) = the brain: referral token, referrer (Abhay), referred friend (Rahul), which campaign generated it, which landing page, click history, referral status, share history, analytics, reward eligibility. Data no other system owns.
- Zoho CRM = the sales pipeline: Lead Created -> Assigned to Executive -> Called -> Documents Pending -> KYC Completed -> Account Opened. GoRefer creates the lead in Zoho; Zoho manages the sales process.
- WATI = only messaging: campaigns, templates, WhatsApp conversations, delivery status, read receipts, incoming messages. Nothing else.

**Architecture:**

```
WhatsApp -> WATI API
             |
         GoRefer (PostgreSQL): Referral Engine, Landing Pages, Referral Kit, Analytics, Redirect Engine
             |
         Zoho CRM: Lead Management, Follow-ups, Executives, Sales Pipeline
GoRefer sits in the middle; everything flows through it.
```

**Example flow:** Customer receives WATI campaign -> clicks -> GoRefer creates referral token -> GoRefer shows Referral Kit -> friend clicks -> GoRefer records click -> GoRefer creates Lead in Zoho CRM -> executive works in Zoho -> account opens -> Zoho notifies GoRefer -> GoRefer updates referral -> GoRefer notifies customer.

Why not only Zoho: leaderboards, referral-kit downloads, QR/Status/Facebook performance, A/B testing, multiple programs are hard to force into a CRM. Why not only PostgreSQL: you'd rebuild lead assignment, follow-up reminders, call logs, pipelines, tasks, notes — Zoho already does these well.

GoRefer is the orchestrator: it does not replace WATI or Zoho, it coordinates them, via its OWN API layer — WATI never talks directly to Zoho and vice versa; everything goes through GoRefer (centralized business logic, easier debugging, better analytics, easier to add Groww/insurance/properties later without changing WATI/Zoho integrations).

**ADR-006 (locked recommendation):** PostgreSQL = primary store for all GoRefer-specific entities (referrals, tokens, journeys, analytics, configuration); Zoho CRM = lead management, executive workflow, sales pipeline; WATI = WhatsApp messaging, templates, campaigns, conversations; GoRefer = the orchestration layer integrating all three.

### Addition 19 — Per-Link Tracking & Referral Intelligence (ADR-007): Every Referral Link is a First-Class Entity

Abhay's requirement: some customers put in extra effort to share, so their referral links get clicked more. He must be able to track EVERY generated/circulated link and every click — even a single click — by which customer, plus whether an account opened. Track each link individually.

ChatGPT reframes: track the complete LIFE of every referral link. Every link gets its own timeline. Example (Rahul, gorefer.in/r/A7KD9P):

```
Owner: Rahul Sharma | Created: 15 Jan 2026 09:15 | Status: Active
Total Clicks 23 | Unique Visitors 18 | WhatsApp Shares 11 | Facebook 4 | Instagram 2 | QR Scans 6
Accounts Started 5 | Opened 3 | Pending 2 | Rejected 0
```

**Click Timeline (every event, not just totals):**

```
09:15 Link Created
09:16 Shared on WhatsApp
09:21 Clicked  (Android, Lucknow, Campaign: WhatsApp)
10:08 Clicked  (Desktop, Delhi)
14:21 Account Started
14:48 Account Opened
```

**Customer Leaderboard:**

```
Customer | Link Clicks | Accounts Opened | Conversion
Rahul    | 92          | 18              | 19.5%
Abhay    | 48          | 16              | 33.3%
Amit     | 31          | 4               | 12.9%
```

Instantly shows who is actively referring, who needs encouragement, who deserves recognition.

**Measure INTENT, not just accounts:** Customer A with 100 clicks / 0 accounts is NOT a bad customer — it means people are interested but something later (landing page, KYC, executive follow-up) is failing. Customer B with 5 clicks / 4 accounts = excellent conversion, different strategy. This insight is very valuable.

**Every referral has a Funnel:**

```
Referral Link Created -> Shared -> Opened -> Landing Viewed -> Clicked Open Account -> Reached Zerodha -> KYC Started -> KYC Completed -> Account Opened -> Reward Eligible -> Reward Confirmed
```

Track how many move forward at each stage. This becomes a business Management Dashboard (not technical) answering: which customers generate the most clicks; which links are inactive; which get traffic but no conversions; which campaigns generate the highest-quality referrals; which customers to personally thank or reward.

**Referral Score per customer** (e.g. ★★★★★ Active Referrer, 98 clicks / 21 shares / 12 accounts) identifies brand ambassadors; enables campaigns like "Top 20 referrers this month get a special reward."

Reframe: GoRefer is not just a referral tool — it is a "Referral Intelligence Platform." The intelligence is in understanding which customers influence others and where the journey succeeds or breaks down.

**ADR-007 (approved by ChatGPT, awaiting Abhay's implicit agreement):** every referral link is a first-class entity with its own complete lifecycle and analytics — unique identifier, owner (referring customer), creation timestamp, share events, click events, visitor details (where available and privacy-compliant), landing page visits, redirects, lead creation status, account opening status, reward status, and a complete chronological timeline. Treated as a CORE feature, not an enhancement. Even in Sprint 1, capture the events needed so historical data is never lost. Principle: "collect everything now, visualize it later."

### Addition 20 — Tracking Account-Opening Status: Observed vs Imported Events (Zoho integration, not Zerodha assumption)

Abhay's challenge: GoRefer can track which links were clicked, from where, and when — but account-opening status comes from Zerodha. How is that tracked? ChatGPT: GoRefer cannot magically know if a Zerodha account was opened; never design around information we don't have. Separate what we KNOW from what we INFER.

**What GoRefer can know with certainty:** referral link created; shared; clicked; time of click; device/browser; referrer (customer); campaign source (WhatsApp, Status, Facebook, etc.); landing page viewed; clicked "Open Zerodha Account." After that the user leaves GoRefer for Zerodha.

**What GoRefer canNOT know by itself:** KYC started; KYC completed; account opened; reward credited — unless Zerodha or another system tells us.

**Three methods to get account status:**

```
Option 1 (good for Sprint 1, 5 stars): Manual update — when an executive sees in the
  Zerodha Partner Console that the account is opened, they set Referral -> Status ->
  Account Opened; or GoRefer syncs from Zoho when the lead is marked "Account Opened."
  Pros: simple, reliable, no Zerodha integration needed, quick to build.

Option 2 (preferred medium-term, 5 stars): Zoho CRM integration — friend clicks referral
  -> GoRefer creates Lead in Zoho -> executive follows up -> executive updates Zoho
  "Account Opened" -> Zoho notifies GoRefer -> GoRefer updates referral. GoRefer never
  asks Zerodha directly; it trusts the CRM where the team works daily, avoiding duplicate
  data entry.

Option 3 (future, if available): Zerodha API/Webhook — Account Opened -> Zerodha ->
  Webhook/API -> GoRefer -> Referral Updated. Ideal, but do NOT assume it exists until
  verified.
```

**Revised philosophy — distinguish two event kinds:**

```
Observed Events = things GoRefer actually witnessed (link clicked, landing page viewed,
  redirect to Zerodha). Facts.

Imported Events = things another trusted system tells GoRefer (lead created from Zoho;
  account opened from Zoho or Zerodha; reward credited). Also facts, but with a
  recorded SOURCE.
```

**Every status includes its source (transparent/auditable):**

```
Status              | Source
Link Clicked        | GoRefer
Lead Created        | Zoho CRM
Executive Assigned  | Zoho CRM
Account Opened      | Zoho CRM (or Zerodha, if available)
Reward Credited     | Manual / Future Zerodha Sync
```

**Decision for Sprint 1:** do NOT block the project waiting for a Zerodha integration. Build referral tracking around the events GoRefer controls, and integrate with Zoho CRM for account-status updates (the team already uses Zoho). Keeps Sprint 1 practical, minimizes duplicate work, leaves the door open for a future direct Zerodha integration.

### Addition 21 — Lazy Journey Creation (ADR-008): No Zerodha integration ever; Zoho is the operational system; track only after first click

Three facts Abhay locked:

1. There will NEVER be a Zerodha integration — remove all Zerodha APIs/webhooks from the roadmap.
2. Zoho CRM is the operational system: a new referral lead is created in Zoho; the executive works in Zoho; when an account is opened a Contact is created in Zoho (or the lead is converted); GoRefer READS that status from Zoho.
3. WATI is only for communication.

Therefore GoRefer is NOT a CRM and NOT a WhatsApp platform — GoRefer is purely a Referral Intelligence Platform.

**Clean architecture:**

```
WATI (send WhatsApp campaigns)
   -> Customer clicks link
   -> GoRefer (Referral Intelligence): (a) track clicks & analytics  (b) create Lead in Zoho CRM
                                         -> Executive works in Zoho
                                         -> Account Opened (Zoho update)
                                         -> GoRefer syncs from Zoho
```

**Key operational insight (Abhay): "You cannot keep tracking without the link even clicked."** Do NOT create a tracking record for every customer. Example: 50,000 customers but only 300 referral links clicked -> need 300 journeys, not 50,000 records. Customer exists + referral link exists + nothing happens = ZERO tracking. First click -> journey starts -> then record everything (Click 1, Click 2, Click 3, Landing, Redirect, Lead, Contact, ...).

**Reframe: think "Referral Journey," not "Referral Link."** Example (Abhay, gorefer.in/r/A7KD9P):

```
12 Jan  Link Created
18 Jan  First Click
19 Jan  Second Click
22 Jan  Redirect
22 Jan  Lead Created
26 Jan  Contact Created
        Completed
```

Every click extends the journey.

**Two dashboards:**

- Dashboard 1 — Operational ("What's happening today?"): New Clicks, New Leads, New Contacts, Pending.
- Dashboard 2 — Referral Explorer (Abhay's requirement): filters by Partner (e.g. Zerodha — because there will be multiple programs), Date, Customer, Mobile, Campaign, Status, Link Clicked, Lead Created, Contact Created; full search. Example: Partner = Zerodha -> "542 Referral Journeys" -> Abhay 12 clicks (Lead Created, Contact Created); Rahul 5 clicks (No Lead); Amit 1 click. Filterable by time/date, and by future partners (properties, etc.).

**Store every click, NOT a click count.** Click 1 (Delhi, Android, 10 AM) vs Click 2 (Lucknow, iPhone, 7 PM) = different people. Storing only "12 clicks" loses the ability to later answer: which cities generate the most referrals, which campaigns perform better on Android, which time of day converts best. Storage is cheap; insights are expensive.

**ADR-008 (LOCKED) — Lazy Journey Creation:** every customer has a referral link; NO tracking record is created until the first click; the first click creates a Referral Journey; every subsequent event is appended to that journey; Zoho CRM enriches the journey with lead/contact information; WATI is used only for communication. Keeps the system lightweight, scalable, aligned with how the business actually operates.

**Refinement:** still generate a referral token for every customer in advance (or on first campaign send) — the link must exist before someone can click it — but create analytics/journey records ONLY after the first click. Best of both: fast ready-to-use personalized links for all customers; minimal DB growth; rich analytics for customers who actually generate referral activity.

### Addition 22 — Referral Token Storage, Two User Types, "Referral Identity", and the Self-Service Verification Decision
Where is the referral token created? NOT only for Abhay's existing customers. A referrer may be an existing customer OR an unknown person with a Zerodha account who self-creates a referral link. Do NOT assume all referrers are in Zoho.
**Two user types:**
- Type 1 — Managed Customer: exists in Zoho CRM; receives WATI campaigns; the team can assist them.
- Type 2 — Self-Service Customer: has a Zerodha account; is NOT in Zoho CRM; visits GoRefer directly; enters their Zerodha Client ID; starts referring immediately.
**Token storage:** the referral token should NEVER live in Zoho or WATI — it is generated and stored ONLY in GoRefer's PostgreSQL database. GoRefer = system of record for referral IDENTITIES; Zoho = system of record for SALES; WATI = system of record for CONVERSATIONS.
**Schema sketch:**
```
Customer:        id, customer_type, zerodha_client_id, mobile (optional), name (optional)
Referral Token:  token, customer_id, program, status, created_at
```
**Scenarios:**
- Scenario 1: Abhay's customer -> campaign sent -> referral token already exists -> works normally.
- Scenario 2: someone never met visits gorefer.in/zerodha, enters Client ID AB1234 -> GoRefer checks if a referral identity already exists; if not, create one + generate token. No Zoho, no WATI involved.
**New concept — "Referral Identity" table** (instead of "Customer"): every person who can refer has one. Fields: Program (e.g. Zerodha), Client ID, Referral token, Source (Zoho / Self-service / Imported), Status. This avoids assuming everyone is a CRM customer.
**Problem to solve — ownership verification.** If an unknown person enters Client ID AB1234, how do we know they actually own it? Without verification, someone could impersonate another client and use their referral link.
**⛔ PRODUCT OWNER DECISION REQUIRED — Verification of self-service users:**
- Option A (ChatGPT's recommendation): require OTP verification on the mobile registered with Zerodha, IF there is a practical way — but since Zerodha won't provide integration, this may not be feasible.
- Option B: require the user to log in with a GoRefer account (mobile OTP) and enter their Zerodha Client ID; ownership of the client ID is NOT verified, but abuse can be detected later.
- Option C: allow anyone to generate a referral link by entering a Client ID. NOT recommended by ChatGPT (someone could enter another person's Client ID and misuse their referral benefits).
ChatGPT's stance: before deciding, explore any practical non-Zerodha way to verify ownership without adding friction; if none exists, design the safest possible fallback. This decision affects security, fraud prevention, and UX. STATUS: awaiting Abhay's decision. (Cross-reference: this is the same self-service-referrer identity/verification problem discussed in the Cowork session — see GoRefer-Build-Spec-Cowork-Decisions.md; Abhay's prior stance there favored minimal friction / raw client_id.)

### Addition 23 — Two Products (Sprint 1 vs Future SaaS), GoRefer User with Multiple Partner Accounts, Partner Credentials, "Build for Tomorrow, Enable only Today"
Question raised: how does a person who doesn't know Abhay create a referral link — come to the website/app, log in, create, and share? For Zerodha we pre-build the link from the Zerodha ID; but non-customers would self-enter their ID. And the same person might refer for Zerodha, properties, and other future partners.
Realization: two different products are being mixed.
- **Product 1 (Sprint 1) — Referral Platform for YOUR customers.** Abhay already has Zerodha customers and their Client IDs; sends them a WATI campaign; GoRefer generates and manages their referral links. Goal: increase referrals from the existing customer base. This delivers value quickly.
- **Product 2 (Future) — Public Referral Platform.** Anyone visits gorefer.in, chooses Zerodha / Groww / Properties / Insurance / etc., logs in, creates an account, manages referrals, tracks rewards. Almost a separate SaaS product.
**Do NOT build Product 2 now** — it doesn't answer the first business question ("Can GoRefer increase Zerodha referrals from your existing customers?"). Validate that first. But DESIGN the architecture so Product 2 fits naturally later.
**Core data design (future-proof):** from day one every "referrer" is simply a GoRefer User; each user can have one or more Partner Accounts:
```
GoRefer User
 ├── Zerodha    Client ID: ABC123
 ├── Groww      Client ID: GR5678
 ├── Insurance  Agent Code: INS001
 └── Property   Broker ID: PROP45
```
**Sprint 1 — the ONLY way a GoRefer User is created:** imported from Abhay's customer list -> WATI campaign sent -> referral link generated. No public sign-up yet.
**Future Sprint:** simply add sign-up, login, "Add Partner Account", start referring. The database does NOT need to change because it was already designed for multiple partner accounts.
**Architectural change — think "Partner Credentials", not "Zerodha Client ID".** For Zerodha the Credential Type is "Client ID"; for Properties, "Agent ID"; for Insurance, "Advisor Code". The referral engine does not care what the credential is — it just stores the credential for the selected partner. Adding a new partner becomes mostly CONFIGURATION rather than new code.
**Principle adopted — "Build for tomorrow, enable only today":** the architecture supports multiple partners and self-service users, but the UI and features initially expose ONLY the Zerodha flow for existing customers. A clean upgrade path without slowing Sprint 1 — don't overbuild today, but don't paint into a corner for Groww/insurance/properties later.

### Addition 24 — Referrer Self-View "My Referrals" & Role-Based Dashboards (ADR-009)
Feature request: a referrer (the customer) should also be able to track his OWN shared link — how many people clicked, from where, etc. Provide this to a logged-in referrer.
**GoRefer has two personas:**
- Persona 1 — Admin (Abhay + team): which customers refer the most; which links are clicked; which campaigns work; which customers to encourage; which referrals became leads; which leads became accounts. This is the Admin Dashboard.
- Persona 2 — the Referrer (the Zerodha customer): cares only about their OWN referral performance. After login (or via a secure personalized link), they see their "My Referrals" page.
**"My Referrals" example:**
```
Hi Abhay 👋  — Your Zerodha Referral Summary
Referral Link [ Copy ]
Total Clicks 24 | Unique Visitors 19 | Account Opening Page Visits 15 | Leads Contacted 4 | Accounts Opened 2 (from Zoho)
Recent Activity:
  Yesterday   Someone clicked your referral link
  2 days ago  Someone visited from Lucknow
  4 days ago  Someone clicked from Android
  5 days ago  Lead created
Share Again: WhatsApp | Status | Facebook | Instagram | Copy Link
```
Gives the customer a reason to come back to GoRefer.
**Motivate action, not just report:**
```
🎯 Referral Progress — Clicks 24 | Accounts Opened 2
You need 1 more successful referral to unlock Zerodha's referral benefits.  [ Refer Another Friend ]
```
**Privacy (critical).** The referrer must NOT see: friend's full name, friend's mobile number, internal CRM notes, executive comments. They only see aggregated/anonymized info: "Someone clicked from Delhi", "Someone started the account opening process", "Two accounts have been opened."
**Both sides, same events.** Admin view = complete visibility across all customers and all partners. Referrer view = complete visibility into their own journey. The SAME underlying events power both dashboards; each sees only what they are authorized to see (no data duplication, presented differently by role).
**Naming:** call the customer view "My Referrals," not "Dashboard" — the customer thinks "I want to know if anyone used my referral," not "I want analytics."
**ADR-009 (LOCKED) — role-based dashboards from the beginning:**
1. Admin Dashboard (Abhay + team): cross-partner analytics; customer performance; campaign analytics; referral intelligence; lead and account status (via Zoho).
2. Referrer Dashboard ("My Referrals"): personal referral link; share tools; click history; unique visitors; landing page visits; account-opening page visits; accounts opened (synced from Zoho when applicable); progress toward referral milestones; recent activity timeline.
Considered a CORE capability (not an enhancement): it gives customers a reason to return, share more, and stay engaged, while giving Abhay the operational intelligence to grow referrals across Zerodha today and other partners later.

### Addition 25 — Consolidation Checkpoint: What's Finalized, 5 Pending Decisions, Spec Plan, and AI Review Board

ChatGPT's confidence ~92–93%; only a handful of product decisions remain before an implementation-ready spec.

**Considered FINALIZED:**

- Business Goal: build GoRefer, initially only Zerodha referrals; architecture extensible for Groww, insurance, properties, etc.
- Technology: GoRefer owns its own PostgreSQL DB; Zoho CRM manages leads/contacts/sales pipeline; WATI manages WhatsApp communication; GoRefer orchestrates everything.
- URL Strategy: gorefer.in/r/{token} for referral links; gorefer.in/zerodha as the public information page.
- Referral Tracking: every customer has a referral token; tracking starts from the first click; every click stored as a separate event; redirects to Zerodha tracked; Zoho enriches the journey with lead/contact status.
- User Types: existing customers (imported from Zoho/WATI); future self-service users (not Sprint 1, but architecture supports them).
- Dashboards: Admin dashboard; Customer "My Referrals" dashboard.

**5 PENDING DECISIONS (to resolve before freezing the Zerodha design):**

1. Authentication — how does an existing Zerodha customer access "My Referrals"? Options: magic link from WATI; mobile OTP; passwordless login; remembered session. Affects security + UX.
2. Referral Token Strategy — one permanent token per customer (gorefer.in/r/ABC123) OR multiple tokens per channel (WhatsApp->Token A, Facebook->Token B, Status->Token C). ChatGPT leans multiple (channel-level analytics) but wants to weigh Sprint-1 complexity.
3. Landing Page — friend clicks link: redirect immediately to Zerodha, OR first show a GoRefer page (why open a Zerodha account, benefits, free assistance) then redirect. ChatGPT recommends the second (explains value, increases chance they contact the team).
4. Lead Creation timing — when does GoRefer create a Zoho lead? On first click / after clicking "Open Zerodha Account" / only after name+mobile submitted. Impacts lead quality.
5. Customer Identity — primary identifier / master key for existing customers: Zerodha Client ID, mobile number, or Zoho Contact ID.

**Next deliverable ChatGPT proposes:** "GoRefer Sprint 1 – Zerodha Referral Design Specification v1.0" — a product & architecture spec (NOT a coding prompt) covering business objectives, user journeys, system architecture, database model, API contracts, UI wireframes, referral lifecycle, event model, Zoho integration, WATI integration, security model, future extensibility, explicit assumptions, open questions. Target ~40–60 pages.

**AI Design Review Board (ChatGPT's proposal):** take the spec to multiple models — Claude ("review as a principal software architect; identify weaknesses"), Grok ("challenge every assumption; what are we missing?"), Gemini ("review UX and scalability"); ChatGPT consolidates feedback into v1.1. Only then Claude Code implements.

### Addition 26 — Multiple Referral Programs per User; One Permanent Link per User per Program; Link Types; Channel Analytics via Share Events (ADR-010)

A customer should be able to generate a separate referral link per business (e.g. one for Zerodha, another for Properties), or reuse — his choice. ChatGPT refinement: NOT "one link for everything" — instead ONE GoRefer account, MULTIPLE referral links:

```
GoRefer User (Abhay)
 ├── Zerodha        gorefer.in/r/Z8XK92
 ├── Properties     gorefer.in/r/P4LM21
 ├── Insurance      gorefer.in/r/I7AQ18
 ├── Mutual Funds   gorefer.in/r/M3RT66
 └── Credit Cards   gorefer.in/r/C5GH90
```

Each business has different landing pages, benefits, tracking, analytics, and conversion funnels. The customer feels like ONE GoRefer account ("I have one GoRefer account with multiple referral programs"); login shows "My Referral Programs" with per-program Copy Link / Share.

Do NOT allow one universal link that asks the visitor to choose Zerodha/Insurance/Property/Loan — it hurts conversion; a Zerodha referral must land directly in the Zerodha journey.

**Three link types:**

1. Program Referral Link (most important): gorefer.in/r/Z8XK92 — directly opens the Zerodha referral journey; used by WATI and campaigns.
2. Public Referral Profile (later): gorefer.in/u/abhay — NOT a referral link; a public profile showing all programs available through that user; visitors who know them choose what interests them.
3. Partner Information Page: gorefer.in/zerodha — general info about Zerodha referrals, no personalization.

Adding a new program later = just add another referral program to the user's account (no DB redesign, no new login, no migration).

**Referral token model resolved:** ONE permanent referral link per user per program. For analytics, every share (WhatsApp, Facebook, Status, Email, etc.) gets its own share event ID behind the scenes. Best of both: the customer always shares the same easy-to-remember link; GoRefer still knows the channel origin when the share happens through GoRefer; no dozens of URLs per program.

**ADR-010 (Proposed):** a GoRefer User can participate in multiple referral programs; each program has ONE permanent referral link for that user; each program has its own dashboard, analytics, and landing experience; a future public profile (gorefer.in/u/{username}) can showcase all programs but is NOT used for campaign referrals; channel-level analytics are achieved through share events, not by creating multiple permanent links for the same program.

### Addition 27 — "No Coming Soon" Principle & GoRefer Product Principles (97–98% confident on the Zerodha MVP)

Abhay's directive: never show "Coming Soon" — it gives false hope. The dashboard reflects only what is actually available today. New design principle: "Never show a feature the user cannot use today."

Sprint 1 dashboard (Zerodha only):

```
My Referral Programs
📈 Zerodha  — [ View Dashboard ] [ Copy Referral Link ] [ Share ]
(nothing else)
```

Later, when Properties launches it simply appears; when Insurance launches it appears — no placeholders, no "Coming Soon."

**GoRefer product principles:**

1. Don't tease unfinished features — only show features that work.
2. One primary action per screen — make the next step obvious.
3. Minimize user effort — if GoRefer can automate it, it should.
4. Measure everything — every click, redirect, share, business event recorded where technically possible.
5. Build for tomorrow, expose only today's capabilities — architecture supports multiple programs; UI exposes only live ones.

**Feature-evaluation commitment:** every proposed feature is judged by — does it increase referrals? reduce user effort? simplify the UI? is it needed in Sprint 1? can it be added later without changing the architecture? If the first four aren't compelling, it is pushed to a later sprint.

**Status:** ~97–98% confident on the Zerodha MVP. Only implementation-level decisions remain (authentication flow, exact Zoho synchronization mechanics, deployment stack), not product-vision decisions. Next deliverable: a comprehensive Zerodha MVP Design Specification to submit to Claude, Grok, and Gemini for independent review before Claude Code implements — to become the single source of truth for Sprint 1, then frozen and built to exactly.

### Addition 28 — Sprint 1 Authentication: Admin-Only, Bootstrap Admin, Feature Flags, Demo Mode (ADR-011)
Decision on the pending Authentication question. For Sprint 1 we are NOT building full authentication — Abhay is the only user testing initially, so no OTPs, passwords, sessions, or user registration are needed. One role: Admin (Abhay).
Architecture (ready for future, only admin active):
```
Authentication Service
 ├── Admin Login    (Enabled)
 ├── Customer Login (Disabled)
 └── Future OTP Login (Planned)
```
Future public launch replaces the auth module with Mobile OTP, Magic Link, optional Google Login, optional Email OTP — the rest of GoRefer does not change.
**Bootstrap admin (production-friendly, do NOT hardcode the account):** on first run, no users exist; the app creates one Admin user from environment variables:
```
ADMIN_NAME=Abhay Kumar
ADMIN_EMAIL=...
ADMIN_PASSWORD=...
```
Deploying to another server = just change the env vars, no code changes.
**Feature flags hide all unfinished functionality** (better than commenting out code or showing "Coming Soon"):
```
ENABLE_CUSTOMER_LOGIN=false
ENABLE_SELF_SERVICE=false
ENABLE_MULTIPLE_PARTNERS=false
ENABLE_REWARDS=false
```
Flip a flag in Sprint 2/3 when the feature is complete.
**ADR-011 (Proposed — recommended to lock):** Sprint 1 = Admin login only; bootstrap admin created from environment variables; customer authentication architecture exists but is disabled; feature flags control unfinished capabilities; no "Coming Soon" screens or inaccessible menu items.
**Demo Mode from day one:** populate the app with sample referral data so Claude, Grok, or another developer can run the project locally and immediately understand GoRefer without Abhay's real data or Zoho setup. Does not affect production; eases development, testing, and future collaboration/review.

### Addition 29 — Public Marketing Homepage + Login, "GoRefer Foundation", Product Positioning (ADR-012)

gorefer.in should be a public marketing WEBSITE (not the application dashboard). A visitor immediately understands: (1) What is GoRefer? (2) Why use it? (3) How to get started.

Homepage content sketch:

```
Hero: "One Referral Link. Unlimited Opportunities."
      Help your friends discover trusted financial products & services while tracking all your referrals from one place.
      [Learn More]                                   [Login] (top-right)
What is GoRefer? — manage & share referral links for multiple trusted partners from one place:
      manage referral programs, share personalized links, track referral activity, monitor clicks & conversions, grow referral income
Why GoRefer? — one place for all programs; smart tracking; easy sharing; personalized referral kits; detailed analytics; mobile-friendly
Supported Programs: Zerodha (initially; section auto-expands as more partners launch)
Footer: About Us | Privacy Policy | Terms | Contact
```

**Login:** top-right button. Sprint 1 — only Abhay's credentials work. Anyone else attempting to log in gets a friendly message: "Access is currently by invitation only." (Not an error, not "Coming Soon.")

**Login flow (don't expose /admin, /dashboard):**

```
gorefer.in -> click Login -> gorefer.in/login -> enter credentials -> Dashboard
```

Future (when registrations open): the SAME login page becomes Email/Mobile + Password/OTP, or "Continue with Mobile OTP" — architecture unchanged.

**Positioning:** internally position GoRefer as a "Referral Intelligence Platform" (or "Referral Management Platform") rather than a plain "Referral Platform" — sounds like a professional product that helps users understand and improve referral performance, not just a link generator. (May not appear prominently on the homepage, but drives design.)

**Naming:** stop calling Sprint 1 the "Zerodha MVP" — call it "GoRefer Foundation," because although only Zerodha is enabled, the core platform is built correctly from the start so future partners (Groww, insurance, properties) plug into the same foundation.

**ADR-012 (Locked):** gorefer.in is a public marketing website, not the dashboard; it explains GoRefer, its purpose, benefits, and supported programs; a Login button appears top-right; in Sprint 1 only the bootstrap admin (Abhay) can authenticate; anyone else gets "Access is currently by invitation only"; the dashboard stays behind authentication; the same login flow later supports customer authentication without redesigning the application.

### Addition 30 — Business-Rule Question 1: Owner Self-Click Handling (Owner Preview vs Counted Click)

ChatGPT confidence 98%; remaining 2% is a few business rules that, if wrong now, would force a later database/workflow change. ChatGPT will ask one question at a time until >99% confidence.

**Question 1 (most important):** Send a WATI campaign to 10,000 Zerodha customers; each gets their own personalized referral link. Suppose Customer A clicks their OWN referral link (curiosity or to see what it looks like). Should GoRefer:

- Option A (ChatGPT's recommendation): ignore it for referral analytics — record it as an "Owner Preview" / "Internal Click," but do NOT count it toward referral clicks, unique visitors, or referral performance.
- Option B: count it exactly like any other click.

Why it matters: without distinguishing an owner's self-click from a genuine referral click, analytics become misleading (a customer might open their own link 20 times while testing, making it look like real referral interest). ChatGPT recommends Option A — record the event for auditing but exclude it from referral metrics by default, with an admin-dashboard option to view owner-preview events. STATUS: awaiting Abhay's answer. (Cross-reference: aligns with the self-click / bot-click filtering already flagged in the Cowork click-tracking discussion — see GoRefer-Build-Spec-Cowork-Decisions.md / click-tracking notes.)

### Addition 31 — Click Confidence Classification (not owner-exclusion) + Business-Rule Question 2 (Same Journey vs New Journey on Re-Click)
Abhay's steer: don't DISCOUNT owner clicks, but — how would we even know a click was by the owner vs someone else? ChatGPT: we DON'T know with 100% certainty, and shouldn't pretend to. Even if the WATI campaign goes to Abhay's mobile and he clicks it from the same WhatsApp chat, we still can't prove it was him (borrowed phone, forwarded message). Without authentication, make no assumptions.
**Revised approach — classify CONFIDENCE, not identity.** Every click gets a confidence level:
```
Unknown (default)      - we don't know who clicked
Authenticated Owner    - the owner was logged in
Authenticated Visitor  - future capability, if visitors ever log in
Internal Test          - owner/admin explicitly marks it as a test
```
In Sprint 1 almost every click is "Unknown" unless someone is logged into the admin interface and deliberately testing. This keeps analytics honest.
Instead of asking "did the owner click?", ask "is this probably the same device that received the campaign?" Collect signals: device fingerprint (privacy-friendly), browser, OS, IP address (stored carefully), user agent. These aid analytics and fraud detection but are NEVER proof of identity.
**Therefore:** do NOT auto-exclude owner clicks. Instead: record every click; label each with a confidence classification; let the analytics layer decide how to present it. Maximum flexibility, no incorrect assumptions.
**Question 2 (business rule; ChatGPT confidence now 98.8%):** A friend clicks a referral link today but fills no form and doesn't contact anyone. 20 days later they click the SAME link again and this time proceed to Zerodha. Treat this as:
- Option A (ChatGPT's recommendation): the SAME referral journey, continuing the history of that visitor/link.
- Option B: a NEW referral journey every time they click after a long gap.
ChatGPT recommends Option A — preserves the complete referral lifecycle, gives richer analytics, and avoids fragmenting the history into multiple unrelated journeys. STATUS: awaiting Abhay's answer.

### Addition 32 — Final Consolidation of the Zerodha MVP (Q2 resolved; ChatGPT confidence 99.6%)
Abhay answered Question 2: "Go with your recommendation" -> Option A (a re-click after a gap CONTINUES the same referral journey). ChatGPT confidence now 99.6%; no remaining product-architecture decisions block Sprint 1; remaining unknowns are purely implementation details (React vs Next.js, PostgreSQL indexing, deployment config) that Claude Code handles.
**LOCKED for the Zerodha MVP ("GoRefer Foundation"):**
- Vision: GoRefer is a Referral Management & Intelligence Platform; Sprint 1 enables ONLY Zerodha, but the architecture is designed for multiple programs.
- Technology Stack: Frontend = modern web app (mobile-first); Backend = GoRefer API layer; Database = PostgreSQL (GoRefer's source of truth); Messaging = WATI; CRM = Zoho CRM; Hosting = to be finalized during implementation.
- Public Website: gorefer.in explains GoRefer, benefits, supported programs; has a Login button; no dashboard exposed publicly.
- Authentication: bootstrap Admin only (Abhay); customer-login architecture exists but disabled; no "Coming Soon" pages.
- Referral Programs: Zerodha only initially; architecture supports Properties, Insurance, Mutual Funds, Loans, Credit Cards, future partners.
- Referral Links: one permanent referral link per user per program (e.g. gorefer.in/r/Z8XK92); no regenerating a new permanent link each time.
- Tracking Philosophy: track everything GoRefer actually observes (link creation, click, landing page, redirect, lead creation, contact creation via Zoho, timeline); never invent data GoRefer cannot verify.
- Referral Journey: starts on the first click; subsequent clicks extend the same journey rather than fragmenting history.
- Dashboards: Admin (referral analytics, customer performance, campaign performance, lead pipeline via Zoho, filters by partner/date/customer/status); Customer (future: personal link, personal analytics, share options, progress) — architecture ready, UI disabled in Sprint 1.
- Design Principles: no "Coming Soon"; mobile-first; build for tomorrow, expose only today's features; measure everything possible; business logic in GoRefer; CRM logic in Zoho; messaging in WATI.

### Addition 33 — LLM Review Process & the Three Deliverables (Foundation Spec, ADRs, LLM Review Guide)
Goal: share a DESIGN SPECIFICATION with other LLMs (not a prompt), so each reviews as a Principal Architect reviewing a design doc before implementation. Recommended process:
- Phase 1 — Create the Design Specification (single source of truth): product vision, business goals, scope, out-of-scope, user personas, user journeys, UI/UX, landing page, referral flow, database design, event model, tracking philosophy, Zoho integration, WATI integration, APIs, dashboard, future roadmap, ADRs, risks, open assumptions, acceptance criteria. Detailed enough that a new engineer could onboard without talking to anyone (~60-100 pages equivalent).
- Phase 2 — Create role-specific Review Prompts:
```
Claude  = Principal Software Architect: challenge database design, scalability, APIs, security; suggest improvements; identify missing requirements; do NOT rewrite the whole architecture.
Grok    = Product Strategist: challenge business assumptions, user journeys, onboarding, growth strategy, monetization, referral psychology.
Gemini  = UX + Platform Architect: review UI, dashboards, usability, future extensibility, mobile-first design.
```
Each LLM reviews from a DIFFERENT angle (more valuable than the same generic question).
- Phase 3 — Consolidation via a Review Matrix (Suggestion | Source | Decision | Reason); nothing accepted automatically, everything evaluated.
- Phase 4 — Design v1.1: update architecture, database, APIs, UI, flows.
- Phase 5 — Freeze: "GoRefer Foundation v1.1 = FROZEN"; only then Claude Code starts coding.
Also maintain a **Decision Log (ADRs)** — every important decision with rationale (e.g. ADR-001 PostgreSQL not MongoDB — relationships/analytics/scalability; ADR-007 one referral link per program — simple/scalable/easy; ADR-011 admin-only login in Sprint 1 — reduce complexity/focus on core engine) so when Claude suggests a change it can be compared against the original reasoning.
**Recommendation — produce THREE documents:** (1) GoRefer Foundation Specification (complete product + technical blueprint); (2) Architecture Decision Records (every key decision + rationale); (3) LLM Review Guide (specialized review instructions for Claude, Grok, Gemini, future models). Disciplined process: define the product -> document why -> challenge with multiple reviewers -> consolidate -> freeze -> implement with Claude Code.

### Addition 34 — Professional Project Repository & AI-First Documentation Plan
Rather than one 70-100 page document (which hits an LLM response-length limit and gets cut off), create a COMPLETE project repository, incrementally and version-controlled. Proposed structure (200+ pages equivalent when complete):
```
GoRefer/
├── 00-README.md
├── 01-GoRefer-Foundation-Specification.md
├── 02-Architecture-Decisions-ADR.md
├── 03-GoRefer-Constitution.md
├── 04-System-Architecture.md
├── 05-Database-Design.md
├── 06-API-Specification.md
├── 07-UI-UX-Specification.md
├── 08-Zoho-WATI-Integration.md
├── 09-Review-Pack/ (Claude.md, Grok.md, Gemini.md)
└── 10-Claude-Code-Implementation-Guide.md
```
Generate as real downloadable Markdown (.md) files (Claude Code reads Markdown well; GitHub renders it; Grok/Gemini ingest it; version-controllable; independently reviewable). Every future discussion updates these documents instead of relying on chat history.
**AI-first repository:** every document includes human-readable explanations, machine-readable sections, stable requirement IDs (REQ-001, REQ-002, ...), Architecture Decision Records (ADR-001, ...), and cross-references between documents — so Claude Code and future AI tools can navigate and implement consistently.

### Addition 35 — Documentation Build Kicked Off (expectations + document order)
ChatGPT created the first draft: 01-GoRefer-Foundation-Specification-v1.0.md — a STARTING document, not the final spec. The complete set will be ~200+ pages across multiple Markdown files. Planned documents:
```
01 GoRefer Foundation Specification (expand to ~50-80 pages equivalent)
02 Architecture Decision Records (ADR)
03 GoRefer Constitution
04 System Architecture
05 Database Design (tables, ERD, indexes, constraints)
06 API Specification
07 UI/UX Specification (wireframes + flows)
08 Zoho CRM & WATI Integration
09 LLM Review Pack (Claude, Grok, Gemini)
10 Claude Code Implementation Guide
```
Quality bar: each document detailed enough that Claude Code can implement directly from it, Grok/Gemini can review meaningfully, and GoRefer can evolve for years without losing design decisions. Treated as a real software-architecture project, produced document by document (Foundation Spec first, then ADRs, then the rest).

### Addition 36 — Documentation Starter Pack Assembled (not for review yet)
ChatGPT assembled a starter pack (GoRefer_Documentation_Starter_Pack.zip) containing 10 skeleton Markdown docs: 01-GoRefer-Foundation-Specification-v1.0.md, 02-Architecture-Decisions-ADR.md, 03-GoRefer-Constitution.md, 04-System-Architecture.md, 05-Database-Design.md, 06-API-Specification.md, 07-UI-UX-Specification.md, 08-Zoho-WATI-Integration.md, 09-LLM-Review-Pack.md, 10-Claude-Code-Implementation-Guide.md.
Do NOT send these to the review LLMs yet — they are starter skeletons, not the comprehensive documents intended. Target is ~250-350 pages equivalent:

```
Foundation      ~60-80 pages
Database        ~30-40 pages
API             ~30 pages
UI/UX           ~50 pages (flows/wireframes)
Claude Code Guide ~50+ pages
ADRs + Constitution + Review Pack  ~30-40 pages
```

Plan: expand each document to production quality, review each together, and only after the repository is complete send it to the other LLMs.

### Addition 37 — Full Rewrite to Production Quality, ChatGPT's Own Architecture Review, and the Quality Gate
ChatGPT takes ownership and will rewrite the documentation almost from scratch (current quality ~15-20% of target) to the level a senior architect would hand over before a multi-month project: every requirement explicit, every business rule documented, every edge case considered, every architectural decision justified, every API defined, every table documented, every user flow illustrated.

Documentation set (targets):

```
Part 1  Foundation Specification   ~70-100 pages
Part 2  System Architecture        ~40-60 pages (component & sequence diagrams, deployment, services, background jobs, event architecture, security, scalability)
Part 3  Database Design            ~40-50 pages (every table's purpose/columns/constraints/indexes/relationships/extensibility + ER diagrams)
Part 4  API Specification          every endpoint: request, response, validation, error handling, authentication, examples
Part 5  UI/UX Specification        every screen/button/modal; desktop/tablet/mobile
Part 6  Claude Code Guide          how to build, folder structure, coding standards, testing, git workflow, feature flags, migration strategy, Definition of Done
Part 7  LLM Review Pack            tailored prompts for Claude, Grok, Gemini with structured review questions
Part 8  Architecture Decision Records
Part 9  GoRefer Constitution
```

**ChatGPT's own Architecture Review (adversarial — deliberately try to break the design) before external review**, asking e.g.:

```
- What happens if Zoho is down?
- What if WATI sends duplicate messages?
- What if a referral link is leaked?
- What if someone generates millions of clicks?
- How do we prevent analytics corruption?
- How do we migrate to multiple partners?
- What if two referral programs have conflicting credential requirements?
```

Only after no major weaknesses remain are the documents considered ready.

**Quality gate (all must be true before sharing externally):**

```
- ChatGPT >=99.5% confident in the architecture
- documents internally consistent
- cross-references correct
- every requirement has a unique ID
- every ADR linked to the relevant requirement
- architecture passed the internal review
- the reviewers will spend effort critiquing the design rather than asking basic clarifications
```

Only then: "GoRefer Architecture Review Package v1.0 is ready for external review" — accompanied by three tailored review prompts (Claude, Grok, Gemini), a feedback-collection template, and a review matrix to merge the best ideas into v1.1 before implementation.
