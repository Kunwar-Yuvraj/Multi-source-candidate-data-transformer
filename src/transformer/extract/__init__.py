"""Source extractors.

Each extractor takes a path (or url) and yields ``RawRecord`` objects. Extractors
must be robust: a malformed file or row produces a warning and is skipped, never
an exception that crashes the pipeline.
"""

from .csv_source import extract_csv  # noqa: F401
from .ats_json import extract_ats_json  # noqa: F401
from .resume import extract_resume  # noqa: F401
