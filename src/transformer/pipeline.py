"""End-to-end orchestration: detect -> extract -> normalize -> merge ->
confidence -> project -> validate.

Designed to stream: extractors yield records lazily and clustering uses an
O(n) hash index, so a single run can handle thousands of candidates.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from .config import OutputConfig
from .detect import detect_source, get_extractor
from .merge import build_profile, cluster_records, normalize_record
from .models import CanonicalProfile, RawRecord
from .project import project
from .validate import validate_canonical, validate_projected

log = logging.getLogger(__name__)

_DATA_EXTS = {".csv", ".json", ".pdf"}


@dataclass
class PipelineResult:
    profiles: List[CanonicalProfile] = field(default_factory=list)
    outputs: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _expand_inputs(inputs: List[str]) -> List[str]:
    """Expand directories into the data files they contain (sorted, stable)."""
    specs: List[str] = []
    for item in inputs:
        if os.path.isdir(item):
            for root, _dirs, files in os.walk(item):
                for fn in sorted(files):
                    if os.path.splitext(fn)[1].lower() in _DATA_EXTS:
                        specs.append(os.path.join(root, fn))
        else:
            specs.append(item)
    # Deterministic processing order.
    return sorted(specs)


def extract_all(inputs: List[str]) -> Iterator[RawRecord]:
    for spec in _expand_inputs(inputs):
        source = detect_source(spec)
        if source is None:
            log.warning("skip: could not detect source type for %s", spec)
            continue
        extractor = get_extractor(source)
        if extractor is None:
            log.warning("skip: no extractor for source %s (%s)", source, spec)
            continue
        try:
            yield from extractor(spec)
        except Exception as exc:  # last-resort guard; extractors handle their own
            log.warning("extractor crashed on %s: %s", spec, exc)


def _has_identity(profile: CanonicalProfile) -> bool:
    """A real candidate must have at least one identifying signal.

    Drops junk clusters (e.g. a malformed row that yielded only a stray skill)
    rather than emitting an anonymous profile.
    """
    return bool(profile.full_name or profile.emails or profile.phones)


def build_profiles(raw_records: List[RawRecord]) -> List[CanonicalProfile]:
    normalized = [normalize_record(r) for r in raw_records]
    clusters = cluster_records(normalized)
    profiles = [build_profile(group) for group in clusters]
    return [p for p in profiles if _has_identity(p)]


class Pipeline:
    def __init__(self, config: Optional[OutputConfig] = None):
        self.config = config or OutputConfig.default()

    def run(self, inputs: List[str], validate: bool = True) -> PipelineResult:
        raw = list(extract_all(inputs))
        profiles = build_profiles(raw)
        result = PipelineResult(profiles=profiles)
        for profile in profiles:
            pdict = profile.to_dict(include_field_confidence=True)
            if validate:
                # Validate the canonical record (without the internal-only field).
                canonical_public = {k: v for k, v in pdict.items() if k != "field_confidence"}
                validate_canonical(canonical_public)
            output = project(pdict, self.config)
            if validate:
                validate_projected(output, self.config)
            result.outputs.append(output)
        return result


def run_pipeline(inputs: List[str], config: Optional[OutputConfig] = None,
                 validate: bool = True) -> PipelineResult:
    return Pipeline(config=config).run(inputs, validate=validate)
