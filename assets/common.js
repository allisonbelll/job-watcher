/* Shared code for every page: data loading, CSV parsing, helpers, charts, service worker. */

const JW = (() => {
  const DATA = { status: "data/status.json", history: "data/history.csv" };

  // ---------- data ----------
  async function getText(url) {
    // The service worker answers from the network when online and from its
    // cache when offline, so the page always gets the last data it loaded.
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
    return res.text();
  }

  async function loadStatus() {
    return JSON.parse(await getText(DATA.status));
  }

  function parseCSV(text) {
    const rows = [];
    let row = [], field = "", i = 0, q = false;
    while (i < text.length) {
      const c = text[i];
      if (q) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
          q = false; i++; continue;
        }
        field += c; i++; continue;
      }
      if (c === '"') { q = true; i++; continue; }
      if (c === ",") { row.push(field); field = ""; i++; continue; }
      if (c === "\r") { i++; continue; }
      if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
      field += c; i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    const head = rows.shift() || [];
    return rows.filter(r => r.length === head.length).map(r => {
      const o = {};
      head.forEach((h, k) => { o[h] = r[k]; });
      o.in_role = o.in_role === "true";
      o.first_run = o.first_run === "true";
      return o;
    });
  }

  async function loadHistory() {
    return parseCSV(await getText(DATA.history));
  }

  // ---------- dates ----------
  const DAY = 86400000;
  const toMs = d => Date.parse(d + "T00:00:00Z");
  const daysBetween = (a, b) => Math.round((toMs(b) - toMs(a)) / DAY);
  function dayRange(a, b) {
    const out = [];
    for (let t = toMs(a); t <= toMs(b); t += DAY) out.push(new Date(t).toISOString().slice(0, 10));
    return out;
  }
  // The last run date in the history: the latest last_seen or removed_date.
  function lastRunDate(rows) {
    let m = "";
    for (const r of rows) {
      if (r.last_seen > m) m = r.last_seen;
      if (r.removed_date > m) m = r.removed_date;
    }
    return m;
  }
  function fmtDay(d) {
    if (!d) return "";
    return new Date(toMs(d)).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
  }
  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }
  function median(xs) {
    if (!xs.length) return null;
    const s = [...xs].sort((a, b) => a - b), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  function countBy(rows, key) {
    const m = new Map();
    for (const r of rows) { const k = typeof key === "function" ? key(r) : r[key]; m.set(k, (m.get(k) || 0) + 1); }
    return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
  }

  // ---------- DOM ----------
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const $ = (sel, root = document) => root.querySelector(sel);
  const fmt = n => (n ?? 0).toLocaleString();
  const pct = x => (x == null ? "—" : (100 * x).toFixed(1) + "%");

  function postingItem(r) {
    const role = r.in_role ? ' <span class="pill role">my role</span>' : "";
    const loc = r.location ? ` · ${esc(r.location)}` : "";
    return `<li><div><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>${role}
      <div class="meta">${esc(r.employer)}${loc}</div></div></li>`;
  }

  function showError(err) {
    const main = $("main");
    main.insertAdjacentHTML("afterbegin",
      `<div class="card" style="border-color:#e8b4b4"><strong>Could not load the data.</strong>
       <div class="muted small">${esc(err.message || err)}</div></div>`);
  }

  // ---------- charts (plain SVG, no libraries, so they work offline) ----------
  const NS = "http://www.w3.org/2000/svg";
  function niceMax(v) {
    if (v <= 5) return 5;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  // Vertical bars over dates; series = [{name, color, values}] drawn side by side.
  function columnChart(el, labels, series, opts = {}) {
    const W = 860, H = opts.height || 260, L = 44, R = 10, T = 10, B = 34;
    let max = niceMax(Math.max(1, ...series.flatMap(s => s.values)));
    if (max < 40) max = Math.ceil(max / 4) * 4;   // whole-number gridlines
    const iw = W - L - R, ih = H - T - B, n = Math.max(1, labels.length);
    const band = iw / n, gap = Math.min(6, band * 0.2), bw = (band - gap) / series.length;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "chart")}">`;
    for (let k = 0; k <= 4; k++) {
      const v = (max / 4) * k, y = T + ih - (v / max) * ih;
      svg += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="#efe4ee"/>`;
      svg += `<text x="${L - 6}" y="${y + 4}" text-anchor="end">${fmt(Math.round(v))}</text>`;
    }
    const every = Math.ceil(n / 14);
    labels.forEach((lab, i) => {
      series.forEach((s, j) => {
        const v = s.values[i] || 0, h = (v / max) * ih;
        const x = L + i * band + gap / 2 + j * bw;
        svg += `<rect x="${x}" y="${T + ih - h}" width="${Math.max(1, bw - 1)}" height="${h}" rx="2" fill="${s.color}"><title>${esc(s.name)} · ${esc(lab)}: ${fmt(v)}</title></rect>`;
      });
      if (i % every === 0) svg += `<text x="${L + i * band + band / 2}" y="${H - 12}" text-anchor="middle">${esc(opts.fmtLabel ? opts.fmtLabel(lab) : lab)}</text>`;
    });
    svg += "</svg>";
    const legend = series.length > 1
      ? `<div class="legend">${series.map(s => `<span style="--c:${s.color}">${esc(s.name)}</span>`).join("")}</div>` : "";
    el.innerHTML = legend + (labels.length ? svg : '<p class="empty">No data yet.</p>');
  }

  // Horizontal bars for ranked categories: items = [[label, value], ...]
  function barList(el, items, opts = {}) {
    if (!items.length) { el.innerHTML = '<p class="empty">No data yet.</p>'; return; }
    const W = 860, row = 26, L = opts.labelWidth || 230, R = 60, H = items.length * row + 8;
    const max = Math.max(1, ...items.map(d => d[1]));
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "chart")}">`;
    items.forEach(([lab, v], i) => {
      const y = 4 + i * row, w = ((W - L - R) * v) / max;
      const short = String(lab).length > 34 ? String(lab).slice(0, 33) + "…" : lab;
      svg += `<text x="${L - 8}" y="${y + 16}" text-anchor="end">${esc(short)}</text>`;
      svg += `<rect x="${L}" y="${y + 3}" width="${Math.max(1, w)}" height="${row - 8}" rx="3" fill="${opts.color || "#b39ddb"}"><title>${esc(lab)}: ${fmt(v)}</title></rect>`;
      svg += `<text x="${L + w + 6}" y="${y + 16}">${opts.fmtValue ? opts.fmtValue(v) : fmt(v)}</text>`;
    });
    el.innerHTML = svg + "</svg>";
  }

  // ---------- service worker / install ----------
  function registerSW() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(err => console.warn("SW", err));
    }
    const setOnline = () => document.body.classList.toggle("offline", !navigator.onLine);
    window.addEventListener("online", setOnline);
    window.addEventListener("offline", setOnline);
    setOnline();
  }

  function setNavStatus(status) {
    const el = $(".nav-status");
    if (el && status) el.textContent = `Last run ${fmtTime(status.run_time)}`;
  }

  registerSW();

  return {
    loadStatus, loadHistory, parseCSV, daysBetween, dayRange, lastRunDate, fmtDay, fmtTime,
    median, countBy, esc, $, fmt, pct, postingItem, showError, columnChart, barList, setNavStatus,
  };
})();
