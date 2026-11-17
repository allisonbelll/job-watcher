# Job Watcher: Entry-Level Financial Advising

[![Tests](https://github.com/allisonbelll/job-watcher/actions/workflows/tests.yml/badge.svg)](https://github.com/allisonbelll/job-watcher/actions/workflows/tests.yml)
[![Daily job watch](https://github.com/allisonbelll/job-watcher/actions/workflows/daily.yml/badge.svg)](https://github.com/allisonbelll/job-watcher/actions/workflows/daily.yml)

**Live site:** https://allisonbelll.github.io/job-watcher/

Every day, GitHub Actions runs this tool on its own. It reads the open postings at 26 financial employers from the public JSON
feed of each employer's applicant tracking system and compares them with the history so far. It records what is new and what
is gone, opens a GitHub Issue for the day, and publishes the result to an installable website.

**Role watched:** entry-level financial advising (financial advisor, wealth management associate, client service associate,
financial planner, and similar).

## Build the history from the raw files

```bash
python -m watcher.build
```

This replays every `data/raw/<date>/<source>.json.gz` in date order and rewrites `data/history.csv` and `data/status.json`.
It reads nothing else, so running it twice gives the same file, and a change to a rule (such as the title rule) applies to
every day of the history.

Other commands:

```bash
pip install -r requirements.txt
python -m watcher.run       # the full daily pipeline (fetch, build, status, issue)
python -m pytest -q         # the test suite
python -m watcher.probe     # test which candidate job boards answer with JSON
```

## Sources

| # | Employer | Applicant tracking system | Board | Search term |
|---|---|---|---|---|
| 1 | JPMorgan Chase | Oracle Recruiting Cloud | `jpmc.fa.oraclecloud.com`, site `CX_1001` | **`wealth`** (the board lists about 6,900 postings) |
| 2 | Robinhood | Greenhouse | `robinhood` | – |
| 3 | Betterment | Greenhouse | `betterment` | – |
| 4 | SoFi | Greenhouse | `sofi` | – |
| 5 | Altruist | Greenhouse | `altruist` | – |
| 6 | Addepar | Greenhouse | `addepar1` | – |
| 7 | Carta | Greenhouse | `carta` | – |
| 8 | Bridgewater Associates | Greenhouse | `bridgewater89` | – |
| 9 | AQR Capital Management | Greenhouse | `aqr` | – |
| 10 | Point72 | Greenhouse | `point72` | – |
| 11 | Affirm | Greenhouse | `affirm` | – |
| 12 | Chime | Greenhouse | `chime` | – |
| 13 | Coinbase | Greenhouse | `coinbase` | – |
| 14 | Galaxy Digital | Greenhouse | `galaxydigitalservices` | – |
| 15 | Upstart | Greenhouse | `upstart` | – |
| 16 | Mercury | Greenhouse | `mercury` | – |
| 17 | Brex | Greenhouse | `brex` | – |
| 18 | Jane Street | Greenhouse | `janestreet` | – |
| 19 | DRW | Greenhouse | `drweng` | – |
| 20 | IMC Trading | Greenhouse | `imc` | – |
| 21 | Jump Trading | Greenhouse | `jumptrading` | – |
| 22 | Ramp | Ashby | `ramp` | – |
| 23 | Plaid | Ashby | `plaid` | – |
| 24 | Wealthsimple | Ashby | `wealthsimple` | – |
| 25 | Kalshi | Ashby | `kalshi` | – |
| 26 | Wealthfront | Lever | `wealthfront` | – |

Every board is read as JSON with no login. No page HTML is read. If a board reports more than 5,000 postings, the
fetcher starts over with the source's search term. Only JPMorgan Chase needs one, and its term is `wealth`.

**Employers that were tried and replaced** (see `candidates.json` and the probe workflow):

- Every Workday board, including Fidelity, Wells Fargo, Schwab, Edward Jones, Capital One, Citi, BlackRock, State
  Street, PNC, U.S. Bank, and T. Rowe Price. From GitHub's servers, these answer the first request with HTTP 429 and a
  block page.
- Morgan Stanley (Eightfold) answers HTTP 403.
- Goldman Sachs runs its own careers site rather than a standard tracking system.
- Several SmartRecruiters company boards (Visa, Equitable, Raymond James, AllianceBernstein, Western Union) return
  no postings.

The Workday and SmartRecruiters adapters stay in the code and in the tests, so a board can be added back if it opens up.

## Title rule

A posting is **in my role** (`in_role = true`) when its title matches at least one *include* pattern and no *exclude*
pattern. Matching ignores case (`watcher/rules.py`).

**Include** (any of):
- `financial` followed by `advisor`, `adviser`, `planner`, `consultant`, `professional`, or `representative`
- `investment`, `wealth`, `retirement`, or `client` followed by `advisor` or `adviser`
- `wealth (management) associate`, `analyst`, `planner`, or `planning`
- `associate` or `analyst` anywhere before `wealth`, `private bank`, or `private client`
- `private client`, `private wealth`, or `private bank(ing)` followed by `associate` or `analyst`
- `client (service) associate`
- `financial planning associate`, `analyst`, or `specialist`
- `paraplanner`
- `advisor` or `adviser` followed by `associate`, `trainee`, `development`, or `apprentice`

**Exclude** (entry level only): `senior`, `sr.`, `lead`, `principal`, `director`, `vice president`, `VP`/`AVP`/`SVP`,
`managing`, `head of`, `manager`, `executive`, `chief`, `partner`, `intern`/`internship`.

## How the history is built

For each date folder in `data/raw/`, oldest first, and each source with a raw file that day:

1. The source's adapter converts every posting to the common columns. Every posting is kept, not only the ones in
   the role.
2. `in_role` is set by the title rule.
3. Then the history is updated:
   - A posting seen for the first time gets that day as `first_seen`. It gets `first_run = true` if that day is
     the source's first raw file.
   - Every posting listed that day gets that day as `last_seen` and `status = open`.
   - An open posting of that source that is no longer listed is marked `status = removed` with
     `removed_date` = that day.
   - A removed posting that is listed again reopens: `removed_date` is cleared and `first_seen` stays the same.
   - A source with no raw file that day (it failed) is left alone, so a failed fetch never removes postings.

Rows are sorted by `posting_id` (`<source>:<source's own id>`). Dates are UTC `YYYY-MM-DD`.

## Daily pipeline (`.github/workflows/daily.yml`)

The pipeline runs every day at 12:23 UTC (and on demand).

1. Calls every source and saves its response, gzipped, to `data/raw/<UTC date>/<source>.json.gz`. A source that fails
   writes no raw file, and the run carries on. The result of every source (ok, count, error) goes to
   `data/runs/<date>.json` and into the status file.
2. Rebuilds `data/history.csv` from all raw files.
3. Writes `data/status.json`.
4. Opens a GitHub Issue titled with the date. The issue lists the new and removed postings, each with a link, and
   closes the previous day's issue. On a quiet day the issue still opens and says "None today." If the lists are
   longer than one issue body allows, the rest goes into comments.
5. Commits the raw files, the history, the status, and the run record.

A second run on the same day deletes that day's raw folder first, rebuilds, and edits the same issue, so each day
counts once.

## Files

| Path | What it does |
|---|---|
| `README.md` | This file. |
| `requirements.txt` | Python dependencies (`requests`, `pytest`). |
| `sources.json` | The watch list: the 26 employers, their applicant tracking system, their board, and their search term. |
| `candidates.json` | Every employer tried by the probe, including the ones that were replaced. |
| `watcher/__init__.py` | Marks the package. |
| `watcher/ats.py` | Adapters for each applicant tracking system (Oracle, Greenhouse, Ashby, Lever, Workday, Eightfold, SmartRecruiters). Each adapter fetches the board's JSON (with paging and the 5,000-posting search rule) and converts a raw file to the common columns. |
| `watcher/rules.py` | The title rule (`in_role`). |
| `watcher/build.py` | Builds `data/history.csv` and `data/status.json` from the raw files alone. |
| `watcher/run.py` | The daily pipeline: fetch every source, write raw files and the run record, build, and publish the issue. |
| `watcher/issue.py` | Opens or updates today's GitHub Issue and closes earlier ones. |
| `watcher/probe.py` | Tests candidate boards and reports which return JSON (used to choose `sources.json`). |
| `watcher/diag.py` | A quick one-request-per-board check of Workday boards. |
| `tests/test_normalize.py` | Converting each applicant tracking system's response to the common columns. |
| `tests/test_rules.py` | The title rule: titles in and out of the role. |
| `tests/test_build.py` | First-seen, last-seen, removed, reopened, and first-run logic; a failed source; same-day reruns; reproducible builds; status counts. |
| `tests/test_issue.py` | Issue body: new and removed lists with links, quiet days, and splitting long lists. |
| `tests/__init__.py` | Marks the test package. |
| `.github/workflows/daily.yml` | Runs the pipeline every day and commits the data. |
| `.github/workflows/tests.yml` | Runs pytest on every push (the badge above). |
| `.github/workflows/probe.yml` | Runs the probe or diagnostic by hand. |
| `data/raw/<date>/<source>.json.gz` | What each board returned that day, compressed. |
| `data/runs/<date>.json` | The result of every source in that day's run. |
| `data/history.csv` | One row per posting with the columns listed below. |
| `data/status.json` | The latest run: `run_time`, `first_run_date`, `days_with_success`, `open`, `new_today`, `removed_today`, and `sources` (`name`, `ok`, `count`). |
| `index.html` | **Today** page: last run time, source status, the four counts, and new and removed postings. |
| `browse.html` | **Browse** page: open postings, a My role / All switch, employer, location, and days-open filters, title search, sort by first seen, apply links, and a ★ shortlist saved in the browser. |
| `market.html` | **Market** page: six findings computed in the browser from `history.csv`. |
| `assets/style.css` | The one set of fonts and colors and the shared navigation bar. |
| `assets/common.js` | Shared code: data loading, CSV parser, date helpers, SVG charts, and service worker registration. |
| `assets/today.js`, `assets/browse.js`, `assets/market.js` | The code for each page. |
| `manifest.webmanifest` | Web app manifest, so the site installs as an app. |
| `sw.js` | Service worker. It tries the network first and falls back to the cache, so the site opens offline with the last data it loaded. |
| `icons/icon-192.png`, `icons/icon-512.png` | App icons. |
| `.gitignore` | Ignores Python caches and the probe output. |

`history.csv` columns: `posting_id, source, source_id, employer, title, location, department, posted_date, url, in_role,
first_run, first_seen, last_seen, status, removed_date`. Columns a source does not provide stay empty. For example,
Greenhouse's list feed has no department.

## Market page definitions

1. **New postings per day:** rows with `first_seen` equal to that day and `first_run = false`, for all postings and
   for my role.
2. **Removed postings per day:** rows with `removed_date` equal to that day.
3. **Open postings per employer:** rows with `status = open`, counted by employer.
4. **Days open:** for removed rows with `first_run = false`, `removed_date − first_seen`. The page reports the median.
5. **Share removed within seven days:** among rows with `first_run = false` and `first_seen` at least 7 days before
   the last run, the share with `removed_date − first_seen ≤ 7`.
6. **Top locations:** open rows counted by location (top 15).
