/* ============================================================================
 * GoRefer — shared.js
 * Reusable PIFS UI components for the customer-facing mockups.
 *
 * WHAT THIS DOES
 *   Injects the shared PIFS header and the shared compliance disclosure/footer
 *   into any page that provides the placeholders:
 *       <div id="gr-header"></div>
 *       <div id="gr-disclosure"></div>
 *
 *   The disclosure block is a COMPLIANCE LOCK (07-UI-UX §9): the SEBI/NSE AP
 *   disclosure + market-risk warning + reward wording are defined ONCE here and
 *   auto-injected, so no page can ship without them.
 *
 * USAGE
 *   1. Add the two placeholders above where you want the header / disclosure.
 *   2. Include this file once, near the end of <body>:
 *          <script src="shared.js"></script>
 *   3. (Optional) Configure per-page before the script tag:
 *          <script>window.GR_CONFIG = { headerSubtitle: '...' };</script>
 *
 * NOTE: Pure vanilla JS, no backend, no localStorage. Mockup only.
 * ==========================================================================*/
(function () {
  'use strict';

  /* ---- Single source of truth for compliance / brand copy ---------------- */
  var GR = {
    entity: 'Passive Income Financial Solutions',
    entityFull: 'Passive Income Financial Solutions Pvt. Ltd.',
    apRegNo: 'AP2516003693',                 // NSE AP registration
    sebiRegNo: 'INZ000031633',               // Zerodha Broking Ltd. SEBI reg.
    // The 10% wording lives in ONE editable field (REFERRAL_INCENTIVE_CLAIM).
    incentiveClaim: '300 reward points + 10% brokerage share',
    riskWarning:
      'Investments in the securities market are subject to market risks; ' +
      'read all the related documents carefully before investing.',
  };

  var CFG = window.GR_CONFIG || {};

  /* ---- Shared PIFS header (branded, NOT Zerodha) ------------------------- */
  function headerHTML() {
    var subtitle = CFG.headerSubtitle ||
      'Authorised Person · NSE AP · Zerodha partner';
    return '' +
    '<header class="bg-pifs-700 text-white px-5 pt-6 pb-7">' +
      '<div class="flex items-center gap-3">' +
        '<div class="h-11 w-11 rounded-xl bg-white/10 ring-1 ring-white/20 flex items-center justify-center">' +
          '<span class="text-xl font-extrabold tracking-tight text-gold">P</span>' +
        '</div>' +
        '<div class="leading-tight">' +
          '<div class="text-base font-bold tracking-tight">' + GR.entity + '</div>' +
          '<div class="text-[11px] text-pifs-100/90 font-medium">' + subtitle + '</div>' +
        '</div>' +
      '</div>' +
    '</header>';
  }

  /* ---- Shared compliance disclosure / footer ---------------------------- *
   * showIncentive: whether the "Referral benefit" panel is shown (hidden on
   *   the partner-direct / invalid-referral fallback where no referral benefit
   *   applies). Defaults to true.
   */
  function disclosureHTML() {
    var showIncentive = CFG.showIncentive !== false;

    var incentiveBlock = showIncentive ? '' +
      '<div class="flex items-center gap-2 mb-2">' +
        '<span class="h-2 w-2 rounded-full bg-gold"></span>' +
        '<span class="text-[11px] font-bold uppercase tracking-wider text-pifs-800/70">Referral benefit</span>' +
      '</div>' +
      '<p class="text-xs font-semibold text-pifs-900 mb-3" data-gr="incentive">' + GR.incentiveClaim + '.</p>' +
      '<div class="border-t border-pifs-200/60 pt-3 space-y-1.5">'
      : '<div class="space-y-1.5">';

    return '' +
    '<section class="px-5 pt-4 pb-6">' +
      '<div class="rounded-xl bg-pifs-100/70 border border-pifs-100 p-4">' +
        incentiveBlock +
          '<p class="text-[10.5px] leading-relaxed text-pifs-800/70">' +
            'Zerodha Broking Ltd.: SEBI Registration no.: <span class="font-semibold">' + GR.sebiRegNo + '</span> | ' +
            GR.entityFull + ' | NSE AP reg. no.: <span class="font-semibold">' + GR.apRegNo + '</span>.' +
          '</p>' +
          '<p class="text-[10.5px] leading-relaxed text-pifs-800/70">' + GR.riskWarning + '</p>' +
        '</div>' +
      '</div>' +
      '<p class="text-center text-[10px] text-pifs-800/40 mt-4">© ' + GR.entityFull + '</p>' +
    '</section>';
  }

  /* ---- Small shared helpers (exposed for pages that want them) ----------- */

  // Indian mobile validation: 10 digits, starts 6-9. Accepts a raw string of
  // digits (the +91 prefix is shown separately in the UI).
  function isValidIndianMobile(raw) {
    var digits = String(raw || '').replace(/\D/g, '');
    return /^[6-9]\d{9}$/.test(digits);
  }

  // Canonical normalization (per CLAUDE.md): strip spaces/+/()/- and prefix 91.
  function normalizeMobile(raw) {
    var digits = String(raw || '').replace(/\D/g, '');
    if (digits.length === 10) digits = '91' + digits;
    return digits;
  }

  /* ---- Inject on DOM ready ----------------------------------------------- */
  function inject() {
    var h = document.getElementById('gr-header');
    if (h) h.innerHTML = headerHTML();
    var d = document.getElementById('gr-disclosure');
    if (d) d.innerHTML = disclosureHTML();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }

  /* ---- Public API -------------------------------------------------------- */
  window.GoRefer = {
    config: GR,
    headerHTML: headerHTML,
    disclosureHTML: disclosureHTML,
    isValidIndianMobile: isValidIndianMobile,
    normalizeMobile: normalizeMobile,
  };
})();
