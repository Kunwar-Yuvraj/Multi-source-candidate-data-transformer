"""Email normalization: lowercase, trim, validate shape, dedupe (order-stable)."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

# Intentionally conservative: we only accept things that clearly look like an
# email. Anything ambiguous becomes None rather than a guessed value.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = value.strip().strip("<>").lower()
    # strip a leading mailto:
    if candidate.startswith("mailto:"):
        candidate = candidate[len("mailto:"):]
    if _EMAIL_RE.match(candidate):
        return candidate
    return None


def normalize_emails(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        norm = normalize_email(v)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out
