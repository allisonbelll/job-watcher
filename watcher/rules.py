"""Title rule: is a posting an entry-level financial advising role?

A title is in the role when it matches at least one INCLUDE pattern and none
of the EXCLUDE patterns.  Matching ignores case.  README.md states the same
rule in words; tests/test_rules.py pins it down with examples.
"""

import re

INCLUDE = [
    r"\bfinancial (advisor|adviser|planner|consultant|professional|representative)s?\b",
    r"\b(investment|wealth|retirement|client) (advisor|adviser)s?\b",
    r"\bwealth (management )?(associate|analyst|planner|planning)\b",
    r"\b(associate|analyst)\b.*\b(wealth|private bank|private client)",
    r"\bprivate (client|wealth|bank(ing)?) (associate|analyst)\b",
    r"\bclient (service )?associate\b",
    r"\bfinancial planning (associate|analyst|specialist)\b",
    r"\bparaplanner\b",
    r"\b(advisor|adviser) (associate|trainee|development|apprentice)\b",
]

EXCLUDE = [
    r"\bsenior\b", r"\bsr\.?(?=\s|$)", r"\blead\b", r"\bprincipal\b",
    r"\bdirector\b", r"\bvice president\b", r"\b(a|s)?vp\b", r"\bmanaging\b",
    r"\bhead of\b", r"\bmanager\b", r"\bexecutive\b", r"\bchief\b",
    r"\bpartner\b", r"\bintern(ship)?\b",
]

_INCLUDE = re.compile("|".join(f"(?:{p})" for p in INCLUDE), re.I)
_EXCLUDE = re.compile("|".join(f"(?:{p})" for p in EXCLUDE), re.I)


def in_role(title: str) -> bool:
    title = title or ""
    return bool(_INCLUDE.search(title)) and not _EXCLUDE.search(title)
