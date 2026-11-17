"""Applicant tracking system (ATS) adapters.

Each adapter has two halves:

* ``fetch_<ats>(source, session)`` calls the employer's public JSON job board
  (no login, no HTML) and returns a dict that is saved, unchanged, as the raw
  file for the day.  Paginated boards keep every page they returned.
* ``normalize_<ats>(source, raw, day)`` turns a raw file into a list of rows in
  the common columns.  The build only ever reads raw files through these
  functions, so the history depends on the raw files alone.

If a board reports more than ``MAX_POSTINGS`` postings, the fetcher starts
over with the source's search term (``search`` in sources.json) and records
the term it used in the raw file.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

MAX_POSTINGS = 5000
TIMEOUT = 30
UA = "job-watcher/1.0 (student project; daily read of public job board JSON)"

COMMON_KEYS = (
    "source", "source_id", "employer", "title", "location",
    "department", "posted_date", "url",
)


class SourceError(RuntimeError):
    """Raised when a board cannot be read; the run records it and moves on."""


def _row(source, source_id, title, location="", department="", posted_date="", url=""):
    return {
        "source": source["name"],
        "source_id": str(source_id).strip(),
        "employer": source["employer"],
        "title": _clean(title),
        "location": _clean(location),
        "department": _clean(department),
        "posted_date": posted_date or "",
        "url": url or "",
    }


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = "; ".join(_clean(v) for v in value if v)
    return re.sub(r"\s+", " ", str(value)).strip()


def _iso_day(value) -> str:
    """Return YYYY-MM-DD (UTC) from an ISO string or epoch seconds/millis."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        secs = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(secs, tz=timezone.utc).date().isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
        return m.group(1) if m else ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def _get(session, url, **kw):
    resp = session.get(url, timeout=TIMEOUT, headers={"User-Agent": UA, "Accept": "application/json"}, **kw)
    if resp.status_code != 200:
        raise SourceError(f"HTTP {resp.status_code} from {url}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError(f"not JSON from {url}") from exc


def _post(session, url, payload):
    resp = session.post(
        url, json=payload, timeout=TIMEOUT,
        headers={"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"},
    )
    if resp.status_code != 200:
        raise SourceError(f"HTTP {resp.status_code} from {url}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError(f"not JSON from {url}") from exc


# --------------------------------------------------------------------------
# Workday  (POST https://<host>/wday/cxs/<tenant>/<site>/jobs)
# --------------------------------------------------------------------------

def _workday_pages(source, session, search_text):
    url = f"https://{source['host']}/wday/cxs/{source['tenant']}/{source['site']}/jobs"
    pages, offset, total, limit = [], 0, None, 20
    while True:
        data = _post(session, url, {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": search_text})
        if total is None:
            total = int(data.get("total") or 0)
            if total > MAX_POSTINGS and not search_text:
                return None, total
        pages.append(data)
        got = len(data.get("jobPostings") or [])
        offset += limit
        if got == 0 or offset >= total or offset >= 10000:
            break
        time.sleep(0.2)
    return pages, total


def fetch_workday(source, session):
    pages, total = _workday_pages(source, session, "")
    term = ""
    if pages is None:
        term = source.get("search") or ""
        if not term:
            raise SourceError(f"{total} postings and no search term configured")
        pages, total = _workday_pages(source, session, term)
    return {"ats": "workday", "search_term": term, "total": total, "pages": pages}


_WD_POSTED = re.compile(r"posted\s+(today|yesterday|(\d+)\s+days?\s+ago)", re.I)


def _workday_posted(posted_on: str, day: str) -> str:
    """Workday gives 'Posted Today', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'.

    The first three become a date relative to the raw file's day; '30+' is
    not a date, so it is left empty.
    """
    m = _WD_POSTED.search(posted_on or "")
    if not m:
        return ""
    base = date.fromisoformat(day)
    word = m.group(1).lower()
    if word == "today":
        n = 0
    elif word == "yesterday":
        n = 1
    else:
        n = int(m.group(2))
    return (base - timedelta(days=n)).isoformat()


def normalize_workday(source, raw, day):
    rows = []
    base = f"https://{source['host']}/en-US/{source['site']}"
    for page in raw.get("pages", []):
        for job in page.get("jobPostings") or []:
            path = job.get("externalPath") or ""
            if not path:
                continue
            tail = path.rsplit("/", 1)[-1]
            sid = tail.rsplit("_", 1)[-1] if "_" in tail else tail
            rows.append(_row(
                source, sid, job.get("title"),
                location=job.get("locationsText"),
                posted_date=_workday_posted(job.get("postedOn", ""), day),
                url=base + path,
            ))
    return rows


# --------------------------------------------------------------------------
# Oracle Recruiting Cloud  (GET <base>/hcmRestApi/resources/latest/recruitingCEJobRequisitions)
# --------------------------------------------------------------------------

def _oracle_pages(source, session, keyword):
    pages, offset, limit, total = [], 0, 100, None
    while True:
        finder = f"findReqs;siteNumber={source['site']},limit={limit},offset={offset},sortBy=POSTING_DATES_DESC"
        if keyword:
            finder += f',keyword="{keyword}"'
        url = (f"{source['base']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
               f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={quote(finder, safe='=;,')}")
        data = _get(session, url)
        items = data.get("items") or [{}]
        block = items[0]
        if total is None:
            total = int(block.get("TotalJobsCount") or 0)
            if total > MAX_POSTINGS and not keyword:
                return None, total
        pages.append(data)
        got = len(block.get("requisitionList") or [])
        offset += limit
        if got == 0 or offset >= total:
            break
        time.sleep(0.2)
    return pages, total


def fetch_oracle(source, session):
    pages, total = _oracle_pages(source, session, "")
    term = ""
    if pages is None:
        term = source.get("search") or ""
        if not term:
            raise SourceError(f"{total} postings and no search term configured")
        pages, total = _oracle_pages(source, session, term)
    return {"ats": "oracle", "search_term": term, "total": total, "pages": pages}


def normalize_oracle(source, raw, day):
    rows = []
    for page in raw.get("pages", []):
        for block in page.get("items") or []:
            for job in block.get("requisitionList") or []:
                jid = job.get("Id")
                if jid in (None, ""):
                    continue
                rows.append(_row(
                    source, jid, job.get("Title"),
                    location=job.get("PrimaryLocation"),
                    department=job.get("Organization") or job.get("JobFamily") or "",
                    posted_date=_iso_day(job.get("PostedDate")),
                    url=f"{source['base']}/hcmUI/CandidateExperience/en/sites/{source['site']}/job/{jid}",
                ))
    return rows


# --------------------------------------------------------------------------
# Eightfold  (GET https://<host>/api/apply/v2/jobs?domain=...)
# --------------------------------------------------------------------------

def _eightfold_pages(source, session, query):
    pages, start, num, total = [], 0, 10, None
    while True:
        url = (f"https://{source['host']}/api/apply/v2/jobs?domain={source['domain']}"
               f"&start={start}&num={num}&sort_by=relevance")
        if query:
            url += f"&query={quote(query)}"
        data = _get(session, url)
        if total is None:
            total = int(data.get("count") or 0)
            if total > MAX_POSTINGS and not query:
                return None, total
        pages.append(data)
        got = len(data.get("positions") or [])
        start += got or num
        if got == 0 or start >= total:
            break
        time.sleep(0.15)
    return pages, total


def fetch_eightfold(source, session):
    pages, total = _eightfold_pages(source, session, "")
    term = ""
    if pages is None:
        term = source.get("search") or ""
        if not term:
            raise SourceError(f"{total} postings and no search term configured")
        pages, total = _eightfold_pages(source, session, term)
    return {"ats": "eightfold", "search_term": term, "total": total, "pages": pages}


def normalize_eightfold(source, raw, day):
    rows = []
    for page in raw.get("pages", []):
        for job in page.get("positions") or []:
            jid = job.get("id")
            if jid in (None, ""):
                continue
            loc = job.get("location") or job.get("locations") or ""
            url = job.get("canonicalPositionUrl") or f"https://{source['host']}/careers/job/{jid}"
            rows.append(_row(
                source, jid, job.get("name"),
                location=loc, department=job.get("department"),
                posted_date=_iso_day(job.get("t_create")), url=url,
            ))
    return rows


# --------------------------------------------------------------------------
# Greenhouse  (GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs)
# --------------------------------------------------------------------------

def fetch_greenhouse(source, session):
    data = _get(session, f"https://boards-api.greenhouse.io/v1/boards/{source['board']}/jobs")
    return {"ats": "greenhouse", "search_term": "", "total": len(data.get("jobs") or []), "pages": [data]}


def normalize_greenhouse(source, raw, day):
    rows = []
    for page in raw.get("pages", []):
        for job in page.get("jobs") or []:
            rows.append(_row(
                source, job.get("id"), job.get("title"),
                location=(job.get("location") or {}).get("name"),
                department="; ".join(d.get("name", "") for d in job.get("departments") or []),
                posted_date=_iso_day(job.get("first_published")),
                url=job.get("absolute_url"),
            ))
    return rows


# --------------------------------------------------------------------------
# Lever  (GET https://api.lever.co/v0/postings/<company>?mode=json)
# --------------------------------------------------------------------------

def fetch_lever(source, session):
    data = _get(session, f"https://api.lever.co/v0/postings/{source['board']}?mode=json")
    if not isinstance(data, list):
        raise SourceError("unexpected Lever response")
    return {"ats": "lever", "search_term": "", "total": len(data), "pages": [data]}


def normalize_lever(source, raw, day):
    rows = []
    for page in raw.get("pages", []):
        for job in page or []:
            cat = job.get("categories") or {}
            rows.append(_row(
                source, job.get("id"), job.get("text"),
                location=cat.get("location") or "; ".join(cat.get("allLocations") or []),
                department=cat.get("department") or cat.get("team"),
                posted_date=_iso_day(job.get("createdAt")),
                url=job.get("hostedUrl"),
            ))
    return rows


# --------------------------------------------------------------------------
# Ashby  (GET https://api.ashbyhq.com/posting-api/job-board/<board>)
# --------------------------------------------------------------------------

def fetch_ashby(source, session):
    data = _get(session, f"https://api.ashbyhq.com/posting-api/job-board/{source['board']}")
    return {"ats": "ashby", "search_term": "", "total": len(data.get("jobs") or []), "pages": [data]}


def normalize_ashby(source, raw, day):
    rows = []
    for page in raw.get("pages", []):
        for job in page.get("jobs") or []:
            rows.append(_row(
                source, job.get("id"), job.get("title"),
                location=job.get("location"),
                department=job.get("department") or job.get("team"),
                posted_date=_iso_day(job.get("publishedAt")),
                url=job.get("jobUrl") or job.get("applyUrl"),
            ))
    return rows


# --------------------------------------------------------------------------
# SmartRecruiters  (GET https://api.smartrecruiters.com/v1/companies/<company>/postings)
# --------------------------------------------------------------------------

def _sr_pages(source, session, q):
    pages, offset, limit, total = [], 0, 100, None
    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{source['board']}/postings?limit={limit}&offset={offset}"
        if q:
            url += f"&q={quote(q)}"
        data = _get(session, url)
        if total is None:
            total = int(data.get("totalFound") or 0)
            if total > MAX_POSTINGS and not q:
                return None, total
        pages.append(data)
        got = len(data.get("content") or [])
        offset += limit
        if got == 0 or offset >= total:
            break
        time.sleep(0.2)
    return pages, total


def fetch_smartrecruiters(source, session):
    pages, total = _sr_pages(source, session, "")
    term = ""
    if pages is None:
        term = source.get("search") or ""
        if not term:
            raise SourceError(f"{total} postings and no search term configured")
        pages, total = _sr_pages(source, session, term)
    return {"ats": "smartrecruiters", "search_term": term, "total": total, "pages": pages}


def normalize_smartrecruiters(source, raw, day):
    rows = []
    for page in raw.get("pages", []):
        for job in page.get("content") or []:
            loc = job.get("location") or {}
            loc_text = loc.get("fullLocation") or ", ".join(
                p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p)
            jid = job.get("id")
            rows.append(_row(
                source, jid, job.get("name"),
                location=loc_text,
                department=(job.get("department") or {}).get("label"),
                posted_date=_iso_day(job.get("releasedDate")),
                url=f"https://jobs.smartrecruiters.com/{source['board']}/{jid}",
            ))
    return rows


FETCHERS = {
    "workday": fetch_workday,
    "oracle": fetch_oracle,
    "eightfold": fetch_eightfold,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
}

NORMALIZERS = {
    "workday": normalize_workday,
    "oracle": normalize_oracle,
    "eightfold": normalize_eightfold,
    "greenhouse": normalize_greenhouse,
    "lever": normalize_lever,
    "ashby": normalize_ashby,
    "smartrecruiters": normalize_smartrecruiters,
}


def fetch(source, session):
    return FETCHERS[source["ats"]](source, session)


def normalize(source, raw, day):
    """Convert one raw file into common rows (de-duplicated by source_id)."""
    rows, seen = [], set()
    for row in NORMALIZERS[source["ats"]](source, raw, day):
        if not row["source_id"] or row["source_id"] in seen:
            continue
        seen.add(row["source_id"])
        rows.append(row)
    return rows
