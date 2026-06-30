"""Skill canonicalization.

Maps noisy skill strings ("JS", "react.js", "nodejs") to canonical names
("JavaScript", "React", "Node.js") via an explicit alias table. Unknown skills
are *kept* (title-cased / cleaned) rather than dropped -- but the caller assigns
them lower confidence, so we never silently invent a known skill.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

# canonical name -> list of aliases (all matched case-insensitively)
_CANONICAL: Dict[str, List[str]] = {
    "JavaScript": ["js", "javascript", "java script", "ecmascript"],
    "TypeScript": ["ts", "typescript", "type script"],
    "Python": ["python", "py", "python3"],
    "Java": ["java", "core java"],
    "C++": ["c++", "cpp", "cplusplus"],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": ["go", "golang"],
    "Rust": ["rust", "rust-lang"],
    "React": ["react", "react.js", "reactjs", "react js"],
    "Node.js": ["node", "node.js", "nodejs", "node js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgres", "postgresql", "psql"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongo", "mongodb"],
    "Redis": ["redis"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Azure": ["azure", "microsoft azure"],
    "Machine Learning": ["ml", "machine learning"],
    "Deep Learning": ["dl", "deep learning"],
    "TensorFlow": ["tensorflow", "tf"],
    "PyTorch": ["pytorch", "torch"],
    "Kafka": ["kafka", "apache kafka"],
    "Spark": ["spark", "apache spark", "pyspark"],
    "GraphQL": ["graphql", "graph ql"],
    "REST": ["rest", "rest api", "restful"],
    "Git": ["git"],
    "Linux": ["linux"],
}

# Build reverse lookup once.
_ALIAS_TO_CANON: Dict[str, str] = {}
for canon, aliases in _CANONICAL.items():
    _ALIAS_TO_CANON[canon.lower()] = canon
    for a in aliases:
        _ALIAS_TO_CANON[a.lower()] = canon


def _clean(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.strip())
    return s


def canonical_skill(value: str) -> Tuple[str, bool]:
    """Return (canonical_name, is_known).

    ``is_known`` is True when we matched the alias table, False when we kept the
    cleaned input verbatim. Callers use this to lower confidence for unknowns.
    """

    if not value:
        return "", False
    cleaned = _clean(value)
    if not cleaned:
        return "", False
    canon = _ALIAS_TO_CANON.get(cleaned.lower())
    if canon:
        return canon, True
    # Unknown: keep a tidy version of the original, do not guess a known skill.
    return cleaned, False


def canonical_skills(values: Iterable[str]) -> List[Tuple[str, bool]]:
    out: List[Tuple[str, bool]] = []
    seen = set()
    for v in values:
        name, known = canonical_skill(v)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append((name, known))
    return out
