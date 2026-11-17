"""Test which candidate job boards answer with JSON, without login.

    python -m watcher.probe            # reads candidates.json

Prints a Markdown table (also appended to the GitHub Actions job summary)
and writes probe_results.json with a ready-to-use source entry for each
board that worked.  Only the first page of each board is requested.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

from . import ats

ROOT = Path(__file__).resolve().parent.parent
WD_PODS = ["wd1", "wd5", "wd12", "wd3"]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def first_page(src: dict, s: requests.Session) -> int:
    """Return the board's total postings, or raise."""
    a = src["ats"]
    if a == "workday":
        url = f"https://{src['host']}/wday/cxs/{src['tenant']}/{src['site']}/jobs"
        d = ats._post(s, url, {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
        if "jobPostings" not in d:
            raise ats.SourceError("no jobPostings key")
        return int(d.get("total") or 0)
    if a == "oracle":
        url = (f"{src['base']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
               f"&finder=findReqs;siteNumber={src['site']},limit=5,offset=0")
        return int(ats._get(s, url)["items"][0].get("TotalJobsCount") or 0)
    if a == "eightfold":
        url = f"https://{src['host']}/api/apply/v2/jobs?domain={src['domain']}&start=0&num=10"
        return int(ats._get(s, url).get("count") or 0)
    if a == "greenhouse":
        return len(ats._get(s, f"https://boards-api.greenhouse.io/v1/boards/{src['board']}/jobs").get("jobs") or [])
    if a == "lever":
        return len(ats._get(s, f"https://api.lever.co/v0/postings/{src['board']}?mode=json"))
    if a == "ashby":
        return len(ats._get(s, f"https://api.ashbyhq.com/posting-api/job-board/{src['board']}").get("jobs") or [])
    if a == "smartrecruiters":
        url = f"https://api.smartrecruiters.com/v1/companies/{src['board']}/postings?limit=1"
        return int(ats._get(s, url).get("totalFound") or 0)
    raise ValueError(a)


def expand(c: dict):
    if c["ats"] != "workday":
        yield dict(c)
        return
    for site in c["sites"]:
        for pod in WD_PODS:
            yield {"employer": c["employer"], "ats": "workday",
                   "host": f"{c['tenant']}.{pod}.myworkdayjobs.com", "tenant": c["tenant"], "site": site}


def main() -> None:
    cands = json.loads((ROOT / "candidates.json").read_text())["candidates"]
    s = requests.Session()
    lines = ["| Employer | ATS | Board | Result | Postings |", "|---|---|---|---|---|"]
    working = []
    done = set()
    for c in cands:
        if c["employer"] in done:
            continue
        last_err = ""
        attempts = []
        for src in expand(c):
            time.sleep(1.5 if src["ats"] == "workday" else 0.3)
            board = src.get("host") or src.get("base") or src.get("board")
            if src["ats"] == "workday":
                board = f"{src['host']}/{src['site']}"
            try:
                total = first_page(src, s)
            except Exception as exc:
                last_err = str(exc)[:80]
                code = re.search(r"HTTP (\d+)", str(exc))
                attempts.append(f"{board}:{code.group(1) if code else 'err'}")
                if code and code.group(1) == "429":
                    time.sleep(20)
                continue
            src["name"] = slug(c["employer"])
            if total > ats.MAX_POSTINGS:
                src["search"] = "advisor"
            working.append(src)
            done.add(c["employer"])
            lines.append(f"| {c['employer']} | {src['ats']} | `{board}` | OK | {total} |")
            break
        else:
            lines.append(f"| {c['employer']} | {c['ats']} | — | FAIL | {' '.join(attempts)[:400]} |")
    table = "\n".join(lines)
    print(table)
    print(f"\n{len(working)} boards work.")
    (ROOT / "probe_results.json").write_text(json.dumps({"sources": working}, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write("## Probe results\n\n" + table + f"\n\n**{len(working)} boards work.**\n")


if __name__ == "__main__":
    main()
