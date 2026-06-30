"""ATS JSON blob extractor (semi-structured source).

The ATS uses its *own* field names that do not match our canonical schema, e.g.::

    {
      "applicant": {"fullName": "...", "primaryEmail": "...", "mobileNumber": "..."},
      "employment": [{"org": "...", "designation": "...", "from": "...", "to": "..."}],
      "schools": [{"name": "...", "qualification": "...", "major": "...", "gradYear": ...}],
      "competencies": ["..."],
      "social": {"linkedinUrl": "...", "githubUrl": "..."}
    }

A file may contain a single object or a list of objects. Malformed JSON is logged
and skipped.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Optional

from ..models import RawRecord

log = logging.getLogger(__name__)

SOURCE = "ats_json"


def _first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return None


def extract_ats_json(path: str) -> Iterator[RawRecord]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("ats_json: cannot parse %s: %s", path, exc)
        return
    blobs = data if isinstance(data, list) else [data]
    for i, blob in enumerate(blobs):
        if not isinstance(blob, dict):
            log.warning("ats_json: skipping non-object entry %d in %s", i, path)
            continue
        try:
            rec = _blob_to_record(blob, f"{path}#{i}")
        except Exception as exc:
            log.warning("ats_json: skipping bad entry %d in %s: %s", i, path, exc)
            continue
        if rec is not None:
            yield rec


def _blob_to_record(blob: Dict[str, Any], ref: str) -> Optional[RawRecord]:
    rec = RawRecord(source=SOURCE, source_ref=ref)
    applicant = blob.get("applicant") if isinstance(blob.get("applicant"), dict) else blob

    name = _first(applicant, ["fullName", "full_name", "name", "candidateName"])
    if name:
        rec.full_name = str(name)
        rec.method_map["full_name"] = f"{SOURCE}:applicant.fullName"

    for key in ["primaryEmail", "email", "emailAddress", "secondaryEmail"]:
        v = applicant.get(key)
        if v:
            rec.emails.append(str(v))
    if rec.emails:
        rec.method_map["emails"] = f"{SOURCE}:applicant.email"

    for key in ["mobileNumber", "phone", "phoneNumber", "mobile"]:
        v = applicant.get(key)
        if v:
            rec.phones.append(str(v))
    if rec.phones:
        rec.method_map["phones"] = f"{SOURCE}:applicant.mobileNumber"

    loc = _first(applicant, ["location", "city", "currentLocation", "address"])
    if loc:
        rec.location_raw = str(loc)
        rec.method_map["location"] = f"{SOURCE}:applicant.location"

    headline = _first(applicant, ["headline", "summary", "objective", "currentTitle"])
    if headline:
        rec.headline = str(headline)
        rec.method_map["headline"] = f"{SOURCE}:applicant.headline"

    social = blob.get("social") if isinstance(blob.get("social"), dict) else {}
    li = _first(social, ["linkedinUrl", "linkedin"])
    gh = _first(social, ["githubUrl", "github"])
    if li:
        rec.links["linkedin"] = str(li)
        rec.method_map["links.linkedin"] = f"{SOURCE}:social.linkedinUrl"
    if gh:
        rec.links["github"] = str(gh)
        rec.method_map["links.github"] = f"{SOURCE}:social.githubUrl"

    yexp = _first(applicant, ["yearsOfExperience", "totalExperience", "experienceYears"])
    if yexp is not None:
        try:
            rec.years_experience = float(yexp)
            rec.method_map["years_experience"] = f"{SOURCE}:applicant.yearsOfExperience"
        except (TypeError, ValueError):
            pass

    comps = blob.get("competencies") or blob.get("skills") or applicant.get("skills")
    if isinstance(comps, list):
        rec.skills = [str(c) for c in comps if c]
        rec.method_map["skills"] = f"{SOURCE}:competencies"

    employment = blob.get("employment") or blob.get("workHistory") or []
    if isinstance(employment, list):
        for job in employment:
            if not isinstance(job, dict):
                continue
            rec.experience.append(
                {
                    "company": _first(job, ["org", "company", "employer"]),
                    "title": _first(job, ["designation", "title", "role"]),
                    "start": _first(job, ["from", "start", "startDate"]),
                    "end": _first(job, ["to", "end", "endDate"]),
                    "summary": _first(job, ["summary", "description"]),
                }
            )
        if rec.experience:
            rec.method_map["experience"] = f"{SOURCE}:employment"

    schools = blob.get("schools") or blob.get("education") or []
    if isinstance(schools, list):
        for sch in schools:
            if not isinstance(sch, dict):
                continue
            rec.education.append(
                {
                    "institution": _first(sch, ["name", "institution", "school"]),
                    "degree": _first(sch, ["qualification", "degree"]),
                    "field": _first(sch, ["major", "field", "fieldOfStudy"]),
                    "end_year": _first(sch, ["gradYear", "endYear", "year"]),
                }
            )
        if rec.education:
            rec.method_map["education"] = f"{SOURCE}:schools"

    has_data = any(
        [rec.full_name, rec.emails, rec.phones, rec.skills, rec.experience, rec.education]
    )
    return rec if has_data else None
