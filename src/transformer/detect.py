"""Source-type detection.

Maps an input file path to an extractor by file extension
(``.csv`` -> recruiter CSV, ``.json`` -> ATS blob, ``.pdf`` -> resume).
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Iterator, Optional

from .extract import extract_ats_json, extract_csv, extract_resume
from .models import RawRecord

log = logging.getLogger(__name__)

Extractor = Callable[[str], Iterator[RawRecord]]


def detect_source(spec: str) -> Optional[str]:
    """Return a source-type label for an input path, or None if unknown."""
    if not os.path.exists(spec):
        return None
    ext = os.path.splitext(spec)[1].lower()
    if ext == ".csv":
        return "recruiter_csv"
    if ext == ".json":
        return "ats_json"
    if ext == ".pdf":
        return "resume"
    return None


_EXTRACTORS = {
    "recruiter_csv": extract_csv,
    "ats_json": extract_ats_json,
    "resume": extract_resume,
}


def get_extractor(source: str) -> Optional[Extractor]:
    return _EXTRACTORS.get(source)
