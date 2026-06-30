import json
import os

import pytest

from transformer.config import OutputConfig, load_config
from transformer.pipeline import run_pipeline
from transformer.validate import validate_canonical

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(HERE, "samples")
CONFIG = os.path.join(HERE, "config")


def _run_default():
    return run_pipeline([SAMPLES], config=OutputConfig.default())


class TestEndToEnd:
    def test_three_candidates(self):
        result = _run_default()
        assert len(result.profiles) == 3
        names = sorted(p.full_name for p in result.profiles)
        assert names == ["Jane Doe", "John Smith", "Priya Sharma"]

    def test_jane_merged_across_sources(self):
        result = _run_default()
        jane = [p for p in result.profiles if p.full_name == "Jane Doe"][0]
        sources = {pr.source for pr in jane.provenance}
        # structured + unstructured both contributed
        assert "recruiter_csv" in sources
        assert "ats_json" in sources
        assert "resume" in sources
        assert jane.location == {"city": "San Francisco", "region": "CA", "country": "US"}
        assert jane.phones == ["+14155550132"]

    def test_canonical_outputs_validate(self):
        result = _run_default()
        for out in result.outputs:
            validate_canonical(out)

    def test_deterministic(self):
        a = _run_default().outputs
        b = _run_default().outputs
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_custom_config_runs_and_validates(self):
        cfg = load_config(os.path.join(CONFIG, "custom_example.json"))
        result = run_pipeline([SAMPLES], config=cfg)
        jane = [o for o in result.outputs if o["full_name"] == "Jane Doe"][0]
        assert jane["primary_email"] == "jane.doe@example.com"
        assert jane["phone"] == "+14155550132"
        assert jane["country"] == "US"
        assert "Python" in jane["skills"]


class TestRobustness:
    def test_malformed_inputs_do_not_crash(self):
        # samples include a malformed JSON and a junk CSV row; pipeline survives.
        result = _run_default()
        assert len(result.profiles) == 3

    def test_missing_path_is_fine(self):
        result = run_pipeline(["/does/not/exist"], config=OutputConfig.default())
        assert result.profiles == []

    def test_on_missing_error_raises(self):
        from transformer.config import parse_config
        from transformer.project import ProjectionError
        # portfolio is null for every sample candidate -> error mode must raise
        cfg = parse_config({
            "fields": [{"path": "portfolio", "from": "links.portfolio"}],
            "on_missing": "error",
        })
        with pytest.raises(ProjectionError):
            run_pipeline([SAMPLES], config=cfg)
