"""Normalization helpers.

Every normalizer is total and pure: given any input it returns either a clean
canonical value or ``None``. They never raise on bad input and never invent
values. This is what keeps the pipeline deterministic and "honestly empty"
rather than "wrong but confident".
"""

from .emails import normalize_email, normalize_emails  # noqa: F401
from .phones import normalize_phone, normalize_phones  # noqa: F401
from .dates import normalize_month, normalize_year  # noqa: F401
from .country import normalize_country, parse_location  # noqa: F401
from .skills import canonical_skill, canonical_skills  # noqa: F401
from .names import normalize_name  # noqa: F401
