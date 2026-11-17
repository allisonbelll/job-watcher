from watcher import issue


def row(pid, **kw):
    r = {"posting_id": pid, "title": "Financial Advisor", "url": f"https://x/{pid}",
         "employer": "Acme", "location": "Dallas", "in_role": True,
         "first_seen": "2026-11-01", "first_run": False, "removed_date": ""}
    r.update(kw)
    return r


def test_issue_lists_new_and_removed_with_links():
    rows = [row("a:1", first_seen="2026-11-02"), row("a:2", removed_date="2026-11-02"),
            row("a:3", first_seen="2026-11-02", first_run=True)]
    (body,) = issue.render(rows, "2026-11-02", [{"name": "a", "ok": True}])
    assert "**1 new** and **1 removed**" in body
    assert "(https://x/a:1)" in body and "(https://x/a:2)" in body
    assert "https://x/a:3" not in body          # first-run postings are not "new"


def test_issue_on_quiet_day_still_has_body():
    (body,) = issue.render([], "2026-11-02", [])
    assert body.count("_None today._") == 2


def test_long_issue_splits_into_comments():
    rows = [row(f"a:{i}", first_seen="2026-11-02", title="x" * 200) for i in range(800)]
    chunks = issue.render(rows, "2026-11-02", [])
    assert len(chunks) > 1
    assert all(len(c) <= issue.BODY_LIMIT + 300 for c in chunks)
    assert all(c.startswith("_(continued)_") for c in chunks[1:])
