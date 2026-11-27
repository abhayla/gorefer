# Daily digest v2 — link report template (DRAFT, not submitted to Meta)

**Status:** draft for owner review (2026-11-27). Not on Meta, not on the Wati dashboard.
Per CLAUDE.md §6c the conversation map gets this card FIRST, then Meta, then the map again.

| | |
|---|---|
| Proposed name | `gr_platform_gorefer_link_report_en_2026_11_27` (cascade key `messaging_digest_template_en_v2`) |
| Category | UTILITY (an operator's own account report: no offer, no link, no "earn"). Read `category` back after submitting; Meta may silently re-categorise. |
| Language | en |
| Variables | 21, positional, filled by `apps/campaigns/digest_links.py::build_slots_v2` |
| Buttons / links | none |
| Switch | `messaging_digest_layout` = `v2` once APPROVED; `v1` is the rollback. The v1 template stays untouched (Wati-Project's 21:30 IST report also sends it). |

## Body (fixed text 486 characters; values are capped at 520 so the message stays under 1024)

```
GoRefer daily report 📊 — {{1}}

Hi {{2}}, here is the day's messaging and link report.

*Messaging*
Sent: {{3}} · Delivered: {{4}} · Not delivered: {{5}} · Rate: {{6}}
Not delivered because: {{7}}; {{8}}. Other streams: {{9}}

*Your links*
Open link: {{10}}
Step 2 taps: {{11}}
Referral link: {{12}}
Share link: {{13}}
Disclosure page: {{14}}

*Kite ID pop-ups*
Share pop-up: {{15}}
Who referred you pop-up: {{16}}
IDs typed in: {{17}}

*Results*
Clicks: {{18}} · New referrers: {{19}}
Accounts opened (Zoho): {{20}} · Top referrer: {{21}}

Counts are for the IST day. Clicks and people are approximate.
```

## Meta sample values (one line each — no newline, tab or 4+ spaces in a variable)

| # | Meaning | Sample |
|---|---|---|
| 1 | IST date | 2026-11-26 |
| 2 | Greeting name (`messaging_digest_greeting_name`) | Abhay |
| 3–6 | Zoho send queue: sent, delivered, not delivered, rate | 40 · 31 · 9 · 78% |
| 7 | Failed (+ pending) | failed 6, pending 1 |
| 8 | Suppressed | capped 2, invalid/blocked 0 |
| 9 | Other streams | 0 |
| 10 | `/zerodha/open` + tagged posts, with 7-day average | 12 (7d avg 9) |
| 11 | Step 2 of the one-tap message (`/zerodha/open/wa`) | 4 (7d avg 2.5) |
| 12 | Clicks on any link with a Kite ID, top IDs | 8 (7d avg 5) — XY9876 ×5 · AB1234 ×3 |
| 13 | One-tap shares with / without an ID, top IDs | 4 with ID, 1 without (7d avg 4.1) — XY9876 ×3 · RJ4521 ×1 |
| 14 | `/d/pifs` views | 3 (7d avg 0.4) |
| 15 | Share pop-up | shown 6 (4 people) · ID typed 3 · without ID 1 · wrong ID 2 |
| 16 | "Who referred you?" pop-up | shown 2 (2 people) · ID typed 1 · no ID 1 · wrong ID 0 |
| 17 | IDs typed into either pop-up | XY9876 ×2 · AB1234 ×1 |
| 18 | All human clicks (approx.) | 14 |
| 19 | Referrers whose first-ever click was today | 1 |
| 20 | Accounts opened, by TRUE Zoho opening date | 2 |
| 21 | Top referrer by Zoho credit | XY9876 (2) |
