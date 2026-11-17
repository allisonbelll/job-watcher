(async () => {
  const { $, esc, fmt, fmtDay, daysBetween } = JW;
  const KEY = "jobwatcher.shortlist";
  const PAGE = 150;

  // ----- shortlist in localStorage -----
  function loadStars() {
    try { return new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { return new Set(); }
  }
  const stars = loadStars();
  function saveStars() {
    try { localStorage.setItem(KEY, JSON.stringify([...stars])); } catch { /* private mode */ }
  }

  const state = { scope: "role", q: "", employer: "", location: "", days: "", sort: "new", limit: PAGE };
  let open = [], runDay = "";

  function fill(select, values) {
    select.insertAdjacentHTML("beforeend",
      values.map(([v, n]) => `<option value="${esc(v)}">${esc(v)} (${fmt(n)})</option>`).join(""));
  }

  function filtered() {
    const q = state.q.trim().toLowerCase();
    let lo = -1, hi = Infinity;
    if (state.days) [lo, hi] = state.days.split("-").map(Number);
    const out = open.filter(r =>
      (state.scope === "all" || (state.scope === "role" && r.in_role) || (state.scope === "star" && stars.has(r.posting_id))) &&
      (!q || r.title.toLowerCase().includes(q)) &&
      (!state.employer || r.employer === state.employer) &&
      (!state.location || r.location === state.location) &&
      (!state.days || (r.days_open >= lo && r.days_open <= hi)));
    out.sort((a, b) => {
      const c = a.first_seen.localeCompare(b.first_seen);
      return (state.sort === "new" ? -c : c) || a.employer.localeCompare(b.employer) || a.title.localeCompare(b.title);
    });
    return out;
  }

  function render() {
    const rows = filtered();
    const label = { role: "in my role", all: "in all roles", star: "on my shortlist" }[state.scope];
    $("#count").textContent = `${fmt(rows.length)} open postings ${label}`;
    $("#rows").innerHTML = rows.slice(0, state.limit).map(r => `
      <tr>
        <td><button class="star" data-id="${esc(r.posting_id)}" aria-pressed="${stars.has(r.posting_id)}"
             title="Save to shortlist" aria-label="Save to shortlist">★</button></td>
        <td>${esc(r.title)}${r.in_role ? ' <span class="pill role">my role</span>' : ""}
            <div class="muted small">${esc(r.department || "")}</div></td>
        <td>${esc(r.employer)}</td>
        <td class="hide-sm">${esc(r.location)}</td>
        <td class="num">${fmtDay(r.first_seen)}</td>
        <td class="num hide-sm">${r.first_run ? "≥ " : ""}${r.days_open}</td>
        <td><a class="apply" href="${esc(r.url)}" target="_blank" rel="noopener">Apply →</a></td>
      </tr>`).join("") || `<tr><td colspan="7" class="empty">${
        state.scope === "star" ? "No starred postings yet. Tap ★ on any posting to save it." : "No postings match these filters."}</td></tr>`;
    $("#more").hidden = rows.length <= state.limit;
  }

  // ----- events -----
  document.querySelectorAll("[data-scope]").forEach(b => b.addEventListener("click", () => {
    state.scope = b.dataset.scope; state.limit = PAGE;
    document.querySelectorAll("[data-scope]").forEach(x => x.setAttribute("aria-pressed", x === b));
    render();
  }));
  $("#q").addEventListener("input", e => { state.q = e.target.value; state.limit = PAGE; render(); });
  for (const id of ["employer", "location", "days", "sort"]) {
    $("#" + id).addEventListener("change", e => { state[id] = e.target.value; state.limit = PAGE; render(); });
  }
  $("#more").addEventListener("click", () => { state.limit += PAGE; render(); });
  $("#reset").addEventListener("click", () => {
    Object.assign(state, { q: "", employer: "", location: "", days: "", sort: "new", limit: PAGE });
    for (const id of ["q", "employer", "location", "days"]) $("#" + id).value = "";
    $("#sort").value = "new";
    render();
  });
  $("#rows").addEventListener("click", e => {
    const b = e.target.closest(".star");
    if (!b) return;
    const id = b.dataset.id;
    stars.has(id) ? stars.delete(id) : stars.add(id);
    saveStars();
    if (state.scope === "star") render(); else b.setAttribute("aria-pressed", stars.has(id));
  });

  try {
    const [status, rows] = await Promise.all([JW.loadStatus().catch(() => null), JW.loadHistory()]);
    JW.setNavStatus(status);
    runDay = (status && status.run_date) || JW.lastRunDate(rows);
    open = rows.filter(r => r.status === "open");
    for (const r of open) r.days_open = daysBetween(r.first_seen, runDay);
    fill($("#employer"), JW.countBy(open, "employer").sort((a, b) => a[0].localeCompare(b[0])));
    fill($("#location"), JW.countBy(open.filter(r => r.location), "location").slice(0, 300));
    render();
  } catch (err) {
    JW.showError(err);
  }
})();
