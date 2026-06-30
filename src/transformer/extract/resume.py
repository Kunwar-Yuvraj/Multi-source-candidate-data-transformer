"""Resume extractor (PDF prose, unstructured source).

We extract text with ``pdfplumber``, mine high-precision signals (emails, phones,
links, skills) with regexes, and run a light section parser for
experience/education plus a first-line name heuristic.

Robustness: any failure to open/parse a file logs a warning and yields nothing.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Iterator, List, Optional

from ..models import RawRecord

log = logging.getLogger(__name__)

SOURCE = "resume"

# --- free-text mining patterns ---------------------------------------------
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:(?:\+?\d{1,3})[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?){2,4}\d{2,4}")
_LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9_\-%/]+", re.I)
_GITHUB_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-.]+)?", re.I)
_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
_SKILLS_LINE_RE = re.compile(r"(?:skills|technologies|tech stack)\s*[:\-]\s*(.+)", re.I)


def _find_phones(text: str) -> List[str]:
    out = []
    for m in _PHONE_RE.findall(text or ""):
        s = m.strip()
        if 7 <= len(re.sub(r"\D", "", s)) <= 15:
            out.append(s)
    return out


def _find_links(text: str) -> Dict[str, object]:
    text = text or ""
    links: Dict[str, object] = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    li = _LINKEDIN_RE.search(text)
    if li:
        links["linkedin"] = li.group(0).rstrip("/.,)")
    gh = _GITHUB_RE.search(text)
    if gh:
        links["github"] = gh.group(0).rstrip("/.,)")
    others = [u.rstrip(".,)>]") for u in _URL_RE.findall(text)
              if "linkedin.com" not in u and "github.com" not in u]
    if others:
        links["other"] = sorted(set(others))
    return links


def _find_skills_line(text: str) -> List[str]:
    skills: List[str] = []
    for line in (text or "").splitlines():
        m = _SKILLS_LINE_RE.search(line)
        if m:
            for tok in re.split(r"[,/|;•]", m.group(1)):
                tok = tok.strip()
                if tok and len(tok) <= 40:
                    skills.append(tok)
    return skills


def _read_pdf(path: str) -> Optional[str]:
    try:
        import pdfplumber
    except ImportError:
        log.warning("resume: pdfplumber not installed; cannot read %s", path)
        return None
    try:
        parts: List[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception as exc:  # corrupt PDF, encrypted, etc.
        log.warning("resume: failed to read PDF %s: %s", path, exc)
        return None


_SECTION_HEADERS = {
    "experience": re.compile(r"^\s*(work experience|experience|employment)\s*$", re.I),
    "education": re.compile(r"^\s*(education|academics)\s*$", re.I),
    "skills": re.compile(r"^\s*(skills|technical skills|technologies)\s*$", re.I),
}

# "Software Engineer, Acme Corp (2019-2022)" style line
_EXP_LINE = re.compile(
    r"^(?P<title>[A-Z][\w/&.\- ]+?)\s+(?:at|@|,)\s+(?P<company>[\w/&.\- ]+?)"
    r"\s*[\(\-]?\s*(?P<start>[A-Za-z0-9]{3,9}\s?\d{4}|\d{4})\s*[-\u2013to]+\s*"
    r"(?P<end>present|current|[A-Za-z0-9]{3,9}\s?\d{4}|\d{4})",
    re.I,
)
_EDU_LINE = re.compile(
    r"^(?P<degree>(?:B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|Ph\.?D\.?|Bachelor|Master|"
    r"B\.?Tech|M\.?Tech)[\w. ]*?)(?:\s+in\s+(?P<field>[\w &]+?))?,?\s+"
    r"(?P<institution>[\w &.\-]+?)(?:,?\s*(?P<year>\d{4}))?\s*$",
    re.I,
)


def _looks_like_name(line: str) -> bool:
    if not line or len(line) > 40:
        return False
    if "@" in line or any(ch.isdigit() for ch in line):
        return False
    words = line.split()
    if not (1 < len(words) <= 4):
        return False
    return all(w[:1].isupper() for w in words if w)


def extract_resume(path: str) -> Iterator[RawRecord]:
    text = _read_pdf(path)
    if not text or not text.strip():
        log.warning("resume: no extractable text in %s", path)
        return

    rec = RawRecord(source=SOURCE, source_ref=path)
    rec.emails = _EMAIL_RE.findall(text)
    rec.phones = _find_phones(text)
    rec.links = _find_links(text)
    rec.skills = _find_skills_line(text)
    if rec.emails:
        rec.method_map["emails"] = f"{SOURCE}:regex:email"
    if rec.phones:
        rec.method_map["phones"] = f"{SOURCE}:regex:phone"
    if rec.skills:
        rec.method_map["skills"] = f"{SOURCE}:regex:skills-line"
    if any(rec.links.get(k) for k in ("linkedin", "github")) or rec.links.get("other"):
        rec.method_map["links.linkedin"] = f"{SOURCE}:regex:url"
        rec.method_map["links.github"] = f"{SOURCE}:regex:url"

    lines = [ln.rstrip() for ln in text.splitlines()]

    # Name: first non-empty line that looks like a name.
    for ln in lines[:8]:
        if _looks_like_name(ln.strip()):
            rec.full_name = ln.strip()
            rec.method_map["full_name"] = f"{SOURCE}:heuristic:first-line"
            break

    # Section-aware experience/education parsing.
    current = None
    skill_tokens: List[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            continue
        matched_header = None
        for name, rx in _SECTION_HEADERS.items():
            if rx.match(stripped):
                matched_header = name
                break
        if matched_header:
            current = matched_header
            continue

        if current == "experience":
            m = _EXP_LINE.match(stripped)
            if m:
                rec.experience.append(
                    {
                        "company": m.group("company").strip(),
                        "title": m.group("title").strip(),
                        "start": m.group("start"),
                        "end": m.group("end"),
                        "summary": None,
                    }
                )
        elif current == "education":
            m = _EDU_LINE.match(stripped)
            if m:
                rec.education.append(
                    {
                        "institution": (m.group("institution") or "").strip() or None,
                        "degree": (m.group("degree") or "").strip() or None,
                        "field": (m.group("field") or "").strip() or None,
                        "end_year": m.group("year"),
                    }
                )
        elif current == "skills":
            for tok in re.split(r"[,/|;•\t]", stripped):
                tok = tok.strip()
                if tok and len(tok) <= 40:
                    skill_tokens.append(tok)

    if skill_tokens:
        rec.skills.extend(skill_tokens)
        rec.method_map["skills"] = f"{SOURCE}:section:skills"
    if rec.experience:
        rec.method_map["experience"] = f"{SOURCE}:section:experience"
    if rec.education:
        rec.method_map["education"] = f"{SOURCE}:section:education"

    has_data = any([rec.full_name, rec.emails, rec.phones, rec.skills, rec.experience])
    if has_data:
        yield rec
