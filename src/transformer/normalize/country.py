"""Location / country normalization.

Country is emitted as ISO-3166 alpha-2. We resolve from alpha-2, alpha-3, full
names, and a small alias table (USA, UK, ...). Unresolvable -> None.
"""

from __future__ import annotations

from typing import Dict, Optional

import pycountry

# Common informal names that pycountry's fuzzy search gets wrong or slow.
_ALIASES: Dict[str, str] = {
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "us": "US",
    "united states": "US",
    "united states of america": "US",
    "america": "US",
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "uae": "AE",
    "south korea": "KR",
    "north korea": "KP",
    "russia": "RU",
    "bharat": "IN",
}

# A few well-known US state abbreviations -> kept as region only (not country).
_US_STATES = {
    "ca", "ny", "tx", "wa", "ma", "fl", "il", "wi", "ga", "co", "or", "nj",
    "va", "pa", "nc", "az", "mi", "oh", "mn",
}


def normalize_country(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    key = raw.lower()
    if key in _ALIASES:
        return _ALIASES[key]
    # alpha-2
    if len(raw) == 2:
        rec = pycountry.countries.get(alpha_2=raw.upper())
        if rec:
            return rec.alpha_2
    # alpha-3
    if len(raw) == 3:
        rec = pycountry.countries.get(alpha_3=raw.upper())
        if rec:
            return rec.alpha_2
    # full name (exact)
    rec = pycountry.countries.get(name=raw)
    if rec:
        return rec.alpha_2
    # fuzzy as last resort
    try:
        matches = pycountry.countries.search_fuzzy(raw)
        if matches:
            return matches[0].alpha_2
    except LookupError:
        pass
    return None


def parse_location(value: Optional[str]) -> Dict[str, Optional[str]]:
    """Parse a free-text location like "San Francisco, CA, USA".

    Returns a dict with city/region/country; any part we cannot determine is
    None. We never fabricate a country from a city name.
    """

    result: Dict[str, Optional[str]] = {"city": None, "region": None, "country": None}
    if not value:
        return result
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if not parts:
        return result

    # Try to peel a country off the last part.
    if len(parts) >= 1:
        country = normalize_country(parts[-1])
        if country is not None:
            result["country"] = country
            parts = parts[:-1]

    if len(parts) == 1:
        # Could be "City" or "Region"; treat a known US state token as region.
        token = parts[0]
        if token.lower() in _US_STATES:
            result["region"] = token.upper()
        else:
            result["city"] = token
    elif len(parts) >= 2:
        result["city"] = parts[0]
        region = parts[1]
        result["region"] = region.upper() if region.lower() in _US_STATES else region
    return result
