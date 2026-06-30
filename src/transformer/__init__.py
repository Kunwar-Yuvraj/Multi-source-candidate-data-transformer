"""Multi-source candidate data transformer.

Turns messy multi-source candidate inputs into one canonical profile per
candidate, then projects that profile into a configurable output schema.
"""

__version__ = "0.1.0"

from .pipeline import run_pipeline, Pipeline  # noqa: E402,F401
