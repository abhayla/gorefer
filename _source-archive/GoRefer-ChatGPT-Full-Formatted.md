# GoRefer — ChatGPT Conversation (Full Transcript)

_Source: ChatGPT shared conversation "Zerodha Referral Image Design"_
_Share URL: https://chatgpt.com/share/6a489986-add8-83ee-9971-403b921314be_

---

## User

[image]

Refer attached image for New Zerodha Account opening 
Now on similar lines, create image for Zerodha account referral 
Update the scanner to open this link: 
https://signup.zerodha.com/api/lead?c=ZMPHZC

Do not proceed until you have more than 95% confidence of my ask. Ask me questions until you get that confidence. Ask one question at a time.

---

## User

You already have accout in Zerodha.

Now Refer your friends to earn rewards!
1. 10% brokerage share - earn 10% of the brokerage that every eligible referred account generates
2. 300 reward points - receive 300 reward points per account opened. 

Eligibility - at least 3 successful referrals in the past 12 months.

Follow these steps to refer:
1. Click Referral Link to refer friend
2. Reply to this message and share friend's Name and Mobile
3. We will contact and help in Free and Fast account opening
4. Once account opened, you start getting referral benefits

Referral Link - https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}
Open Zerodha Account: https://signup.zerodha.com/?c=ZMPHZC
View Referral and Rewards - https://console.zerodha.com/refer

---

## ChatGPT

Let's focus purely on the **Zerodha Referral Workflow** and ignore implementation details for now.

One of the biggest things I realized while researching is that **there are actually two separate workflows**:

1. **Zerodha's official referral workflow**

2. **Your enhanced workflow** (where your team helps with account opening)

Your opportunity is to combine them.

# Workflow 1: Official Zerodha Referral Workflow

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

* The brokerage-sharing benefit requires meeting Zerodha's eligibility conditions (such as maintaining at least three successful referrals in the past 12 months). [[image]Zerodha Support+1](https://support.zerodha.com/category/console/profile/account/articles/how-do-i-refer-zerodha-to-my-friends-or-family)

# Official Zerodha Rules

## Step 1

Customer has a Zerodha account.

Example:

```
Client ID

AB1234
```

## Step 2

Customer generates a referral link.

Example:

```
https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB1234
```

## Step 3

Customer shares this link.

Can be via:

- WhatsApp

- SMS
- Email

- Facebook

- LinkedIn

- Copy Link

## Step 4

Friend clicks the link.

This creates the referral mapping.

## Step 5

Friend completes account opening.

Important:

- Account must be opened within **60 days** of referral.

- If the prospect had already registered on Zerodha **before** using the referral link, the referral mapping won't apply. [[image]Zerodha Support+1](https://support.zerodha.com/category/console/profile/account/articles/how-do-i-refer-zerodha-to-my-friends-or-family)

## Step 6

Friend starts trading.

Now:

- 300 reward points are credited.

