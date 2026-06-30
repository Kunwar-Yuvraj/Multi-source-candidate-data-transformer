"""Output validation.

Two validators:

* ``validate_canonical`` -- checks the internal canonical profile against the
  fixed canonical JSON schema.
* ``schema_from_config`` + ``validate_projected`` -- derive a JSON schema from the
  runtime config and validate the projected output against it, so a config can
  never silently produce a malformed result.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import jsonschema

from .config import OutputConfig

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "canonical_schema.json")

_TYPE_MAP = {
    "string": {"type": ["string", "null"]},
    "number": {"type": ["number", "null"]},
    "integer": {"type": ["integer", "null"]},
    "boolean": {"type": ["boolean", "null"]},
    "object": {"type": ["object", "null"]},
    "any": {},
    "string[]": {"type": "array", "items": {"type": "string"}},
    "number[]": {"type": "array", "items": {"type": "number"}},
    "object[]": {"type": "array", "items": {"type": "object"}},
}


class ValidationError(ValueError):
    pass


def _load_canonical_schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_canonical(profile: Dict[str, Any]) -> None:
    schema = _load_canonical_schema()
    try:
        jsonschema.validate(profile, schema)
    except jsonschema.ValidationError as exc:
        raise ValidationError(f"canonical profile invalid: {exc.message}") from exc


def _nest_property(props: Dict[str, Any], required: List[str], path: str, subschema: Dict[str, Any]) -> None:
    parts = path.split(".")
    if len(parts) == 1:
        props[parts[0]] = subschema
        return
    head = parts[0]
    node = props.setdefault(head, {"type": "object", "properties": {}})
    node.setdefault("properties", {})
    _nest_property(node["properties"], [], ".".join(parts[1:]), subschema)


def schema_from_config(config: OutputConfig) -> Dict[str, Any]:
    if config.is_passthrough:
        return _load_canonical_schema()
    props: Dict[str, Any] = {}
    required: List[str] = []
    for spec in config.fields:
        sub = dict(_TYPE_MAP.get(spec.type, {}))
        # on_missing=null means the value may be null even for typed fields
        if config.on_missing == "null" and "type" in sub and isinstance(sub["type"], str):
            sub = {"type": [sub["type"], "null"]}
        _nest_property(props, required, spec.path, sub)
        if spec.required and "." not in spec.path:
            required.append(spec.path)
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": props,
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


def validate_projected(output: Dict[str, Any], config: OutputConfig) -> None:
    schema = schema_from_config(config)
    try:
        jsonschema.validate(output, schema)
    except jsonschema.ValidationError as exc:
        raise ValidationError(f"projected output invalid: {exc.message}") from exc
