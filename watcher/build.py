"""Build data/history.csv (and data/status.json) from the raw files alone.

    python -m watcher.build

reads every data/raw/<date>/<source>.json.gz in date order and replays the
history from scratch, so running it twice gives the same file and a change
to a rule (for example the title rule) applies to every day.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import ats
from .rules import in_role

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

COLUMNS = [
    "posting_id", "source", "source_id", "employer", "title", "location",
    "department", "posted_date", "url", "in_role", "first_run",
    "first_seen", "last_seen", "status", "removed_date",
]

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def raw_days(raw_dir: Path) -> list[str]:
    """Dates (sorted) that have at least one raw file."""
    if not raw_dir.exists():
        return []
    return sorted(
        d.name for d in raw_dir.iterdir()
        if d.is_dir() and _DAY.match(d.name) and any(d.glob("*.json.gz"))
    )


def read_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def rows_for_day(raw_dir: Path, day: str) -> dict[str, list[dict]]:
    """{source name: [common rows]} for every raw file of one day."""
    out = {}
    for path in sorted((raw_dir / day).glob("*.json.gz")):
        raw = read_raw(path)
        source = raw["source"]
        out[source["name"]] = ats.normalize(source, raw["response"], day)
    return out


def posting_id(source: str, source_id: str) -> str:
    return f"{source}:{source_id}"


def apply_day(history: dict, first_day: dict, day: str, day_rows: dict[str, list[dict]]) -> None:
    """Update the history in place with one day of rows.

    * first time seen  -> first_seen = day (first_run if it is the source's first raw file)
    * listed today     -> last_seen = day, status open, removed_date cleared
    * open, its source has a file today, not listed -> removed with removed_date = day
    Sources without a raw file today are left alone.
    """
    for source, rows in day_rows.items():
        first_day.setdefault(source, day)
        listed = set()
        for r in rows:
            pid = posting_id(source, r["source_id"])
            listed.add(pid)
            rec = history.get(pid)
            if rec is None:
                rec = {
                    "posting_id": pid,
                    "first_seen": day,
                    "first_run": day == first_day[source],
                }
                history[pid] = rec
            rec.update({k: r[k] for k in ats.COMMON_KEYS})
            rec["in_role"] = in_role(r["title"])
            rec["last_seen"] = day
            rec["status"] = "open"
            rec["removed_date"] = ""
        for pid, rec in history.items():
            if rec["source"] == source and rec["status"] == "open" and pid not in listed:
                rec["status"] = "removed"
                rec["removed_date"] = day


def build_history(raw_dir: Path) -> list[dict]:
    history: dict[str, dict] = {}
    first_day: dict[str, str] = {}
    for day in raw_days(raw_dir):
        apply_day(history, first_day, day, rows_for_day(raw_dir, day))
    return [history[k] for k in sorted(history)]


def _fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def history_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: _fmt(r.get(c, "")) for c in COLUMNS})
    return buf.getvalue()


def build_status(rows: list[dict], raw_dir: Path, run: dict | None) -> dict:
    days = raw_days(raw_dir)
    latest = (run or {}).get("date") or (days[-1] if days else "")
    return {
        "run_time": (run or {}).get("run_time") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_date": latest,
        "first_run_date": days[0] if days else None,
        "days_with_success": len(days),
        "open": sum(r["status"] == "open" for r in rows),
        "open_in_role": sum(r["status"] == "open" and r["in_role"] for r in rows),
        "new_today": sum(r["first_seen"] == latest and not r["first_run"] for r in rows),
        "removed_today": sum(r["removed_date"] == latest for r in rows),
        "sources": (run or {}).get("sources", []),
    }


def latest_run(data_dir: Path) -> dict | None:
    runs = sorted((data_dir / "runs").glob("*.json"))
    return json.loads(runs[-1].read_text()) if runs else None


def main(data_dir: Path = DATA) -> list[dict]:
    raw_dir = data_dir / "raw"
    rows = build_history(raw_dir)
    (data_dir / "history.csv").write_text(history_csv(rows), encoding="utf-8")
    status = build_status(rows, raw_dir, latest_run(data_dir))
    (data_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"history.csv: {len(rows)} postings, {status['open']} open "
          f"({status['new_today']} new, {status['removed_today']} removed on {status['run_date']})")
    return rows


if __name__ == "__main__":
    main()
