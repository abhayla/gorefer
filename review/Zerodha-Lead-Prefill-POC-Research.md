# Zerodha Lead-Form Prefill — POC Research Findings

> **Mission:** GoRefer192 (remote-control research session). **Researcher:** Engineer (Claude Code), research-only — no production code changed, nothing deployed, nothing submitted to Zerodha.
> **Date:** 2026-07-20. **Resolves:** the OPEN POC in `docs/api/06-API-Specification.md` §5.3 + Open item 5 ("Continue to Zerodha form → Zerodha auto-fill — currently believed not possible") and the CLAUDE.md §4 landing-page note ("Auto-filling Zerodha's own fields is an OPEN POC, NOT a dependency").

---

> **FINAL OUTCOME (2026-07-20, owner-confirmed):** Abhay asked Zerodha directly about the §5
> lead-registration API. **Zerodha confirmed they do NOT currently provide that API to partners.**
> The GO-IF avenue is therefore CLOSED. Combined with the NO-GO below, the complete verdict is:
> **there is no mechanism — prefill or API — to remove the double entry on Zerodha's side.** The
> double entry is a permanent property of the Zerodha funnel until Zerodha changes something.
> ADR-013's blanket "NO Zerodha API, ever" stands unamended. Revisit trigger: only if Zerodha
> announces partner lead-API access. The §5.side-finding (24h direct-mapping window) remains valid.

## Verdict up front

**NO-GO on URL-based prefill.** Zerodha's lead page (`signup.zerodha.com/api/lead/`) accepts **only `c=` (partner code) and `r=` (referral id)** — there is no query-string, hash, or alternate-parameter mechanism that prefills name/email/mobile. This is conclusive from the page's own server-rendered HTML and every script it loads, not an inference.

**GO-IF on a better avenue discovered during the research:** Zerodha's official *Client Introducer — Rules & Procedures* document explicitly sanctions **lead registration via Zerodha's APIs from the Introducer's own website** — which would *eliminate* the double entry entirely rather than easing it. That is a Design-Authority decision + Zerodha sign-off, not an Engineer pick — details in §5.

The prefill result **does not strengthen the case for re-enabling `LANDING_MODE=page`** — see §8.

---

## 1. Method and evidence base

Live in-browser inspection was attempted but the Claude-in-Chrome extension blocks `signup.zerodha.com` at the site-permission level ("not allowed due to safety restrictions"). The fallback was **static inspection via plain GETs** (curl with a mobile-Chrome UA) — equivalent evidence, and in one way stronger: it covers the server's rendering behaviour *and* the complete client-side JS, rather than one browser session's observable state.

All probes were **GET navigations only** — exactly what a browser does on our 302. **Nothing was POSTed, no form was submitted, no reCAPTCHA was touched, no lead was created.** Per Abhay's instruction, all probes used the placeholder partner code `ZMPXXX` (never the live `ZMPHZC`) with `r=EKU497`.

Caching was ruled out: each fetch returned a distinct `csrfmiddlewaretoken`, so every response was freshly rendered — the negative reflection results are real, not a cached page.

Artifacts (session scratchpad): `lead_page.html`, `lead_page_prefill.html`, `alt_params.html`, `account_opening.js`, `zerodha.referral.js`, `any_user_config.js`, `signup_root.html`, `signup_bundle.js`, `utils_bundle.js`, `introducer_extract.txt`.

## 2. What the Zerodha lead page actually is

`GET /api/lead/?c=ZMPXXX&r=EKU497` returns a classic **server-rendered Django page** (17,530 bytes; `csrfmiddlewaretoken`, jQuery 1.12, no SPA). The form:

```html
<form id="lead_data_form" action="/api/lead/register/" method="post" autocomplete="off">
  <input type='hidden' name='csrfmiddlewaretoken' value='…' />
  <input type="text" name="mobile"  id="id_mobile"  placeholder="Your mobile number" maxlength="15" minlength="10" required />
  <input type="text" name="name"   id="id_name"   placeholder="Full name" maxlength="280" minlength="3" required />
  <input type="text" name="email"  id="id_email"  placeholder="E-mail" maxlength="140" minlength="5" />
  <select name="account_type">…Individual (default)…</select>
  <input type="text" name="partner_or_referral" value="ZMPXXX" maxlength="6" />   <!-- ← c= reflected -->
  <input type="text" name="referral"            value="EKU497" maxlength="6" />   <!-- ← r= reflected -->
  <div class="g-recaptcha" id="captcha"></div>
  <button id="lead_data_capture" type="submit">Continue</button>
</form>
```

Key facts:
- The server **does** reflect query params into form values — but **only `c` and `r`**. Our 302 already delivers both; that part of the funnel is optimal today.
- Submission POSTs to `/api/lead/register/` and is gated by Google reCAPTCHA (widget + an inline JS handler that blocks submit until `grecaptcha.getResponse()` is non-empty). Untouched by this research; irrelevant to prefill (a prefill would still leave captcha + submit to the human).
- The form carries `autocomplete="off"` and **no** `autocomplete` tokens on any field (see §3c).

