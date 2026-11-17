"""Each ATS response converts to the common columns."""

import pytest

from watcher import ats

KEYS = set(ats.COMMON_KEYS)
DAY = "2026-11-17"


def src(**kw):
    base = {"name": "acme", "employer": "Acme Bank"}
    base.update(kw)
    return base


def test_workday():
    s = src(ats="workday", host="acme.wd1.myworkdayjobs.com", tenant="acme", site="Careers")
    raw = {"pages": [{"total": 3, "jobPostings": [
        {"title": "Financial Advisor", "externalPath": "/job/Dallas-TX/Financial-Advisor_R-101",
         "locationsText": "Dallas, TX", "postedOn": "Posted 3 Days Ago", "bulletFields": ["R-101"]},
        {"title": "Teller", "externalPath": "/job/Austin-TX/Teller_R-102",
         "locationsText": "2 Locations", "postedOn": "Posted 30+ Days Ago"},
        {"title": "Duplicate", "externalPath": "/job/Austin-TX/Teller_R-102", "postedOn": "Posted Today"},
    ]}]}
    rows = ats.normalize(s, raw, DAY)
    assert len(rows) == 2                     # duplicate source_id dropped
    assert set(rows[0]) == KEYS
    assert rows[0] == {
        "source": "acme", "source_id": "R-101", "employer": "Acme Bank",
        "title": "Financial Advisor", "location": "Dallas, TX", "department": "",
        "posted_date": "2026-11-14",
        "url": "https://acme.wd1.myworkdayjobs.com/en-US/Careers/job/Dallas-TX/Financial-Advisor_R-101",
    }
    assert rows[1]["posted_date"] == ""       # "30+ days" is not a date


@pytest.mark.parametrize("posted,expected", [
    ("Posted Today", "2026-11-17"), ("Posted Yesterday", "2026-11-16"),
    ("Posted 1 Day Ago", "2026-11-16"), ("Posted 30+ Days Ago", ""), ("", ""),
])
def test_workday_posted_on(posted, expected):
    assert ats._workday_posted(posted, DAY) == expected


def test_oracle():
    s = src(ats="oracle", base="https://acme.fa.oraclecloud.com", site="CX_1")
    raw = {"pages": [{"items": [{"TotalJobsCount": 1, "requisitionList": [
        {"Id": "210500", "Title": "Wealth Management Associate", "PostedDate": "2026-11-10",
         "PrimaryLocation": "New York, NY, United States", "Organization": "Wealth"},
    ]}]}]}
    (row,) = ats.normalize(s, raw, DAY)
    assert set(row) == KEYS
    assert row["source_id"] == "210500"
    assert row["posted_date"] == "2026-11-10"
    assert row["department"] == "Wealth"
    assert row["url"] == "https://acme.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/210500"


def test_eightfold():
    s = src(ats="eightfold", host="acme.eightfold.ai", domain="acme.com")
    raw = {"pages": [{"count": 1, "positions": [
        {"id": 5550, "name": "Client Service Associate", "location": "Chicago, IL",
         "department": "Wealth Management", "t_create": 1762992000,
         "canonicalPositionUrl": "https://acme.eightfold.ai/careers/job/5550"},
    ]}]}
    (row,) = ats.normalize(s, raw, DAY)
    assert set(row) == KEYS
    assert row["source_id"] == "5550"
    assert row["posted_date"] == "2025-11-13"
    assert row["department"] == "Wealth Management"


def test_greenhouse():
    s = src(ats="greenhouse", board="acme")
    raw = {"pages": [{"jobs": [
        {"id": 4001, "title": "  Financial  Planner ", "location": {"name": "Remote"},
         "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/4001",
         "first_published": "2026-11-01T12:00:00-05:00"},
    ]}]}
    (row,) = ats.normalize(s, raw, DAY)
    assert set(row) == KEYS
    assert row["title"] == "Financial Planner"        # whitespace cleaned
    assert row["posted_date"] == "2026-11-01"
    assert row["department"] == ""


def test_lever():
    s = src(ats="lever", board="acme")
    raw = {"pages": [[
        {"id": "abc-123", "text": "Paraplanner", "hostedUrl": "https://jobs.lever.co/acme/abc-123",
         "createdAt": 1763000000000, "categories": {"location": "Denver, CO", "team": "Advice"}},
    ]]}
    (row,) = ats.normalize(s, raw, DAY)
    assert set(row) == KEYS
    assert row["source_id"] == "abc-123"
    assert row["department"] == "Advice"
    assert row["posted_date"] == "2025-11-13"


def test_ashby():
    s = src(ats="ashby", board="acme")
    raw = {"pages": [{"jobs": [
        {"id": "u-1", "title": "Analyst", "location": "New York", "department": "Finance",
         "publishedAt": "2026-11-12T08:00:00.000+00:00", "jobUrl": "https://jobs.ashbyhq.com/acme/u-1"},
    ]}]}
    (row,) = ats.normalize(s, raw, DAY)
    assert set(row) == KEYS
    assert (row["source_id"], row["posted_date"]) == ("u-1", "2026-11-12")


def test_smartrecruiters():
    s = src(ats="smartrecruiters", board="Acme")
    raw = {"pages": [{"totalFound": 1, "content": [
        {"id": "7440", "name": "Investment Advisor", "releasedDate": "2026-11-15T10:00:00.000Z",
         "location": {"city": "Austin", "region": "TX", "country": "us"}, "department": {"label": "Sales"}},
    ]}]}
    (row,) = ats.normalize(s, raw, DAY)
    assert set(row) == KEYS
    assert row["location"] == "Austin, TX, us"
    assert row["url"] == "https://jobs.smartrecruiters.com/Acme/7440"


def test_every_ats_has_fetcher_and_normalizer():
    assert set(ats.FETCHERS) == set(ats.NORMALIZERS)
