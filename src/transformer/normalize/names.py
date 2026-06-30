"""Name normalization: collapse whitespace, strip noise, title-case carefully.

We avoid aggressive title-casing that would mangle names like "McDonald" or
"de la Cruz"; we only title-case tokens that are all-lower or all-upper.
"""

from __future__ import annotations

import re
from typing import Optional

_NOISE = re.compile(r"[\t\r\n]+")


def _fix_token(tok: str) -> str:
    if not tok:
        return tok
    if tok.islower() or tok.isupper():
        return tok[:1].upper() + tok[1:].lower()
    return tok  # leave mixed-case tokens (McDonald, DeWitt) alone


def normalize_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    s = _NOISE.sub(" ", str(value))
    s = re.sub(r"\s+", " ", s).strip(" ,;")
    if not s:
        return None
    # Drop obvious non-name artifacts
    if "@" in s or any(ch.isdigit() for ch in s):
        # names with digits/emails are almost certainly junk
        return None
    return " ".join(_fix_token(t) for t in s.split(" "))


def name_key(value: Optional[str]) -> str:
    """A normalized key for matching: lowercase, alnum-only, sorted-insensitive."""
    n = normalize_name(value)
    if not n:
        return ""
    return re.sub(r"[^a-z0-9]", "", n.lower())