## 3. Mechanisms tested, one by one

### (a) Query-string prefill — **NOT SUPPORTED**
`GET /api/lead/?c=ZMPXXX&r=EKU497&name=PrefillTestName&email=prefilltest%40example.com&mobile=9876543210&phone=9876543210` → byte-identical page (17,530 bytes), zero reflection of any value into `id_mobile` / `id_name` / `id_email` (all render empty). A second probe with **eight alternate param names** (`m`, `n`, `e`, `mob`, `mobile_no`, `full_name`, `lead_name`, `email_id`, `num`) — likewise zero reflection, byte-identical page. The server-side handler simply ignores everything except `c` and `r`.

### (b) URL fragment / hash — **NOT SUPPORTED**
Nothing in the page or any script it loads reads `location.hash` (grep across the HTML + all three first-party scripts: 0 occurrences). A fragment would arrive at the browser and die unread.

Client-side query handling was checked exhaustively: the only script that reads `location.search` is `zerodha.referral.js` (read in full, 121 lines) — it handles **only the `c` param** (validates the partner-id pattern, sets a 24h `ref` attribution cookie, injects a hidden `zlm_partner_id` field into forms with id `zlm_add_lead` — an id this form doesn't have). `account_opening.js` (19 KB) and `any_user_config.js` read no URL params at all.

### (c) Browser-native autofill — **exists, but not a mechanism GoRefer controls**
The form declares `autocomplete="off"` and no field carries an autocomplete token. Chrome (the dominant browser for our Indian-mobile audience) is known to ignore `autocomplete="off"` for its *contact/address* autofill heuristics, and the field names (`name`, `email`, `mobile`) are heuristic-friendly — so a user who has contact data saved in Chrome will *likely* still get autofill suggestions on tap. But: (1) that fills the **user's own saved browser data**, not what GoRefer captured; (2) there is **no web API by which one origin can write another origin's autofill store** — GoRefer cannot inject anything; (3) behaviour varies by browser/WebView (in-app WhatsApp WebView autofill is notably weaker). Net: a happy accident for some users, not a designable mechanism. Nothing to build.

### (d) Documented partner/AP mechanism — **the real finding; see §5**
No *prefill* parameter is documented anywhere (partner materials, Kite Connect ecosystem — Kite Connect is trading APIs, unrelated to onboarding). But Zerodha's official Introducer rulebook sanctions something better: direct lead **registration** via API.

### (e) Everything else considered — all dead or forbidden
- **Cross-origin DOM/JS injection** after the 302: impossible (same-origin policy); Zerodha's page has no `postMessage` listener.
- **Serving a pre-filled replica of Zerodha's form** (same POST target + CSRF + captcha embedded on our page): technically conceivable, **rejected without testing** — it is impersonation/cloning (ADR-014), adjacent to auto-submit (guardrail #1), and would break at Zerodha's whim. Never build this.
- **Clipboard assist** (on "Continue" tap, `navigator.clipboard.writeText(mobile)` inside the user-gesture handler + a "your number is copied — long-press to paste" hint): compliant, cheap, works cross-origin because it goes through the user's clipboard, but helps with one field only and reads as a gimmick. Available as a minor UX option if page mode returns; not recommended as a reason for anything.

## 4. Also checked: the modern root flow (`signup.zerodha.com/`)

Since `/open` targets `signup.zerodha.com/?c=…`, the root flow was inspected too: it is a Vite/Vue SPA (`signup-6FOFLFJ0.js`, ~180 KB + `utils` ~120 KB). Grep of both bundles: **no query-param prefill of any kind** — the `prefill_data` strings visible in the bundle are populated from Zerodha's *own backend session APIs* between signup stages (mobile → OTP → PAN…), not from the URL. Partner attribution again rides only on the `zerodha.referral.js` cookie. Same conclusion as the lead page.

## 5. Discovery: Zerodha's sanctioned lead-registration API (avenue worth pursuing)

Zerodha's official **"Client Introducer — Rules & Procedures"** (zerodha-common.s3.ap-south-1.amazonaws.com/Docs/Introducer-Rules-Procedures.pdf) states that Introducers/APs can add leads three ways (p. 18): manual dashboard entry; **"via APIs on their own page"**; or the affiliate link. Section B (p. 4) is explicit:

> "Via APIs: Introducers may build their own website, frontend and user experience/interface, and by using Zerodha's APIs allow lead registration directly from these websites."

Third-party partner-program reviews corroborate a REST lead-submission API that returns a unique lead id per accepted lead. Access appears to go through the partner portal (partner.zerodha.com / dashboard.zerodhapartner.com) / the PIFS relationship manager; the API docs themselves are behind the partner login — **not retrievable in this session**.

**Why this beats prefill:** prefill still makes the prospect re-type nothing but still face Zerodha's form + captcha. Sanctioned API registration means GoRefer's captured lead lands **directly in Zerodha's CRM as a mapped lead** — the prospect never sees `signup.zerodha.com/api/lead/` at all, and the Ashok-assisted KYC call proceeds from a lead Zerodha already holds. It converts the landing form from "duplicate data entry" into "the only data entry".

**What it is NOT:** it is not auto-submitting the reCAPTCHA form (guardrail #1 targets the public form; this is a partner-authenticated, Zerodha-sanctioned channel). But adopting it would still require, in order: (1) a **DA decision** — it's a new integration and CLAUDE.md currently says "NO Zerodha API, ever" (written about account-status, but the blanket wording would need a deliberate ADR amendment, plus a scoped update to guardrail test #1's "never POSTs to Zerodha" assertion so it keeps protecting the redirect path while permitting an authenticated adapter); (2) **Zerodha written confirmation** of API access + T&C fit (referral T&C cl. 8.vii); (3) the usual contract-doc + flag treatment (`ENABLE_ZERODHA_LEAD_API=false` until all of that lands). **Engineer takes no step on this without a DA MISSION entry.**

**Side finding (attribution intel):** the same document states a prospective client must *initiate account opening within 24 hours of clicking the affiliate link* for the lead to be directly mapped to the Introducer. GoRefer's click-timestamp data can therefore predict/explain unattributed conversions (click → open > 24 h apart). Worth surfacing to the DA for the Referral Explorer someday; no action now.

## 6. Compliance assessment against the mission constraints

1. **Never auto/headless/bot-submit** — upheld: research was GET-only; no POST, no submit, no lead created anywhere.
2. **No reCAPTCHA circumvention** — upheld: captcha never rendered in a JS-executing context, never interacted with; the (dead) prefill avenue wouldn't have touched it either.
3. **Never impersonate/clone Zerodha (ADR-014)** — upheld; the one mechanism that would violate it (form replica, §3e) is documented as rejected-without-testing. Nothing public was produced.
4. **Fill-but-never-submit during live inspection** — moot: the browser extension blocked the site, so the page was never even loaded in a live browser; only static GETs were used. `ZMPXXX` used throughout per Abhay.

## 7. Why prefill is fundamentally impossible (plain-language summary)

For anyone reading this later and wondering "did we just not find the trick?" — there is no trick to find. Two hard walls close every path:

1. **Zerodha's server decides what gets prefilled.** The form fields get their values when Zerodha's own code renders the page. That code reads exactly two things from the URL — `c=` and `r=` — and ignores everything else (proven in §3a: eleven candidate parameter names, byte-identical empty-field responses every time). Unless Zerodha ships new code accepting more parameters, nothing GoRefer puts in the URL can ever appear in those boxes.
2. **The browser forbids one site from touching another site's page.** After the 302 the user is on `signup.zerodha.com`, a different origin; the same-origin policy means no gorefer.in JavaScript can reach into that page and type into its fields. That's not a Zerodha choice — it's the web's core security model (the same rule that stops any site from filling forms on a user's banking site).

The only three technical exceptions, and why each fails:
- **A browser extension** on the prospect's device could fill the form — a non-starter for a referral flow (no prospect installs an extension to open an account).
- **Hosting a pre-filled replica of Zerodha's form on our page** — buildable, but it is impersonation (ADR-014), adjacent to auto-submit (guardrail #1), fragile against any Zerodha change, and forbidden. Rejected without testing (§3e).
- **Zerodha offering it themselves** — either a prefill parameter (none exists) or the sanctioned lead-registration API (§5). The API is the real answer: it doesn't prefill the form, it makes the form *unnecessary*.

**Bottom line: prefill is permanently closed unless Zerodha changes their page. Skip-the-form-entirely (the §5 API) is open, pending Zerodha's answer on access.**

## 8. Recommendation

1. **Close the OPEN POC as NO-GO.** Doc 06 §5.3 / Open item 5's "currently believed not possible" is now **verified fact** with evidence. There is no URL format to record because none exists; the current 302 (`c=` + `r=` only) is already everything the page accepts. Recommend the DA update doc 06 (Open item 5 → CLOSED, citing this file) — DA's edit, not mine.
2. **Do not re-enable `LANDING_MODE=page` for prefill's sake.** The trade stands exactly where ADR-032 left it: page mode buys capture-first + Zoho lead + WATI touch at the cost of one extra form; prefill was the only prospect of removing that cost, and it doesn't exist. The `direct`-vs-`page` choice should continue to be made on capture-value grounds alone.
3. **Pursue avenue (d) instead, as a question to Zerodha** (GO-IF): Abhay/PIFS asks the Zerodha RM / partner portal one question — *"As a registered AP, can PIFS get access to the documented lead-registration API for leads captured on our own website?"* If yes, the DA scopes a properly flagged adapter (per §5's gating list). This is the only path that actually removes the double entry — and it would materially strengthen the case for bringing back page mode (or WhatsApp-first capture feeding the same adapter).
4. **Optional, only if page mode returns:** clipboard-assist for the mobile number (§3e) — one line of JS, compliant, marginal value. Not worth doing on its own.
