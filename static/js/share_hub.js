/* GoRefer share hub (T-053) — GET /hub/{token}.
 *
 * Three jobs, no third-party script and no SDK:
 *   1. every share button tap records a per-channel `share_clicked` event through the
 *      EXISTING POST /api/share (client_id + channel only — no PII, and never the
 *      token from the page URL);
 *   2. "Copy link" puts the referrer's credit link on the clipboard;
 *   3. "More…" opens the OS share sheet via navigator.share, and stays hidden where
 *      that API does not exist (no dead button — Constitution §4).
 *
 * The platform buttons are plain <a href> web intents built server-side. This file
 * never constructs a share URL, so it has no way to leak the access token into one.
 */
(function () {
  "use strict";

  var hub = document.getElementById("shareHub");
  if (!hub) return;

  var clientId = hub.getAttribute("data-client-id") || "";
  var linkEl = document.getElementById("myLink");
  var link = linkEl ? (linkEl.textContent || "").trim() : "";

  var message = link;
  var payload = document.getElementById("shareMessage");
  if (payload) {
    try { message = JSON.parse(payload.textContent) || link; } catch (e) { /* keep link */ }
  }

  function recordShare(channel) {
    if (!clientId || !channel) return;
    fetch("/api/share/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, channel: channel }),
      // Non-blocking on purpose: the tap must open the share sheet even if this
      // request is slow, throttled, or refused.
      keepalive: true,
    }).catch(function () { /* analytics must never block a share */ });
  }

  // ---- platform buttons (anchors; the browser follows the href as usual) ----
  var buttons = hub.querySelectorAll("a[data-share-channel]");
  for (var i = 0; i < buttons.length; i++) {
    (function (el) {
      el.addEventListener("click", function () {
        recordShare(el.getAttribute("data-share-channel"));
      });
    })(buttons[i]);
  }

  // ---- copy ----
  var copyBtn = document.getElementById("copyLinkBtn");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var done = copyBtn.getAttribute("data-done-label") || "Copied";
      var original = copyBtn.textContent;
      function confirmCopy() {
        copyBtn.textContent = done;
        setTimeout(function () { copyBtn.textContent = original; }, 2000);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(confirmCopy, function () { /* ignore */ });
      } else if (linkEl && window.getSelection && document.createRange) {
        // Fallback for browsers without the async clipboard API: select the link so
        // the referrer can copy it with one long-press, rather than getting nothing.
        var range = document.createRange();
        range.selectNodeContents(linkEl);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
      recordShare(copyBtn.getAttribute("data-share-channel"));
    });
  }

  // ---- native share sheet ----
  var nativeBtn = document.getElementById("nativeShareBtn");
  if (nativeBtn && navigator.share) {
    nativeBtn.hidden = false;
    nativeBtn.addEventListener("click", function () {
      navigator.share({ text: message, url: link }).then(
        function () { recordShare(nativeBtn.getAttribute("data-share-channel")); },
        function () { /* user dismissed the sheet — not a share */ }
      );
    });
  }
})();
