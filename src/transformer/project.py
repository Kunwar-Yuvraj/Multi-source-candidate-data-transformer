"""Projection layer.

Reads from the canonical profile (as a dict) and produces the configured output.
This is the ONLY place that knows about the output shape; the canonical record is
oblivious to it. That separation is what lets one engine serve many configs.

Includes a small path mini-language for the ``from`` expressions:

* ``full_name``            -> scalar field
* ``location.city``        -> nested field
* ``emails[0]``            -> indexed list element
* ``skills[].name``        -> project a subfield across a list
* ``experience[].company`` -> same, for objects
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import FieldSpec, OutputConfig
from .normalize import (
    canonical_skill,
    normalize_country,
    normalize_month,
    normalize_phone,
)


class ProjectionError(ValueError):
    pass


class _Missing:
    _instance = None

    def __repr__(self):  # pragma: no cover
        return "<MISSING>"


MISSING = _Missing()

_TOKEN_RE = re.compile(r"^([A-Za-z0-9_]+)(?:\[(\d*)\])?$")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def resolve_path(data: Any, expr: str) -> Any:
    """Resolve a path expression against ``data``; returns MISSING if absent."""
    tokens = expr.split(".")
    return _resolve(data, tokens)


def _resolve(obj: Any, tokens: List[str]) -> Any:
    if not tokens:
        return obj
    tok, rest = tokens[0], tokens[1:]
    m = _TOKEN_RE.match(tok)
    if not m:
        return MISSING
    name, index = m.group(1), m.group(2)
    if not isinstance(obj, dict) or name not in obj:
        return MISSING
    val = obj[name]
    if index is None:
        return _resolve(val, rest)
    # bracketed access
    if not isinstance(val, list):
        return MISSING
    if index == "":
        results = []
        for el in val:
            r = _resolve(el, rest)
            if r is not MISSING and r is not None:
                results.append(r)
        return results
    i = int(index)
    if i < 0 or i >= len(val):
        return MISSING
    return _resolve(val[i], rest)


# ---------------------------------------------------------------------------
# Per-field normalization (applied during projection)
# ---------------------------------------------------------------------------


def _apply_normalize(value: Any, norm: Optional[str]) -> Any:
    if value is None or value is MISSING or norm is None:
        return value
    if isinstance(value, list):
        out = [_apply_scalar_norm(v, norm) for v in value]
        return [v for v in out if v is not None]
    return _apply_scalar_norm(value, norm)


def _apply_scalar_norm(value: Any, norm: str) -> Any:
    if value is None:
        return None
    if norm == "E164":
        return normalize_phone(str(value))
    if norm == "canonical":
        return canonical_skill(str(value))[0]
    if norm == "iso_country":
        return normalize_country(str(value))
    if norm == "yyyy_mm":
        return normalize_month(str(value))
    if norm == "lower":
        return str(value).lower()
    if norm == "upper":
        return str(value).upper()
    return value


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------


def _set_nested(out: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _is_empty(value: Any) -> bool:
    return value is MISSING or value is None or value == []


def project(profile_dict: Dict[str, Any], config: OutputConfig) -> Dict[str, Any]:
    """Project a canonical profile dict into the configured output shape."""
    if config.is_passthrough:
        return _project_passthrough(profile_dict, config)

    out: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}
    field_conf = profile_dict.get("field_confidence", {})

    for spec in config.fields:
        raw_value = resolve_path(profile_dict, spec.from_path)
        value = _apply_normalize(raw_value, spec.normalize)

        if _is_empty(value):
            if spec.required:
                raise ProjectionError(
                    f"required output field '{spec.path}' (from '{spec.from_path}') "
                    f"is missing"
                )
            if config.on_missing == "error":
                raise ProjectionError(
                    f"output field '{spec.path}' (from '{spec.from_path}') is missing "
                    f"and on_missing='error'"
                )
            if config.on_missing == "omit":
                continue
            value = spec.default  # on_missing == "null"

        _set_nested(out, spec.path, value)

        if config.include_confidence:
            root = spec.from_path.split(".")[0].split("[")[0]
            if root in field_conf:
                confidences[spec.path] = field_conf[root]

    if config.include_confidence:
        out["overall_confidence"] = profile_dict.get("overall_confidence")
        if confidences:
            out["confidence"] = confidences
    if config.include_provenance:
        out["provenance"] = profile_dict.get("provenance", [])

    return out


def _project_passthrough(profile_dict: Dict[str, Any], config: OutputConfig) -> Dict[str, Any]:
    out = {k: v for k, v in profile_dict.items() if k != "field_confidence"}
    if not config.include_confidence:
        out.pop("overall_confidence", None)
    if not config.include_provenance:
        out.pop("provenance", None)
    return out
