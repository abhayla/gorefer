/* Variant C KPI conversion rings. Renders an SVG progress ring into every
   [data-ring] element from its data-* attributes:
     data-frac    fraction filled 0..1 (already computed server-side)
     data-display centre label text (e.g. "1,284" or "24.4%")
     data-label   small caption under the number
     data-color   stroke colour
   No dependency; safe to run on any page that has [data-ring] nodes. */
(function () {
  function render(el) {
    var frac = Math.max(0, Math.min(parseFloat(el.dataset.frac || "0"), 1));
    var display = el.dataset.display || "";
    var label = el.dataset.label || "";
    var color = el.dataset.color || "#2F5BFF";
    var r = 22, c = 2 * Math.PI * r, off = c * (1 - frac);
    el.innerHTML =
      '<svg width="60" height="60" viewBox="0 0 60 60" role="img" aria-label="' +
      label + " " + display + '">' +
      '<circle cx="30" cy="30" r="' + r + '" fill="none" stroke="#eef2ff" stroke-width="6"/>' +
      '<circle cx="30" cy="30" r="' + r + '" fill="none" stroke="' + color +
      '" stroke-width="6" stroke-linecap="round" stroke-dasharray="' + c +
      '" stroke-dashoffset="' + off + '" transform="rotate(-90 30 30)"/>' +
      '<text x="30" y="34" text-anchor="middle" font-size="13" font-weight="800" fill="#0f1729">' +
      display + "</text></svg>";
  }
  document.querySelectorAll("[data-ring]").forEach(render);
})();
