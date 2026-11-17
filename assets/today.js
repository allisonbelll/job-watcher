(async () => {
  const { $, esc, fmt, fmtTime, fmtDay, postingItem } = JW;
  const SHOW = 60;

  function list(el, rows, countEl) {
    countEl.textContent = `(${fmt(rows.length)})`;
    if (!rows.length) { el.innerHTML = '<li class="empty">None in the latest run.</li>'; return; }
    rows.sort((a, b) => (b.in_role - a.in_role) || a.employer.localeCompare(b.employer) || a.title.localeCompare(b.title));
    el.innerHTML = rows.slice(0, SHOW).map(postingItem).join("") +
      (rows.length > SHOW ? `<li class="muted small">…and ${fmt(rows.length - SHOW)} more. See the daily GitHub Issue for the full list.</li>` : "");
  }

  try {
    const [status, rows] = await Promise.all([JW.loadStatus(), JW.loadHistory()]);
    JW.setNavStatus(status);
    const day = status.run_date || JW.lastRunDate(rows);

    $("#run-time").textContent = `${fmtTime(status.run_time)} (UTC date ${day})`;
    $("#t-days").textContent = fmt(status.days_with_success);
    $("#t-days-note").textContent = status.first_run_date ? `since ${fmtDay(status.first_run_date)}` : "";
    $("#t-open").textContent = fmt(status.open);
    $("#t-open-note").textContent = `${fmt(rows.filter(r => r.status === "open" && r.in_role).length)} in my role`;

    const fresh = rows.filter(r => r.first_seen === day && !r.first_run);
    const gone = rows.filter(r => r.removed_date === day);
    $("#t-new").textContent = fmt(status.new_today);
    $("#t-new-note").textContent = `${fmt(fresh.filter(r => r.in_role).length)} in my role`;
    $("#t-removed").textContent = fmt(status.removed_today);
    $("#t-removed-note").textContent = `${fmt(gone.filter(r => r.in_role).length)} in my role`;

    list($("#new-list"), fresh, $("#new-count"));
    list($("#removed-list"), gone, $("#removed-count"));

    $("#sources").innerHTML = (status.sources || []).map(s => `
      <tr>
        <td>${esc(s.employer || s.name)}</td>
        <td class="hide-sm muted">${esc(s.ats || "")}</td>
        <td>${s.ok ? '<span class="pill ok">OK</span>' : '<span class="pill fail">Failed</span>'}</td>
        <td class="num">${s.ok ? fmt(s.count) : "–"}</td>
        <td class="hide-sm muted small">${esc(s.ok ? (s.search_term ? `search: “${s.search_term}”` : "") : s.error || "")}</td>
      </tr>`).join("") || '<tr><td colspan="5" class="empty">No run yet.</td></tr>';
  } catch (err) {
    JW.showError(err);
  }
})();
