"""Phone normalization to E.164 using the ``phonenumbers`` library.

If a number has no country code and no default region can be inferred, we return
None instead of guessing a region -- a wrong phone number is worse than an empty
one.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import phonenumbers


def normalize_phone(
    value: Optional[str], default_region: Optional[str] = None
) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # Try as-is first (handles +country-code numbers regardless of region).
    candidates = [None]
    if default_region:
        candidates.append(default_region)
    for region in candidates:
        try:
            parsed = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
    return None


def normalize_phones(
    values: Iterable[str], default_region: Optional[str] = None
) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        norm = normalize_phone(v, default_region=default_region)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out
