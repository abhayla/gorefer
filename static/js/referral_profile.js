/* Referral Profile — Clicks tab (client-side filter/sort/tab-switch).
   Data + column config are server-rendered as JSON (json_script), so no copy or
   column set is hardcoded here (config-over-code). Bot rows are dimmed and excluded
   from the header counts (already excluded from totals server-side). */
(function () {
  var clicks = JSON.parse(document.getElementById("gr-clicks").textContent || "[]");
  var cCols = JSON.parse(document.getElementById("gr-ccols").textContent || "[]");
  var cSort = { k: null, dir: 1 };
  var filt = "all";

  function fmtTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    var mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var hh = d.getHours(), mm = ("0" + d.getMinutes()).slice(-2);
    return ("0" + d.getDate()).slice(-2) + " " + mon[d.getMonth()] + " " +
      ("0" + hh).slice(-2) + ":" + mm;
  }

  function head() {
    var el = document.getElementById("chead");
    el.innerHTML = "";
    cCols.forEach(function (col) {
      var k = col[0], label = col[1];
      var th = document.createElement("th");
      th.className = "py-2 px-3 font-semibold sortable";
      var arrow = cSort.k === k ? (cSort.dir > 0 ? " ▲" : " ▼") : "";
      th.innerHTML = label + '<span class="text-cobalt-600">' + arrow + "</span>";
      th.onclick = function () {
        if (cSort.k === k) cSort.dir *= -1;
        else { cSort.k = k; cSort.dir = 1; }
        render();
      };
      el.appendChild(th);
    });
  }

  function sortRows(rows) {
    if (!cSort.k) return rows;
    return rows.slice().sort(function (a, b) {
      var x = a[cSort.k], y = b[cSort.k];
      if (typeof x === "boolean") { x = x ? 1 : 0; y = y ? 1 : 0; }
      return (x > y ? 1 : x < y ? -1 : 0) * cSort.dir;
    });
  }

  function render() {
    head();
    var q = (document.getElementById("q").value || "").toLowerCase();
    var rows = clicks.filter(function (c) {
      if (filt === "human" && (c.bot || c.synthetic)) return false;
      if (filt === "bot" && !c.bot) return false;
      if ((filt === "Mobile" || filt === "Desktop") && c.device !== filt) return false;
      if (filt === "WhatsApp" && c.channel !== "WhatsApp") return false;
      if (q && !((c.city || "").toLowerCase().indexOf(q) >= 0 ||
                 (c.ip || "").toLowerCase().indexOf(q) >= 0)) return false;
      return true;
    });
    rows = sortRows(rows);
    var b = document.getElementById("cbody");
    b.innerHTML = "";
    rows.forEach(function (c) {
      var tr = document.createElement("tr");
      tr.className = "hover:bg-cobalt-50/40 " + ((c.bot || c.synthetic) ? "opacity-50" : "");
      var traffic = c.bot
        ? '<span class="text-rose-500">Bot</span>'
        : (c.synthetic
          ? '<span class="text-ink-300">Synthetic</span>'
          : '<span class="text-positive">Human</span>');
      tr.innerHTML =
        '<td class="py-1.5 px-3 whitespace-nowrap text-ink-700">' + fmtTime(c.t) + "</td>" +
        '<td class="py-1.5 px-3">' + c.partner + "</td>" +
        '<td class="py-1.5 px-3">' + c.channel + "</td>" +
        '<td class="py-1.5 px-3">' + c.city + "</td>" +
        '<td class="py-1.5 px-3 text-ink-500">' + c.region + "</td>" +
        '<td class="py-1.5 px-3 text-ink-500">' + c.country + "</td>" +
        '<td class="py-1.5 px-3 font-mono text-[11px] text-ink-500">' + c.ip + "</td>" +
        '<td class="py-1.5 px-3">' + c.device + "</td>" +
        '<td class="py-1.5 px-3 text-ink-500 whitespace-nowrap">' + c.ua + "</td>" +
        '<td class="py-1.5 px-3">' + traffic + "</td>" +
        '<td class="py-1.5 px-3 ' + (c.outcome_class || "") + '">' + c.outcome +
        (c.self_click
          ? ' <span class="text-[10px] font-semibold text-rose-500" title="Click and lead mobile both match the referrer\'s own on-file mobile">SELF-CLICK</span>'
          : "") + "</td>";
      b.appendChild(tr);
    });
    document.getElementById("clicksEmpty").classList.toggle("hidden", rows.length !== 0);
  }

  window.grRenderC = render;

  window.grTab = function (w) {
    var c = w === "c";
    document.getElementById("clicksWrap").classList.toggle("hidden", !c);
    document.getElementById("cf").classList.toggle("hidden", !c);
    document.getElementById("peopleWrap").classList.toggle("hidden", c);
    document.getElementById("tc").className =
      "px-4 py-2 rounded-full text-[12.5px] font-semibold " +
      (c ? "bg-cobalt-600 text-white" : "text-ink-500 hover:bg-cobalt-50");
    document.getElementById("tp").className =
      "px-4 py-2 rounded-full text-[12.5px] font-semibold " +
      (!c ? "bg-cobalt-600 text-white" : "text-ink-500 hover:bg-cobalt-50");
  };

  document.querySelectorAll(".chip").forEach(function (ch) {
    ch.onclick = function () {
      document.querySelectorAll(".chip").forEach(function (x) { x.classList.remove("chip-on"); });
      ch.classList.add("chip-on");
      filt = ch.dataset.k;
      render();
    };
  });

  render();
})();
