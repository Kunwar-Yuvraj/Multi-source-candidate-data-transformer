"""Output configuration model + loader.

The configuration reshapes the output without any code changes. It is validated
on load so a bad config fails fast with a clear message.

Config shape::

    {
      "fields": [
        {"path": "full_name", "type": "string", "required": true},
        {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
        {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
        {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
      ],
      "include_confidence": true,
      "include_provenance": false,
      "on_missing": "null"        # one of: null | omit | error
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

VALID_ON_MISSING = {"null", "omit", "error"}
VALID_NORMALIZE = {None, "E164", "canonical", "lower", "upper", "iso_country", "yyyy_mm"}
VALID_TYPES = {
    "string", "number", "integer", "boolean", "object",
    "string[]", "number[]", "object[]", "any",
}


class ConfigError(ValueError):
    pass


@dataclass
class FieldSpec:
    path: str                       # output key (may be dotted for nesting)
    source: Optional[str] = None    # canonical path expression ("from")
    type: str = "any"
    required: bool = False
    normalize: Optional[str] = None
    default: object = None          # value to use when missing and on_missing=null

    @property
    def from_path(self) -> str:
        return self.source or self.path


@dataclass
class OutputConfig:
    fields: List[FieldSpec] = field(default_factory=list)
    include_confidence: bool = False
    include_provenance: bool = False
    on_missing: str = "null"

    @staticmethod
    def default() -> "OutputConfig":
        """The default config emits the full canonical schema unchanged."""
        return OutputConfig(fields=[], include_confidence=True,
                            include_provenance=True, on_missing="null")

    @property
    def is_passthrough(self) -> bool:
        return not self.fields


def _parse_field(raw: dict, idx: int) -> FieldSpec:
    if not isinstance(raw, dict):
        raise ConfigError(f"fields[{idx}] must be an object")
    if "path" not in raw:
        raise ConfigError(f"fields[{idx}] missing required 'path'")
    ftype = raw.get("type", "any")
    if ftype not in VALID_TYPES:
        raise ConfigError(f"fields[{idx}] has unknown type {ftype!r}")
    norm = raw.get("normalize")
    if norm not in VALID_NORMALIZE:
        raise ConfigError(f"fields[{idx}] has unknown normalize {norm!r}")
    return FieldSpec(
        path=raw["path"],
        source=raw.get("from"),
        type=ftype,
        required=bool(raw.get("required", False)),
        normalize=norm,
        default=raw.get("default"),
    )


def parse_config(data: dict) -> OutputConfig:
    if not isinstance(data, dict):
        raise ConfigError("config root must be an object")
    on_missing = data.get("on_missing", "null")
    if on_missing not in VALID_ON_MISSING:
        raise ConfigError(
            f"on_missing must be one of {sorted(VALID_ON_MISSING)}, got {on_missing!r}"
        )
    raw_fields = data.get("fields", [])
    if not isinstance(raw_fields, list):
        raise ConfigError("'fields' must be a list")
    fields = [_parse_field(f, i) for i, f in enumerate(raw_fields)]
    return OutputConfig(
        fields=fields,
        include_confidence=bool(data.get("include_confidence", False)),
        include_provenance=bool(data.get("include_provenance", False)),
        on_missing=on_missing,
    )


def load_config(path: Optional[str]) -> OutputConfig:
    if not path:
        return OutputConfig.default()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_config(data)
