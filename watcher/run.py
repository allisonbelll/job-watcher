"""The daily pipeline.  GitHub Actions runs ``python -m watcher.run`` once a day.

1. Call every source in sources.json and save its response, compressed, to
   data/raw/<UTC date>/<source>.json.gz.  A failing source is recorded and
   skipped; it writes no raw file.  A second run on the same day replaces
   that day's raw files.
2. Rebuild data/history.csv from all raw files (watcher.build).
3. Write data/status.json.
4. Open (or update) today's GitHub Issue and close the previous one.
5. Committing is done by the workflow right after this script.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import ats, build, issue

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCES_FILE = ROOT / "sources.json"


def load_sources(path: Path = SOURCES_FILE) -> list[dict]:
    return json.loads(path.read_text())["sources"]


def write_raw(path: Path, source: dict, response: dict, fetched_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": source, "fetched_at": fetched_at, "response": response}
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(payload, fh, separators=(",", ":"), sort_keys=True)


def fetch_all(sources: list[dict], day: str, data_dir: Path, session=None) -> list[dict]:
    session = session or requests.Session()
    day_dir = data_dir / "raw" / day
    if day_dir.exists():          # second run today: start the day over
        shutil.rmtree(day_dir)
    results = []
    for src in sources:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            response = ats.fetch(src, session)
            count = len(ats.normalize(src, response, day))
            write_raw(day_dir / f"{src['name']}.json.gz", src, response, started)
            results.append({"name": src["name"], "employer": src["employer"], "ats": src["ats"],
                            "ok": True, "count": count, "search_term": response.get("search_term", ""),
                            "error": ""})
            print(f"  ok    {src['name']:<24} {count:>6}")
        except Exception as exc:  # one source must never stop the run
            results.append({"name": src["name"], "employer": src["employer"], "ats": src["ats"],
                            "ok": False, "count": 0, "search_term": "",
                            "error": f"{type(exc).__name__}: {exc}"[:300]})
            print(f"  FAIL  {src['name']:<24} {exc}")
    return results


def main() -> int:
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    run_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Job Watcher run {run_time} (UTC date {day})")

    results = fetch_all(load_sources(), day, DATA)
    runs = DATA / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{day}.json").write_text(json.dumps(
        {"date": day, "run_time": run_time, "sources": results}, indent=2) + "\n")

    rows = build.main(DATA)

    try:
        issue.publish(rows, day, results)
    except Exception:
        # The issue is reported but never stops the commit of the day's data.
        traceback.print_exc()
        print("WARNING: could not publish the GitHub Issue")
    ok = sum(r["ok"] for r in results)
    print(f"{ok}/{len(results)} sources ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
