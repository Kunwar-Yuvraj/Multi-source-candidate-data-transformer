"""Normalize -> cluster -> resolve into one canonical profile per candidate.

This module owns the deterministic identity-resolution and conflict policy:

* Matching keys: normalized email, then E.164 phone, then (name + company).
* Winner selection: highest confidence, then source trust, then a stable
  alphabetical tiebreak so the same inputs always yield the same output.
* Every contributing value is recorded in provenance, including losers.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import confidence as conf
from .models import (
    CanonicalProfile,
    FieldValue,
    Provenance,
    RawRecord,
    Skill,
    source_trust,
)
from .normalize import (
    canonical_skills,
    normalize_country,
    normalize_emails,
    normalize_month,
    normalize_name,
    normalize_phones,
    normalize_year,
    parse_location,
)
from .normalize.names import name_key

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalized intermediate
# ---------------------------------------------------------------------------


@dataclass
class NormalizedRecord:
    source: str
    source_ref: str
    full_name: Optional[FieldValue] = None
    emails: List[FieldValue] = field(default_factory=list)
    phones: List[FieldValue] = field(default_factory=list)
    location: Optional[FieldValue] = None  # value is dict city/region/country
    links: Dict[str, FieldValue] = field(default_factory=dict)
    links_other: List[FieldValue] = field(default_factory=list)
    headline: Optional[FieldValue] = None
    years_experience: Optional[FieldValue] = None
    skills: List[Tuple[FieldValue, bool]] = field(default_factory=list)  # (fv, is_known)
    experience: List[FieldValue] = field(default_factory=list)  # value is dict
    education: List[FieldValue] = field(default_factory=list)  # value is dict


def _fv(value, source, method) -> FieldValue:
    return FieldValue(
        value=value,
        source=source,
        method=method,
        confidence=conf.base_confidence(source, method),
    )


def normalize_record(raw: RawRecord) -> NormalizedRecord:
    """Convert a raw, source-shaped record into normalized canonical values."""
    src = raw.source
    nr = NormalizedRecord(source=src, source_ref=raw.source_ref)

    name = normalize_name(raw.full_name)
    if name:
        nr.full_name = _fv(name, src, raw.method_for("full_name"))

    # Location first so we can use country as a phone region hint.
    loc = {"city": None, "region": None, "country": None}
    if raw.location_raw:
        loc = parse_location(raw.location_raw)
    for k in ("city", "region", "country"):
        if raw.location.get(k):
            if k == "country":
                loc[k] = normalize_country(raw.location[k]) or loc[k]
            else:
                loc[k] = raw.location[k] or loc[k]
    if any(loc.values()):
        nr.location = _fv(loc, src, raw.method_for("location", f"{src}:location"))

    region_hint = loc.get("country")
    for e in normalize_emails(raw.emails):
        nr.emails.append(_fv(e, src, raw.method_for("emails", f"{src}:email")))
    for p in normalize_phones(raw.phones, default_region=region_hint):
        nr.phones.append(_fv(p, src, raw.method_for("phones", f"{src}:phone")))

    for kind in ("linkedin", "github", "portfolio"):
        v = raw.links.get(kind)
        if v:
            nr.links[kind] = _fv(
                str(v).strip(), src, raw.method_for(f"links.{kind}", f"{src}:link")
            )
    for o in raw.links.get("other", []) or []:
        nr.links_other.append(_fv(str(o).strip(), src, f"{src}:link:other"))

    headline = raw.headline or raw.title
    if headline:
        nr.headline = _fv(str(headline).strip(), src, raw.method_for("headline", f"{src}:headline"))

    if raw.years_experience is not None:
        nr.years_experience = _fv(
            float(raw.years_experience), src, raw.method_for("years_experience")
        )

    for name_, known in canonical_skills(raw.skills):
        nr.skills.append((_fv(name_, src, raw.method_for("skills", f"{src}:skill")), known))

    for job in raw.experience:
        norm_job = {
            "company": (job.get("company") or None),
            "title": (job.get("title") or None),
            "start": normalize_month(job.get("start")),
            "end": normalize_month(job.get("end")),
            "summary": (job.get("summary") or None),
        }
        if any(norm_job.values()):
            nr.experience.append(_fv(norm_job, src, raw.method_for("experience", f"{src}:experience")))

    for edu in raw.education:
        norm_edu = {
            "institution": (edu.get("institution") or None),
            "degree": (edu.get("degree") or None),
            "field": (edu.get("field") or None),
            "end_year": normalize_year(edu.get("end_year")),
        }
        if any(v is not None for v in norm_edu.values()):
            nr.education.append(_fv(norm_edu, src, raw.method_for("education", f"{src}:education")))

    return nr


# ---------------------------------------------------------------------------
# Clustering (identity resolution)
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _identity_keys(nr: NormalizedRecord) -> List[str]:
    keys = []
    for e in nr.emails:
        keys.append(f"email:{e.value}")
    for p in nr.phones:
        keys.append(f"phone:{p.value}")
    if nr.full_name:
        company = ""
        if nr.experience:
            company = (nr.experience[0].value.get("company") or "").strip().lower()
        nk = name_key(nr.full_name.value)
        if nk and company:
            keys.append(f"nameco:{nk}|{company}")
    return keys


def cluster_records(records: List[NormalizedRecord]) -> List[List[NormalizedRecord]]:
    uf = _UnionFind(len(records))
    key_to_idx: Dict[str, int] = {}
    for i, nr in enumerate(records):
        for key in _identity_keys(nr):
            if key in key_to_idx:
                uf.union(i, key_to_idx[key])
            else:
                key_to_idx[key] = i
    groups: Dict[int, List[NormalizedRecord]] = defaultdict(list)
    for i, nr in enumerate(records):
        groups[uf.find(i)].append(nr)
    # Deterministic ordering of clusters and of records within a cluster.
    ordered = []
    for root in sorted(groups):
        members = sorted(groups[root], key=lambda r: (r.source, r.source_ref))
        ordered.append(members)
    return ordered


# ---------------------------------------------------------------------------
# Winner selection
# ---------------------------------------------------------------------------


def _select_scalar(values: List[FieldValue]) -> Optional[Tuple[FieldValue, float, int]]:
    """Pick a winning scalar value with agreement-aware confidence.

    Returns (winning_field_value, final_confidence, n_agreeing) or None.
    """
    if not values:
        return None
    groups: Dict[str, List[FieldValue]] = defaultdict(list)
    for v in values:
        groups[str(v.value).strip().lower()].append(v)

    best = None
    for _, grp in groups.items():
        rep = max(grp, key=lambda v: (v.confidence, source_trust(v.source)))
        final_conf = conf.agreement_boost(rep.confidence, len(grp))
        # Deterministic ranking: confidence, then trust, then corroboration,
        # then a stable alphabetical tiebreak on the value itself.
        score = (final_conf, source_trust(rep.source), len(grp), str(rep.value))
        if best is None or score > best[0]:
            best = (score, rep, final_conf, len(grp))
    _, rep, final_conf, n = best
    return rep, final_conf, n


def _provenance_for(field_name: str, values: List[FieldValue]) -> List[Provenance]:
    seen = set()
    out = []
    for v in sorted(values, key=lambda x: (-x.confidence, x.source, x.method)):
        sig = (field_name, v.source, v.method)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(Provenance(field=field_name, source=v.source, method=v.method))
    return out


def _candidate_id(group: List[NormalizedRecord]) -> str:
    keys = set()
    for nr in group:
        for e in nr.emails:
            keys.add(f"e:{e.value}")
        for p in nr.phones:
            keys.add(f"p:{p.value}")
    if not keys:
        for nr in group:
            if nr.full_name:
                keys.add(f"n:{name_key(nr.full_name.value)}")
    if not keys:
        for nr in group:
            keys.add(f"r:{nr.source_ref}")
    digest = hashlib.sha1("|".join(sorted(keys)).encode("utf-8")).hexdigest()[:12]
    return f"cand_{digest}"


def build_profile(group: List[NormalizedRecord]) -> CanonicalProfile:
    cid = _candidate_id(group)
    profile = CanonicalProfile(candidate_id=cid)
    provenance: List[Provenance] = []
    field_conf: Dict[str, float] = {}

    # full_name
    names = [nr.full_name for nr in group if nr.full_name]
    sel = _select_scalar(names)
    if sel:
        profile.full_name = sel[0].value
        field_conf["full_name"] = sel[1]
        provenance += _provenance_for("full_name", names)

    # emails / phones: union, ordered by confidence then value
    profile.emails, ec = _merge_list_scalars([e for nr in group for e in nr.emails])
    if profile.emails:
        field_conf["emails"] = ec
        provenance += _provenance_for("emails", [e for nr in group for e in nr.emails])
    profile.phones, pc = _merge_list_scalars([p for nr in group for p in nr.phones])
    if profile.phones:
        field_conf["phones"] = pc
        provenance += _provenance_for("phones", [p for nr in group for p in nr.phones])

    # location: component-wise winner
    loc_fvs = [nr.location for nr in group if nr.location]
    if loc_fvs:
        location = {"city": None, "region": None, "country": None}
        comp_confs = []
        for comp in ("city", "region", "country"):
            comp_vals = [
                FieldValue(value=fv.value[comp], source=fv.source, method=fv.method, confidence=fv.confidence)
                for fv in loc_fvs
                if fv.value.get(comp)
            ]
            csel = _select_scalar(comp_vals)
            if csel:
                location[comp] = csel[0].value
                comp_confs.append(csel[1])
        profile.location = location
        if comp_confs:
            field_conf["location"] = conf.aggregate(comp_confs)
            provenance += _provenance_for("location", loc_fvs)

    # links
    for kind in ("linkedin", "github", "portfolio"):
        vals = [nr.links[kind] for nr in group if kind in nr.links]
        sel = _select_scalar(vals)
        if sel:
            profile.links[kind] = sel[0].value
            field_conf[f"links.{kind}"] = sel[1]
            provenance += _provenance_for(f"links.{kind}", vals)
    other_vals = [o for nr in group for o in nr.links_other]
    if other_vals:
        profile.links["other"], _ = _merge_list_scalars(other_vals)

    # headline
    headlines = [nr.headline for nr in group if nr.headline]
    sel = _select_scalar(headlines)
    if sel:
        profile.headline = sel[0].value
        field_conf["headline"] = sel[1]
        provenance += _provenance_for("headline", headlines)

    # years_experience
    yexp = [nr.years_experience for nr in group if nr.years_experience]
    sel = _select_scalar(yexp)
    if sel:
        profile.years_experience = sel[0].value
        field_conf["years_experience"] = sel[1]
        provenance += _provenance_for("years_experience", yexp)

    # skills: aggregate by canonical name across sources
    profile.skills, skills_conf = _merge_skills(group)
    if profile.skills:
        field_conf["skills"] = skills_conf
        skill_fvs = [fv for nr in group for (fv, _known) in nr.skills]
        provenance += _provenance_for("skills", skill_fvs)

    # experience / education: union + dedupe by identity tuple
    profile.experience = _merge_dicts(
        [e for nr in group for e in nr.experience],
        key=lambda d: ((d.get("company") or "").lower(), (d.get("title") or "").lower()),
    )
    if profile.experience:
        field_conf["experience"] = conf.aggregate(
            [e.confidence for nr in group for e in nr.experience]
        )
        provenance += _provenance_for("experience", [e for nr in group for e in nr.experience])
    profile.education = _merge_dicts(
        [e for nr in group for e in nr.education],
        key=lambda d: ((d.get("institution") or "").lower(), (d.get("degree") or "").lower()),
    )
    if profile.education:
        field_conf["education"] = conf.aggregate(
            [e.confidence for nr in group for e in nr.education]
        )
        provenance += _provenance_for("education", [e for nr in group for e in nr.education])

    profile.provenance = provenance
    profile.field_confidence = field_conf
    profile.overall_confidence = conf.aggregate(field_conf.values())
    return profile


def _merge_list_scalars(values: List[FieldValue]) -> Tuple[List[str], float]:
    """Union dedupe scalar list values, ordered by confidence then alpha."""
    best_conf: Dict[str, float] = {}
    for v in values:
        cur = best_conf.get(v.value, 0.0)
        # corroboration: same value from multiple sources -> boost
        n = sum(1 for x in values if x.value == v.value)
        c = conf.agreement_boost(max(cur, v.confidence), n)
        best_conf[v.value] = c
    ordered = sorted(best_conf.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ordered:
        return [], 0.0
    out = [k for k, _ in ordered]
    agg = conf.aggregate([c for _, c in ordered])
    return out, agg


def _merge_skills(group: List[NormalizedRecord]) -> Tuple[List[Skill], float]:
    by_name: Dict[str, Dict] = {}
    for nr in group:
        for fv, known in nr.skills:
            entry = by_name.setdefault(
                fv.value, {"sources": set(), "confs": [], "known": False}
            )
            entry["sources"].add(fv.source)
            # unknown skills get a confidence penalty; known ones a small bump
            base = fv.confidence * (1.0 if known else 0.8)
            entry["confs"].append(base)
            entry["known"] = entry["known"] or known
    skills: List[Skill] = []
    for name, entry in by_name.items():
        n_sources = len(entry["sources"])
        c = conf.agreement_boost(max(entry["confs"]), n_sources)
        skills.append(Skill(name=name, confidence=c, sources=sorted(entry["sources"])))
    # Deterministic: highest confidence first, then name.
    skills.sort(key=lambda s: (-s.confidence, s.name))
    agg = conf.aggregate([s.confidence for s in skills]) if skills else 0.0
    return skills, agg


def _merge_dicts(values: List[FieldValue], key) -> List[Dict]:
    """Dedupe dict-valued entries by ``key``, keeping the most complete one."""
    chosen: Dict = {}
    for fv in values:
        d = fv.value
        k = key(d)
        completeness = sum(1 for v in d.values() if v)
        if k not in chosen or completeness > chosen[k][0]:
            chosen[k] = (completeness, fv.confidence, d)
    # Deterministic order: by key tuple.
    return [chosen[k][2] for k in sorted(chosen, key=lambda x: (str(x),))]
