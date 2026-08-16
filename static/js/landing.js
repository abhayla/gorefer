/* GoRefer landing page JS (M3).
 * - Client-side Indian mobile validation (+91, 10 digits, starts 6-9).
 * - Fires the human-confirmation beacon with the server nonce; on success,
 *   fetches the referrer's first name via the nonce-gated reveal endpoint and
 *   personalizes the greeting (generic until then — #1/#3 enumeration guard).
 * - "Continue to Zerodha": saves the lead FIRST (POST /api/leads) then navigates
 *   to the server-side continue route (which 302s to Zerodha). No raw URL here.
 * - "Share on WhatsApp": records POST /api/share, then the wa.me link opens.
 */
(function () {
  "use strict";
  var GR = window.GR || {};

  function isValidMobile(d) { return /^[6-9]\d{9}$/.test(d); }

  // ---- mobile validation ----
  var input = document.getElementById("mobileInput");
  var wrap = document.getElementById("mobileWrap");
  var msg = document.getElementById("mobileMsg");
  var BASE = "flex rounded-lg border bg-white overflow-hidden transition-colors ";
  var NEUTRAL = "border-line focus-within:ring-2 focus-within:ring-cobalt-500/30 focus-within:border-cobalt-500";
  var VALID = "border-positive ring-2 ring-positive/25";
  var ERROR = "border-danger ring-2 ring-danger/25";

  function evaluate() {
    var digits = input.value.replace(/\D/g, "");
    if (digits !== input.value) input.value = digits;
    if (digits.length === 0) { wrap.className = BASE + NEUTRAL; msg.textContent = ""; return; }
    if (isValidMobile(digits)) {
      wrap.className = BASE + VALID;
      msg.textContent = "Looks good — a valid Indian mobile number.";
      msg.className = "mt-1 text-[11px] font-medium min-h-[15px] text-positive";
      return;
    }
    if (digits.length < 10 && /^[6-9]/.test(digits)) { wrap.className = BASE + NEUTRAL; msg.textContent = ""; return; }
    wrap.className = BASE + ERROR;
    msg.textContent = "Enter a valid 10-digit mobile number starting with 6–9.";
    msg.className = "mt-1 text-[11px] font-medium min-h-[15px] text-danger";
  }
  if (input) { input.addEventListener("input", evaluate); input.addEventListener("blur", evaluate); }

  // ---- human-confirmation beacon + name reveal ----
  function jsonHeaders() { return { "Content-Type": "application/json" }; }

  function fireBeaconAndReveal() {
    if (!GR.nonce) return;
    fetch("/api/click/confirm", {
      method: "POST", headers: jsonHeaders(),
      body: JSON.stringify({ client_id: GR.clientId, nonce: GR.nonce }),
    }).then(function (r) {
      if (!r.ok) return;
      return fetch("/api/click/referrer/" + encodeURIComponent(GR.clientId) + "?nonce=" + encodeURIComponent(GR.nonce));
    }).then(function (r) {
      if (!r || !r.ok) return;
      return r.json();
    }).then(function (data) {
      if (data && data.first_name) {
        var el = document.getElementById("gr-referrer");
        if (el) el.textContent = data.first_name;
      }
    }).catch(function () { /* silent — generic greeting stays */ });
  }

  // ---- Continue to Zerodha: save lead FIRST, then navigate to the 302 route ----
  var continueBtn = document.getElementById("continueBtn");
  var formMsg = document.getElementById("formMsg");
  if (continueBtn) {
    continueBtn.addEventListener("click", function () {
      formMsg.textContent = "";
      var name = (document.getElementById("nameInput").value || "").trim();
      var email = (document.getElementById("emailInput").value || "").trim();
      var mobile = (input.value || "").replace(/\D/g, "");
      var consent = document.getElementById("consentInput").checked;
      if (name.length < 2) { formMsg.textContent = "Please enter your full name."; return; }
      if (!isValidMobile(mobile)) { formMsg.textContent = "Please enter a valid mobile number."; return; }
      if (!consent) { formMsg.textContent = "Please tick consent to continue."; return; }

      continueBtn.disabled = true;
      fetch("/api/leads/", {
        method: "POST", headers: jsonHeaders(),
        body: JSON.stringify({ client_id: GR.clientId, name: name, email: email, mobile: mobile, consent: consent, submitted_by: "friend" }),
      }).then(function (r) {
        if (!r.ok) { continueBtn.disabled = false; formMsg.textContent = "Could not save your details. Please try again."; return null; }
        return r.json();
      }).then(function (data) {
        if (data) window.location.href = data.continue_url || GR.continueUrl;
      }).catch(function () { continueBtn.disabled = false; formMsg.textContent = "Network error. Please try again."; });
    });
  }

  // ---- WhatsApp share: build the wa.me deep link from the form inputs + referral
  //      id at click time, record the share event, then open WhatsApp. Target = the
  //      config-driven WATI business number (never Ashok's personal number). ----
  function buildWhatsappShareUrl() {
    var name = (document.getElementById("nameInput").value || "").trim();
    var email = (document.getElementById("emailInput").value || "").trim();
    var phone = (input.value || "").replace(/\D/g, "");
    // Exact message (DA polish round); empty fields leave the label blank so the
    // prospect can type it in WhatsApp.
    var msg =
      "Hi, I'd like to refer for a Zerodha account. My Referral ID: " + GR.clientId + "\n" +
      "*Here are referral details*\n" +
      "Name: " + name + "\n" +
      "Phone Number: " + phone + "\n" +
      "Email: " + email;
    return "https://wa.me/" + GR.watiNumber + "?text=" + encodeURIComponent(msg);
  }

  var whatsappBtn = document.getElementById("whatsappBtn");
  if (whatsappBtn) {
    whatsappBtn.addEventListener("click", function () {
      // Set the freshest href from the current form state, then let the <a> open it.
      whatsappBtn.setAttribute("href", buildWhatsappShareUrl());
      fetch("/api/share/", {
        method: "POST", headers: jsonHeaders(),
        body: JSON.stringify({ client_id: GR.clientId, channel: "whatsapp" }),
      }).catch(function () { /* non-blocking */ });
    });
  }

  fireBeaconAndReveal();
})();
