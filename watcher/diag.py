"""One request per known Workday board, printing the status code and a snippet.

    python -u -m watcher.diag

Uses the same honest User-Agent as the pipeline. A board that answers
403/429 is treated as blocking the tool and gets replaced in sources.json.
"""
import time

import requests

from . import ats

BOARDS = [
    ("fmr.wd1.myworkdayjobs.com", "fmr", "FidelityCareers"),
    ("capitalone.wd12.myworkdayjobs.com", "capitalone", "Capital_One"),
    ("blackrock.wd1.myworkdayjobs.com", "blackrock", "BlackRock_Professional"),
    ("statestreet.wd1.myworkdayjobs.com", "statestreet", "Global"),
    ("pnc.wd5.myworkdayjobs.com", "pnc", "External"),
    ("troweprice.wd5.myworkdayjobs.com", "troweprice", "TRowePrice"),
    ("usbank.wd1.myworkdayjobs.com", "usbank", "US_Bank_Careers"),
    ("citi.wd5.myworkdayjobs.com", "citi", "2"),
]

HEADERS = {"User-Agent": ats.UA, "Accept": "application/json", "Content-Type": "application/json"}

for host, tenant, site in BOARDS:
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    try:
        r = requests.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
                          headers=HEADERS, timeout=30)
        print(f"{host}/{site} {r.status_code} {r.text[:120]!r}", flush=True)
    except Exception as exc:
        print(f"{host}/{site} ERROR {exc}", flush=True)
    time.sleep(3)
