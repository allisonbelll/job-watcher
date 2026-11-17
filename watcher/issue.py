"""Daily GitHub Issue: title = UTC date, body = new and removed postings.

Uses the GitHub REST API with the workflow's GITHUB_TOKEN.  A second run on
the same day edits that day's issue instead of opening another.  Every
earlier open issue with the ``daily`` label is closed.  When the lists are
too long for one issue body, the rest goes into comments.
"""

from __future__ import annotations

import os

import requests

API = "https://api.github.com"
LABEL = "daily"
BODY_LIMIT = 60000
SITE_NOTE = "Full lists, filters and charts are on the site."


def _line(r: dict) -> str:
    star = "⭐ " if r["in_role"] else ""
    loc = f" — {r['location']}" if r["location"] else ""
    return f"- {star}[{r['title']}]({r['url']}) · {r['employer']}{loc}"


def render(rows: list[dict], day: str, results: list[dict]) -> list[str]:
    """Return [body, comment, comment, ...] in Markdown."""
    new = sorted((r for r in rows if r["first_seen"] == day and not r["first_run"]),
                 key=lambda r: (not r["in_role"], r["employer"], r["title"]))
    gone = sorted((r for r in rows if r["removed_date"] == day),
                  key=lambda r: (not r["in_role"], r["employer"], r["title"]))
    ok = sum(s["ok"] for s in results)
    failed = [s["name"] for s in results if not s["ok"]]

    head = [
        f"# Job Watcher — {day}",
        "",
        f"**{len(new)} new** and **{len(gone)} removed** postings today "
        f"({sum(r['in_role'] for r in new)} new / {sum(r['in_role'] for r in gone)} removed in my role, marked ⭐).",
        f"Sources OK: {ok}/{len(results)}" + (f" — failed: {', '.join(failed)}" if failed else ""),
        "",
    ]
    lines = head + [f"## New postings ({len(new)})"] + ([_line(r) for r in new] or ["_None today._"])
    lines += ["", f"## Removed postings ({len(gone)})"] + ([_line(r) for r in gone] or ["_None today._"])
    lines += ["", SITE_NOTE]

    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) + 1 > BODY_LIMIT:
            chunks.append(cur)
            cur = "_(continued)_\n"
        cur += ln + "\n"
    chunks.append(cur)
    return chunks


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return s


def _check(resp):
    if resp.status_code >= 300:
        raise RuntimeError(f"GitHub API {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.text else {}


def publish(rows: list[dict], day: str, results: list[dict]) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("No GITHUB_TOKEN/GITHUB_REPOSITORY: skipping the issue (local run).")
        return
    s = _session(token)
    base = f"{API}/repos/{repo}"
    chunks = render(rows, day, results)

    # make sure the label exists (422 = already there)
    s.post(f"{base}/labels", json={"name": LABEL, "color": "1f6feb", "description": "Daily Job Watcher report"})

    open_issues = []
    page = 1
    while True:
        batch = _check(s.get(f"{base}/issues", params={"labels": LABEL, "state": "open",
                                                        "per_page": 100, "page": page}))
        open_issues += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
        page += 1

    today = next((i for i in open_issues if i["title"] == day), None)
    if today is None:
        today = _check(s.post(f"{base}/issues", json={"title": day, "body": chunks[0], "labels": [LABEL]}))
        print(f"Opened issue #{today['number']} {day}")
    else:
        _check(s.patch(f"{base}/issues/{today['number']}", json={"body": chunks[0]}))
        # replace earlier overflow comments from a previous run today
        for c in _check(s.get(f"{base}/issues/{today['number']}/comments", params={"per_page": 100})):
            if c["body"].startswith("_(continued)_"):
                s.delete(f"{base}/issues/comments/{c['id']}")
        print(f"Updated issue #{today['number']} {day}")
    for extra in chunks[1:]:
        _check(s.post(f"{base}/issues/{today['number']}/comments", json={"body": extra}))

    for i in open_issues:
        if i["number"] != today["number"]:
            _check(s.patch(f"{base}/issues/{i['number']}", json={"state": "closed"}))
            print(f"Closed issue #{i['number']} {i['title']}")
