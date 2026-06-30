"""Command-line interface.

Examples::

    python -m transformer --inputs samples/ --config config/default.json --pretty
    python -m transformer --inputs samples/ --config config/custom_example.json \
        --out output/custom.json
    python -m transformer --inputs samples/ --emit-canonical --out output/canonical.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List

from .config import ConfigError, OutputConfig, load_config
from .pipeline import run_pipeline
from .project import ProjectionError
from .validate import ValidationError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transformer",
        description="Multi-source candidate data transformer",
    )
    p.add_argument(
        "--inputs", "-i", nargs="+", required=True,
        help="Input files and/or directories (CSV, ATS JSON, resumes, notes).",
    )
    p.add_argument(
        "--config", "-c", default=None,
        help="Path to an output config JSON. Omit for the default canonical schema.",
    )
    p.add_argument(
        "--out", "-o", default=None,
        help="Write resulting JSON here. Omit to print to stdout.",
    )
    p.add_argument(
        "--emit-canonical", action="store_true",
        help="Emit the full canonical profiles, ignoring --config projection.",
    )
    p.add_argument(
        "--no-validate", action="store_true",
        help="Skip output schema validation (not recommended).",
    )
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    p.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity for pipeline warnings.",
    )
    return p


def main(argv: List[str] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        config = OutputConfig.default() if args.emit_canonical else load_config(args.config)
    except (ConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"error: bad config: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_pipeline(
            inputs=args.inputs,
            config=config,
            validate=not args.no_validate,
        )
    except (ProjectionError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = result.outputs
    indent = 2 if args.pretty else None
    text = json.dumps(payload, indent=indent, ensure_ascii=False, sort_keys=False)

    if args.out:
        import os
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(
            f"wrote {len(payload)} profile(s) to {args.out}", file=sys.stderr
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
