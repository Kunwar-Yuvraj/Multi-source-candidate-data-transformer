"""Confidence scoring.

Confidence is a number in [0, 1] expressing how much we trust a value. It is a
deterministic function of:

* the *source* it came from (structured recruiter data > parsed free text),
* the *method* used to extract it (a labeled column > a regex guess),
* *agreement* across sources (independent corroboration raises confidence).

This is intentionally simple and explainable -- no learned weights -- so every
score can be defended.
"""

from __future__ import annotations

from typing import Iterable

from .models import source_trust

# Method reliability multipliers applied on top of source trust.
METHOD_MULTIPLIER = {
    "column": 1.0,        # labeled CSV column
    "field": 0.95,        # labeled structured field (ATS/json)
    "regex": 0.75,        # regex match in free text
    "section": 0.7,       # parsed from a resume section
    "heuristic": 0.55,    # positional / shape guess
}

DEFAULT_METHOD_MULT = 0.6


def _method_class(method: str) -> str:
    m = (method or "").lower()
    for key in METHOD_MULTIPLIER:
        if key in m:
            return key
    return "default"


def base_confidence(source: str, method: str) -> float:
    trust = source_trust(source) / 100.0
    mult = METHOD_MULTIPLIER.get(_method_class(method), DEFAULT_METHOD_MULT)
    return round(min(0.99, trust * mult), 4)


def agreement_boost(base: float, n_agreeing: int) -> float:
    """Raise confidence when multiple independent sources agree on a value."""
    if n_agreeing <= 1:
        return base
    boosted = base + 0.08 * (n_agreeing - 1)
    return round(min(0.99, boosted), 4)


def aggregate(field_confidences: Iterable[float]) -> float:
    vals = [c for c in field_confidences if c is not None]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)
