"""Recruiter CSV extractor (structured source).

Expected-ish columns: name, email, phone, current_company, title, location,
linkedin, github, skills. We map flexible header aliases to canonical fields and
skip rows that are unusable, without crashing on a single bad row.
"""

from __future__ import annotations

import csv
import logging
from typing import Dict, Iterator, List

from ..models import RawRecord

log = logging.getLogger(__name__)

SOURCE = "recruiter_csv"

# header alias -> canonical raw field
_HEADER_MAP: Dict[str, str] = {
    "name": "full_name",
    "full name": "full_name",
    "candidate": "full_name",
    "candidate name": "full_name",
    "email": "email",
    "email address": "email",
    "e-mail": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "current company": "current_company",
    "company": "current_company",
    "employer": "current_company",
    "title": "title",
    "job title": "title",
    "role": "title",
    "position": "title",
    "location": "location",
    "city": "location",
    "linkedin": "linkedin",
    "linkedin url": "linkedin",
    "github": "github",
    "skills": "skills",
}


def _norm_header(h: str) -> str:
    # Treat underscores/extra whitespace as spaces so "current_company",
    # "current company" and "Current  Company" all map the same way.
    return " ".join((h or "").strip().lower().replace("_", " ").split())


def extract_csv(path: str) -> Iterator[RawRecord]:
    try:
        f = open(path, "r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        log.warning("csv: cannot open %s: %s", path, exc)
        return
    with f:
        try:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                log.warning("csv: empty or headerless file %s", path)
                return
            field_lookup = {
                name: _HEADER_MAP.get(_norm_header(name))
                for name in reader.fieldnames
            }
            row_no = 1
            for row in reader:
                row_no += 1
                try:
                    rec = _row_to_record(row, field_lookup, path, row_no)
                except Exception as exc:  # never let one row kill the run
                    log.warning("csv: skipping bad row %d in %s: %s", row_no, path, exc)
                    continue
                if rec is not None:
                    yield rec
        except csv.Error as exc:
            log.warning("csv: parse error in %s: %s", path, exc)


def _row_to_record(row, field_lookup, path, row_no):
    rec = RawRecord(source=SOURCE, source_ref=f"{path}#row{row_no}")
    skills: List[str] = []
    found_anything = False
    for col, value in row.items():
        canon = field_lookup.get(col)
        if not canon or value is None:
            continue
        value = value.strip()
        if not value:
            continue
        found_anything = True
        if canon == "full_name":
            rec.full_name = value
            rec.method_map["full_name"] = f"{SOURCE}:column:{col}"
        elif canon == "email":
            rec.emails.append(value)
            rec.method_map["emails"] = f"{SOURCE}:column:{col}"
        elif canon == "phone":
            rec.phones.append(value)
            rec.method_map["phones"] = f"{SOURCE}:column:{col}"
        elif canon == "current_company":
            rec.current_company = value
            rec.method_map["current_company"] = f"{SOURCE}:column:{col}"
        elif canon == "title":
            rec.title = value
            rec.method_map["headline"] = f"{SOURCE}:column:{col}"
        elif canon == "location":
            rec.location_raw = value
            rec.method_map["location"] = f"{SOURCE}:column:{col}"
        elif canon == "linkedin":
            rec.links["linkedin"] = value
            rec.method_map["links.linkedin"] = f"{SOURCE}:column:{col}"
        elif canon == "github":
            rec.links["github"] = value
            rec.method_map["links.github"] = f"{SOURCE}:column:{col}"
        elif canon == "skills":
            for tok in value.replace("|", ",").replace(";", ",").split(","):
                tok = tok.strip()
                if tok:
                    skills.append(tok)
            rec.method_map["skills"] = f"{SOURCE}:column:{col}"
    if skills:
        rec.skills = skills
    if rec.current_company and rec.title:
        rec.experience.append(
            {
                "company": rec.current_company,
                "title": rec.title,
                "start": None,
                "end": None,
                "summary": None,
            }
        )
        rec.method_map["experience"] = f"{SOURCE}:columns:company+title"
    return rec if found_anything else None
