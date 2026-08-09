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

  // Configured share-poster images (T-063) — already same-origin-resolved server-side
  // (apps.accounts.hub.resolve_share_image_url). Empty list when unconfigured.
  var shareImages = [];
  var imagesPayload = document.getElementById("shareImages");
  if (imagesPayload) {
    try { shareImages = JSON.parse(imagesPayload.textContent) || []; } catch (e) { /* none */ }
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
  // Text-only share (today's behaviour) works on any browser with navigator.share.
  // When at least one poster image is configured AND the browser's Web Share API
  // level 2 supports file attachments (navigator.canShare({files})), the sheet
  // carries the image file(s) too. Everything here is feature-detected at runtime —
  // a browser without file support (or without navigator.share at all) gets exactly
  // today's text-only share, never a broken button or a console error.
  function fetchAsFiles(images) {
    return Promise.all(images.map(function (image) {
      return fetch(image.url).then(function (resp) {
        if (!resp.ok) throw new Error("share image fetch failed: " + image.url);
        return resp.blob().then(function (blob) {
          return new File([blob], image.filename, { type: blob.type || "image/png" });
        });
      });
    }));
  }

  function doTextShare(nativeBtn) {
    return navigator.share({ text: message, url: link }).then(
      function () { recordShare(nativeBtn.getAttribute("data-share-channel")); },
      function () { /* user dismissed the sheet — not a share */ }
    );
  }

  var nativeBtn = document.getElementById("nativeShareBtn");
  if (nativeBtn && navigator.share) {
    nativeBtn.hidden = false;
    nativeBtn.addEventListener("click", function () {
      if (!shareImages.length || !navigator.canShare) {
        doTextShare(nativeBtn);
        return;
      }
      fetchAsFiles(shareImages).then(function (files) {
        var filesShare = { files: files, text: message };
        if (navigator.canShare(filesShare)) {
          navigator.share(filesShare).then(
            function () { recordShare(nativeBtn.getAttribute("data-share-channel")); },
            function () { /* user dismissed the sheet — not a share */ }
          );
        } else {
          doTextShare(nativeBtn);
        }
      }).catch(function () {
        // Fetch/File construction failed (offline, CORS, unsupported blob type) —
        // fall back to the text-only sheet rather than leaving the tap dead.
        doTextShare(nativeBtn);
      });
    });
  }
})();
