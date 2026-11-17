import pytest

from watcher.rules import in_role


@pytest.mark.parametrize("title", [
    "Financial Advisor",
    "Financial Advisor Associate",
    "Financial Advisor Trainee - Fayetteville, AR",
    "Associate Financial Advisor",
    "Financial Planner",
    "Financial Consultant",
    "Wealth Management Associate",
    "Wealth Management Analyst",
    "Associate, Private Wealth Management",
    "Analyst - Private Client Group",
    "Private Client Associate",
    "Client Service Associate",
    "Client Associate",
    "Investment Advisor",
    "Financial Planning Associate",
    "Paraplanner",
    "Advisor Development Program",
    "Retirement Advisor",
    "J.P. Morgan Wealth Management – Private Client Advisor - Bend, OR",
    "2027 Global Private Bank Advisor Program (Full-time Analyst)",
    "2027 Financial Advisor Development Program",
])
def test_in_role(title):
    assert in_role(title)


@pytest.mark.parametrize("title", [
    "Senior Financial Advisor",
    "Sr. Financial Advisor",
    "Executive Director, Wealth Management",
    "Vice President - Private Client Advisor",
    "Branch Manager",
    "Wealth Management Director",
    "Financial Advisor Summer Intern",
    "Software Engineer",
    "Data Analyst",
    "Teller",
    "Relationship Banker",
    "Recruiting Analyst - Wealth Management",
    "Media Relations Associate - J.P. Morgan Wealth Management",
    "Quality Control Associate, Asset Wealth Management Operations",
    "Software Engineer III - Private Client Technology",
    "",
])
def test_not_in_role(title):
    assert not in_role(title)


def test_case_insensitive():
    assert in_role("FINANCIAL ADVISOR")
    assert not in_role("SENIOR FINANCIAL ADVISOR")