- Brokerage sharing starts (subject to eligibility). [[image]Zerodha Support+1](https://support.zerodha.com/category/console/profile/account/articles/how-do-i-refer-zerodha-to-my-friends-or-family)

# Where customers struggle

This is the part you've correctly identified.

The customer has to:

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

Most customers don't want to do all this.

# Your enhanced workflow

This is where you add value.

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

But there is one critical step.

# The Referral Link

You **must ensure the friend's account is opened through the customer's own referral link** so the referral is attributed correctly.
That means your team needs to use or share the customer's personalized referral URL before the prospect completes the account-opening process. If someone registers directly on Zerodha first and only later uses the referral link, the referral won't be mapped. [[image]Zerodha Support+1](https://support.zerodha.com/category/console/profile/account/articles/how-do-i-refer-zerodha-to-my-friends-or-family)

# I think the ideal workflow is this

```
Customer receives WhatsApp

        │

        ▼

Replies

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
This keeps the customer's effort minimal while preserving the referral attribution.

# I would add one more automation

Since you're already using the Meta API and WATI:

```
Campaign

↓

Customer replies

↓

Bot asks

Friend Name?

↓

Friend Mobile?

↓

Bot stores CRM

↓

Executive assigned

↓

Executive gets

Customer Name

Customer Client ID

Referral Link

Friend Details

↓

Call initiated
```

At that point, your executive already has everything needed before making the first call.

# One issue I think we should solve

From everything we've discussed over the past few months, I think the **biggest bottleneck isn't getting referrals—it's preserving the referral mapping while making the process effortless**.

Instead of asking the customer to manage the referral link manually, I'd build a **GoRefer workflow** that sits between WATI and Zerodha.

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

That architecture gives you:

- One place to manage referrals.

- Visibility into the referral pipeline.

- Reduced manual work.

- The ability to extend the same platform later to referrals for insurance, mutual funds, loans, and other products.

For your long-term vision, I think **GoRefer should become the referral management layer**, while Zerodha remains the underlying brokerage platform. That separation makes the system reusable across multiple referral programs in the future.

---

## User
Break the whole workflow from multiple angels - Meta Template in Wati, WhatsApp status message or Pic for Zerodha clients to encourage them to refer, pre-built Message for clients which they can post on social media like Facebook, Instagram. Everywhere referal links should be there both for customer and partner (ZMPHZC)

---

## ChatGPT

I think we should treat this as a **Referral Growth System**, not just a WhatsApp campaign. Every touchpoint should have one goal: **make it effortless for an existing Zerodha customer to refer friends while ensuring the referral is attributed correctly.**

Here's how I'd break it down.

# Referral Growth System

```
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

# 1. WATI / Meta WhatsApp Template

This should target **existing Zerodha customers**.

### Header

Referral poster (premium image)

### Body

- Personalize with customer name.

- Mention the rewards.
- Recommend the easiest option (share friend's details).

- Also include the customer's **personalized referral link**.

Example variables:

- `{{1}}` = Customer Name

- `{{2}}` = Customer Referral Link

- `{{3}}` = Partner Link (your AP account opening link)

CTA should encourage replies rather than just clicks.

# 2. WhatsApp Status (Customer Posts)

Remember: Status doesn't support clickable links.

So the objective changes.

Instead of:

> Scan QR

I'd use:

> 🎁 Earn Zerodha Referral Rewards!
> Get:
> 
> ✔ 10% Brokerage Share*
> 
> ✔ 300 Reward Points
> Interested?
> Message me.

Then include:

- customer's referral link

- your AP link

For example:

```
My Referral Link

https://z.gorefer.in/{{client_id}}

Need Help?

https://z.gorefer.in/open
```

# 3. WhatsApp Status Image

I'd avoid lots of text.

Visual hierarchy:

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

# 4. Facebook Post

Facebook supports clickable URLs.

Template:

> 🎁 Already planning to invest?
> Open your FREE Zerodha account using my referral link.
> My Referral Link:
> {{Customer Referral Link}}
> Need help?
> Open through our partner:
> {{Partner Link}}

# 5. Instagram

Instagram captions don't make links clickable.

Instead:

```
Referral Link

👇

z.gorefer.in/AB123
```

or

```
Link in Bio
```

The bio points to

```
gorefer.in
```

# 6. LinkedIn

Professional tone.

> Investing soon?
> I'd appreciate it if you used my Zerodha referral link.
> {{Customer Referral Link}}
> If you need assistance with account opening, here's a partner who can help:
> {{Partner Link}}

# 7. Twitter/X

Keep it concise.

```
Thinking of opening a Zerodha account?

Use my referral link:

{{Customer Link}}
Need assistance?

{{Partner Link}}
```

# 8. Email Template

Subject:

> Earn Zerodha Referral Rewards

Body:

Explain benefits.

Large button:

```
Share Referral Link
```

Secondary button:

```
Need Help Opening Account?
```

# 9. Referral Landing Page

Suppose customer visits

```
z.gorefer.in/AB123
```

The page should display:

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

This page then redirects to

```
https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=AB123
```

# 10. Partner Link

You asked that **both links** should always be present.

I'd structure it like this.

## Customer Link

```
My Referral Link

https://z.gorefer.in/{{client_id}}
```

Purpose:

Customer earns rewards.

## Partner Link

```
Need Assistance?

https://z.gorefer.in/open
```

Purpose:

Lead comes to your team.

You help with documentation.
Eventually redirect using the customer's referral link whenever appropriate so the customer receives referral credit.

# Recommended URL Strategy

| Purpose | URL |
| --- | --- |
| Customer Referral | `z.gorefer.in/{{client_id}}` |
| Partner Account Opening | `z.gorefer.in/open` |
| Referral Benefits | `z.gorefer.in/rewards` |
| Referral FAQ | `z.gorefer.in/help` |
| Track Rewards | `z.gorefer.in/track` |

# The One Thing I'd Change

I would **not expose Zerodha URLs anywhere**.

Instead of sending:

```
https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}
```

customers always see:

```
https://z.gorefer.in/{{client_id}}
```

and instead of:

```
https://signup.zerodha.com/?c=ZMPHZC
```

they see:

```
https://z.gorefer.in/open
```

Your server then redirects to the appropriate Zerodha URL. This gives you several advantages:

- Cleaner, more memorable links.
- Ability to track clicks and campaign performance.

- Freedom to change the destination later without updating every template or poster.

- Consistent branding across WhatsApp, social media, emails, and printed materials.

That approach also scales naturally when you add other referral programs under `gorefer.in` in the future.

---

## User

this is very high level information. Give very detailed and comprehensive information. I will then share it with Claude code which will then implment everything e2e.

---

## ChatGPT (image generation)

Perfect. Since you plan to hand this to Claude Code for end-to-end implementation, I'll give you a detailed product + technical specification for the Zerodha Referral Growth System using WATI + Meta WhatsApp API + gorefer.in.

This is written as an implementation-ready blueprint.
