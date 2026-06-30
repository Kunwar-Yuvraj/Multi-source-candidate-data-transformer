"""Internal data models.

There are two layers, kept deliberately separate:

* ``RawRecord``      -- whatever an extractor pulled out of a single source,
                        before normalization and before merging.
* ``CanonicalProfile`` -- the merged, normalized, deterministic profile for one
                        candidate. The projection layer reads from this.

Keeping the canonical record independent from the output projection is what lets
the same engine emit many different output shapes with no code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Source / provenance primitives
# ---------------------------------------------------------------------------

# Trust ranking for sources. Higher = more trusted when resolving conflicts.
# Structured, recruiter-maintained data outranks free text we parsed ourselves.
SOURCE_TRUST: Dict[str, int] = {
    "recruiter_csv": 90,
    "ats_json": 85,
    "resume": 60,
}

DEFAULT_TRUST = 30


def source_trust(source: str) -> int:
    return SOURCE_TRUST.get(source, DEFAULT_TRUST)


@dataclass(frozen=True)
class Provenance:
    """Where a single value came from and how it was obtained."""

    field: str
    source: str          # e.g. "recruiter_csv"
    method: str          # e.g. "csv_column:phone", "regex:email"

    def to_dict(self) -> Dict[str, str]:
        return {"field": self.field, "source": self.source, "method": self.method}


@dataclass
class FieldValue:
    """A single candidate value for a field, with its provenance + confidence.

    The merge step collects many ``FieldValue`` objects per field and selects a
    winner; all candidates (winning and losing) survive in provenance so the
    result stays explainable.
    """

    value: Any
    source: str
    method: str
    confidence: float = 0.5

    def provenance(self, field_name: str) -> Provenance:
        return Provenance(field=field_name, source=self.source, method=self.method)


# ---------------------------------------------------------------------------
# Raw record (post-extract, pre-normalize/merge)
# ---------------------------------------------------------------------------


@dataclass
class RawRecord:
    """One candidate-ish blob from a single source.

    Fields use canonical-ish keys where the extractor can map them, but values
    are *not yet normalized*. ``source``/``method_map`` carry provenance so we
    never lose track of where anything came from.
    """

    source: str
    source_ref: str = ""          # file path / url / row id, for debugging
    # Scalar-ish fields (values are raw strings or simple structures)
    full_name: Optional[str] = None
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location_raw: Optional[str] = None
    location: Dict[str, Optional[str]] = field(default_factory=dict)
    links: Dict[str, Any] = field(default_factory=dict)
    headline: Optional[str] = None
    current_company: Optional[str] = None
    title: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[str] = field(default_factory=list)
    experience: List[Dict[str, Any]] = field(default_factory=list)
    education: List[Dict[str, Any]] = field(default_factory=list)
    # method_map: field name -> extraction method string (for provenance)
    method_map: Dict[str, str] = field(default_factory=dict)

    def method_for(self, field_name: str, default: str = "") -> str:
        return self.method_map.get(field_name, default or f"{self.source}:field")


# ---------------------------------------------------------------------------
# Canonical profile (post-merge)
# ---------------------------------------------------------------------------


@dataclass
class Skill:
    name: str
    confidence: float
    sources: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "confidence": round(self.confidence, 4),
            "sources": sorted(set(self.sources)),
        }


@dataclass
class CanonicalProfile:
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location: Dict[str, Optional[str]] = field(
        default_factory=lambda: {"city": None, "region": None, "country": None}
    )
    links: Dict[str, Any] = field(
        default_factory=lambda: {
            "linkedin": None,
            "github": None,
            "portfolio": None,
            "other": [],
        }
    )
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = field(default_factory=list)
    experience: List[Dict[str, Any]] = field(default_factory=list)
    education: List[Dict[str, Any]] = field(default_factory=list)
    provenance: List[Provenance] = field(default_factory=list)
    overall_confidence: float = 0.0
    # field -> confidence, kept internal (not part of the spec output) so the
    # projection layer can attach per-field confidence when asked.
    field_confidence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self, include_field_confidence: bool = False) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "full_name": self.full_name,
            "emails": list(self.emails),
            "phones": list(self.phones),
            "location": dict(self.location),
            "links": {
                "linkedin": self.links.get("linkedin"),
                "github": self.links.get("github"),
                "portfolio": self.links.get("portfolio"),
                "other": list(self.links.get("other", [])),
            },
            "headline": self.headline,
            "years_experience": self.years_experience,
            "skills": [s.to_dict() for s in self.skills],
            "experience": list(self.experience),
            "education": list(self.education),
            "provenance": [p.to_dict() for p in self.provenance],
            "overall_confidence": round(self.overall_confidence, 4),
        }
        if include_field_confidence:
            out["field_confidence"] = {
                k: round(v, 4) for k, v in self.field_confidence.items()
            }
        return out
