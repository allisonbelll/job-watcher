"""First-seen, last-seen, removed and reopened logic, built from raw files."""

import csv
import io
import json

import pytest

from watcher import build
from watcher.run import write_raw

GH = {"name": "gh", "employer": "Green Co", "ats": "greenhouse", "board": "green"}
LV = {"name": "lv", "employer": "Lever Co", "ats": "lever", "board": "lev"}


def gh_raw(*ids):
    return {"pages": [{"jobs": [
        {"id": i, "title": f"Financial Advisor {i}", "location": {"name": "Remote"},
         "absolute_url": f"https://x/{i}"} for i in ids]}]}


def lv_raw(*ids):
    return {"pages": [[{"id": i, "text": f"Engineer {i}", "hostedUrl": f"https://y/{i}",
                        "categories": {}} for i in ids]]}


@pytest.fixture
def data(tmp_path):
    return tmp_path


def put(data, day, source, raw):
    write_raw(data / "raw" / day / f"{source['name']}.json.gz", source, raw, f"{day}T12:00:00Z")


def by_id(rows):
    return {r["posting_id"]: r for r in rows}


def test_first_seen_last_seen_and_first_run(data):
    put(data, "2026-11-01", GH, gh_raw(1, 2))
    put(data, "2026-11-02", GH, gh_raw(1, 2, 3))
    h = by_id(build.build_history(data / "raw"))
    assert h["gh:1"]["first_seen"] == "2026-11-01" and h["gh:1"]["first_run"] is True
    assert h["gh:1"]["last_seen"] == "2026-11-02"
    assert h["gh:3"]["first_seen"] == "2026-11-02" and h["gh:3"]["first_run"] is False
    assert all(r["status"] == "open" and r["removed_date"] == "" for r in h.values())


def test_removed_when_source_no_longer_lists_it(data):
    put(data, "2026-11-01", GH, gh_raw(1, 2))
    put(data, "2026-11-02", GH, gh_raw(1))
    h = by_id(build.build_history(data / "raw"))
    assert h["gh:2"]["status"] == "removed"
    assert h["gh:2"]["removed_date"] == "2026-11-02"
    assert h["gh:2"]["last_seen"] == "2026-11-01"


def test_missing_raw_file_does_not_remove(data):
    put(data, "2026-11-01", GH, gh_raw(1))
    put(data, "2026-11-01", LV, lv_raw("a"))
    put(data, "2026-11-02", LV, lv_raw("a"))      # GH failed on 11-02: no raw file
    put(data, "2026-11-03", GH, gh_raw(1))
    h = by_id(build.build_history(data / "raw"))
    assert h["gh:1"]["status"] == "open"
    assert h["gh:1"]["last_seen"] == "2026-11-03"


def test_reopened_keeps_first_seen(data):
    put(data, "2026-11-01", GH, gh_raw(1))
    put(data, "2026-11-02", GH, gh_raw(2))
    put(data, "2026-11-03", GH, gh_raw(1, 2))
    r = by_id(build.build_history(data / "raw"))["gh:1"]
    assert r["status"] == "open"
    assert r["removed_date"] == ""
    assert r["first_seen"] == "2026-11-01"
    assert r["last_seen"] == "2026-11-03"


def test_first_run_is_per_source(data):
    put(data, "2026-11-01", GH, gh_raw(1))
    put(data, "2026-11-02", LV, lv_raw("a"))      # LV's first file is on day 2
    put(data, "2026-11-03", LV, lv_raw("a", "b"))
    h = by_id(build.build_history(data / "raw"))
    assert h["lv:a"]["first_run"] is True
    assert h["lv:b"]["first_run"] is False


def test_in_role_and_sorted_columns(data):
    put(data, "2026-11-01", LV, lv_raw("b", "a"))
    put(data, "2026-11-01", GH, gh_raw(10, 9))
    rows = build.build_history(data / "raw")
    assert [r["posting_id"] for r in rows] == sorted(r["posting_id"] for r in rows)
    assert by_id(rows)["gh:9"]["in_role"] is True
    assert by_id(rows)["lv:a"]["in_role"] is False
    text = build.history_csv(rows)
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == build.COLUMNS
    first = next(reader)
    assert first["in_role"] in ("true", "false") and first["first_run"] in ("true", "false")


def test_build_is_reproducible(data):
    put(data, "2026-11-01", GH, gh_raw(1, 2))
    put(data, "2026-11-02", GH, gh_raw(2, 3))
    build.main(data)
    first = (data / "history.csv").read_text()
    build.main(data)
    assert (data / "history.csv").read_text() == first


def test_status_counts(data):
    put(data, "2026-11-01", GH, gh_raw(1, 2))
    put(data, "2026-11-02", GH, gh_raw(2, 3, 4))
    (data / "runs").mkdir()
    (data / "runs" / "2026-11-02.json").write_text(json.dumps({
        "date": "2026-11-02", "run_time": "2026-11-02T12:00:00Z",
        "sources": [{"name": "gh", "ok": True, "count": 3}]}))
    build.main(data)
    st = json.loads((data / "status.json").read_text())
    assert st["first_run_date"] == "2026-11-01"
    assert st["days_with_success"] == 2
    assert (st["open"], st["new_today"], st["removed_today"]) == (3, 2, 1)
    assert st["sources"] == [{"name": "gh", "ok": True, "count": 3}]


def test_failing_source_does_not_stop_run(data, monkeypatch):
    from watcher import run, ats

    def fake_fetch(source, session):
        if source["name"] == "gh":
            raise ats.SourceError("HTTP 403")
        return lv_raw("a")

    monkeypatch.setattr(ats, "fetch", fake_fetch)
    results = run.fetch_all([GH, LV], "2026-11-05", data, session=object())
    assert [r["ok"] for r in results] == [False, True]
    assert not (data / "raw" / "2026-11-05" / "gh.json.gz").exists()
    assert (data / "raw" / "2026-11-05" / "lv.json.gz").exists()


def test_second_run_same_day_replaces_files(data, monkeypatch):
    from watcher import run, ats
    put(data, "2026-11-05", GH, gh_raw(1))
    monkeypatch.setattr(ats, "fetch", lambda s, session: lv_raw("a"))
    run.fetch_all([LV], "2026-11-05", data, session=object())
    files = sorted(p.name for p in (data / "raw" / "2026-11-05").iterdir())
    assert files == ["lv.json.gz"]
