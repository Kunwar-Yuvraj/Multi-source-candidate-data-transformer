"""Date normalization.

Canonical month format is ``YYYY-MM``. We accept a range of common inputs
(ISO, "Jan 2020", "January 2020", "2020", "03/2020", "2020-03-01") and degrade
to None when we cannot confidently parse. The string ``present``/``current`` is
recognized and returned as the literal ``"present"`` for ongoing experience.
"""

from __future__ import annotations

import re
from typing import Optional

from dateutil import parser as _dateparser

_PRESENT = {"present", "current", "now", "ongoing"}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_YEAR_ONLY_RE = re.compile(r"^(19|20)\d{2}$")
_YYYY_MM_RE = re.compile(r"^(19|20)\d{2}-(0[1-9]|1[0-2])$")
_MON_YEAR_RE = re.compile(r"^([A-Za-z]+)\.?\s+(\d{4})$")


def normalize_month(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.lower() in _PRESENT:
        return "present"
    if _YYYY_MM_RE.match(raw):
        return raw
    if _YEAR_ONLY_RE.match(raw):
        # Year only -> we keep just the year as YYYY (no fake month).
        return raw
    m = _MON_YEAR_RE.match(raw)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            return f"{m.group(2)}-{mon:02d}"
    # Fall back to dateutil for ISO-ish strings, but require an explicit month.
    try:
        # default day=1 so we can detect whether month was actually present
        dt = _dateparser.parse(raw, default=_dateparser.parse("2000-01-01"))
    except (ValueError, OverflowError, TypeError):
        return None
    # Guard: dateutil happily parses bare numbers; require a 4-digit year token.
    if not re.search(r"(19|20)\d{2}", raw):
        return None
    return f"{dt.year:04d}-{dt.month:02d}"


def normalize_year(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip()
    m = re.search(r"(19|20)\d{2}", raw)
    if m:
        return int(m.group(0))
    return None
