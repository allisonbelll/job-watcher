/* Market page: all six sections are computed here from history.csv.
   Definitions follow the assignment:
   1 New per day      = rows with first_seen == day and first_run == false (all, and in_role)
   2 Removed per day  = rows with removed_date == day
   3 Open per employer = rows with status == open, counted by employer
   4 Days open        = removed rows, not first_run: removed_date - first_seen (median reported)
   5 Removed within 7 = not first_run and first_seen <= last run - 7 days;
                        share with removed_date - first_seen <= 7
   6 Top locations    = open rows counted by location                                     */
(async () => {
  const { $, esc, fmt, pct, fmtDay, daysBetween, dayRange, median, countBy } = JW;
  const ALL = "#cfdbe6", ROLE = "#7f9cb8";

  function section(id, heading, text) {
    const s = $("#" + id);
    s.querySelector("h2").textContent = heading;
    s.querySelector("p").innerHTML = text;
    return s.querySelector(".chart");
  }
  const plural = (n, w) => `${fmt(n)} ${w}${n === 1 ? "" : "s"}`;

  try {
    const [status, rows] = await Promise.all([JW.loadStatus().catch(() => null), JW.loadHistory()]);
    JW.setNavStatus(status);
    const last = JW.lastRunDate(rows);
    if (!rows.length || !last) throw new Error("The history is empty: no run has finished yet.");
    const first = rows.reduce((m, r) => (r.first_seen < m ? r.first_seen : m), last);
    const days = dayRange(first, last);
    const open = rows.filter(r => r.status === "open");
    $("#intro").insertAdjacentHTML("beforeend",
      ` The history covers <strong>${plural(days.length, "day")}</strong> (${fmtDay(first)} to ${fmtDay(last)})
        and <strong>${fmt(rows.length)}</strong> postings.`);

    // 1. New postings per day
    {
      const fresh = rows.filter(r => !r.first_run);
      const all = days.map(d => fresh.filter(r => r.first_seen === d).length);
      const role = days.map(d => fresh.filter(r => r.first_seen === d && r.in_role).length);
      const tot = all.reduce((a, b) => a + b, 0), totRole = role.reduce((a, b) => a + b, 0);
      const active = days.length > 1 ? days.length - 1 : 1;   // the first day has only first-run postings
      const heading = tot
        ? `Employers add about ${fmt(Math.round(tot / active))} new postings a day; ${fmt(totRole)} so far are in my role`
        : "No new postings yet beyond the first day";
      const el = section("s-new", heading,
        `Postings first seen on each day, leaving out postings that were already open when a board was first read.
         Across ${plural(days.length, "day")} the tool found <strong>${fmt(tot)}</strong> new postings, of which
         <strong>${fmt(totRole)}</strong> (${pct(tot ? totRole / tot : null)}) match the financial advising title rule.`);
      JW.columnChart(el, days, [
        { name: "All postings", color: ALL, values: all },
        { name: "My role", color: ROLE, values: role },
      ], { fmtLabel: fmtDay, label: "New postings per day" });
    }

    // 2. Removed postings per day
    {
      const vals = days.map(d => rows.filter(r => r.removed_date === d).length);
      const tot = vals.reduce((a, b) => a + b, 0);
      const peak = Math.max(0, ...vals), peakDay = days[vals.indexOf(peak)];
      const heading = tot ? `${fmt(tot)} postings have come down, with the most on ${fmtDay(peakDay)} (${fmt(peak)})`
                          : "No postings have been removed yet";
      const el = section("s-removed", heading,
        `Postings whose employer stopped listing them, counted on the day they disappeared. A posting that is
         removed and later listed again counts only on its latest removal date.`);
      JW.columnChart(el, days, [{ name: "Removed", color: "#b9c7a8", values: vals }],
        { fmtLabel: fmtDay, label: "Removed postings per day" });
    }

    // 3. Open postings per employer
    {
      const by = countBy(open, "employer");
      const roleBy = new Map(countBy(open.filter(r => r.in_role), "employer"));
      const [topName, topN] = by[0] || ["—", 0];
      const el = section("s-employer",
        `${topName} has the most open postings (${fmt(topN)} of ${fmt(open.length)})`,
        `Open postings at each employer as of the last run on ${fmtDay(last)}. Bars count every open posting;
         the number in my role is ${fmt(open.filter(r => r.in_role).length)}, led by
         ${esc((countBy(open.filter(r => r.in_role), "employer")[0] || ["no employer"])[0])}.`);
      JW.barList(el, by, {
        label: "Open postings per employer", color: "#9fb6cc",
        fmtValue: v => fmt(v),
      });
      el.insertAdjacentHTML("beforeend", `<p class="muted small">In my role: ${
        by.map(([e]) => `${esc(e)} ${fmt(roleBy.get(e) || 0)}`).join(" · ")}</p>`);
    }

    // 4. Days open (removed, not first-run)
    {
      const spans = rows.filter(r => r.removed_date && !r.first_run).map(r => daysBetween(r.first_seen, r.removed_date));
      const med = median(spans);
      const heading = med == null ? "Not enough removed postings yet to measure how long postings stay open"
                                  : `A posting stays open a median of ${med} day${med === 1 ? "" : "s"}`;
      const el = section("s-days", heading,
        `For ${plural(spans.length, "removed posting")} whose first day the tool saw, the removed date minus the
         first-seen date. Median: <strong>${med == null ? "—" : med + " days"}</strong>.
         The chart shows how many postings closed after each number of days.`);
      const max = spans.length ? Math.max(...spans) : 0;
      const labels = Array.from({ length: max + 1 }, (_, i) => String(i));
      JW.columnChart(el, spans.length ? labels : [], [{ name: "Postings", color: ROLE, values: labels.map(l => spans.filter(s => s === +l).length) }],
        { label: "Days open histogram", fmtLabel: l => l + "d" });
    }

    // 5. Share removed within seven days
    {
      const cohort = rows.filter(r => !r.first_run && daysBetween(r.first_seen, last) >= 7);
      const quick = cohort.filter(r => r.removed_date && daysBetween(r.first_seen, r.removed_date) <= 7);
      const later = cohort.filter(r => r.removed_date && daysBetween(r.first_seen, r.removed_date) > 7);
      const share = cohort.length ? quick.length / cohort.length : null;
      const heading = share == null
        ? "Too early to tell: no new posting has been watched for seven days yet"
        : `${pct(share)} of new postings come down within a week`;
      const el = section("s-share", heading,
        `Among ${plural(cohort.length, "posting")} first seen at least seven days before the last run (and not
         first-run), the share removed seven days or less after it was first seen:
         <span class="big-number">${pct(share)}</span>`);
      JW.barList(el, [
        ["Removed within 7 days", quick.length],
        ["Removed after 7 days", later.length],
        ["Still open", cohort.length - quick.length - later.length],
      ], { label: "Removed within seven days", color: ROLE, labelWidth: 200 });
    }

    // 6. Top locations among open postings
    {
      const locs = countBy(open.filter(r => r.location), "location").slice(0, 15);
      const blank = open.filter(r => !r.location).length;
      const [topLoc, topN] = locs[0] || ["—", 0];
      const el = section("s-locations", `${topLoc} leads open postings with ${fmt(topN)}`,
        `The 15 most common locations among the ${fmt(open.length)} open postings, as each job board writes them${blank ? ` (${fmt(blank)} postings list no location)` : ""}. Workday boards list a posting with several
         sites as “N Locations”.`);
      JW.barList(el, locs, { label: "Top locations", color: "#a9b99a", labelWidth: 260 });
    }
  } catch (err) {
    JW.showError(err);
  }
})();
