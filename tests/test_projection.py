import pytest

from transformer.config import OutputConfig, parse_config
from transformer.project import MISSING, ProjectionError, project, resolve_path

PROFILE = {
    "full_name": "Jane Doe",
    "emails": ["jane@x.com", "j@y.com"],
    "phones": ["+14155550132"],
    "location": {"city": "SF", "region": "CA", "country": "US"},
    "links": {"linkedin": "https://linkedin.com/in/jane", "github": None, "portfolio": None, "other": []},
    "skills": [{"name": "Python", "confidence": 0.9, "sources": ["csv"]},
               {"name": "React", "confidence": 0.8, "sources": ["ats"]}],
    "experience": [{"company": "Acme", "title": "SWE", "start": "2021-03", "end": "present"}],
    "overall_confidence": 0.82,
    "field_confidence": {"full_name": 0.9, "emails": 0.85, "skills": 0.85},
}


class TestPathResolution:
    def test_scalar(self):
        assert resolve_path(PROFILE, "full_name") == "Jane Doe"

    def test_nested(self):
        assert resolve_path(PROFILE, "location.country") == "US"

    def test_index(self):
        assert resolve_path(PROFILE, "emails[0]") == "jane@x.com"

    def test_index_out_of_range(self):
        assert resolve_path(PROFILE, "phones[5]") is MISSING

    def test_list_subfield(self):
        assert resolve_path(PROFILE, "skills[].name") == ["Python", "React"]

    def test_object_index_subfield(self):
        assert resolve_path(PROFILE, "experience[0].company") == "Acme"

    def test_missing(self):
        assert resolve_path(PROFILE, "nope") is MISSING
        assert resolve_path(PROFILE, "location.zip") is MISSING


class TestProjection:
    def test_basic_projection_and_rename(self):
        cfg = parse_config({
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        })
        out = project(PROFILE, cfg)
        assert out == {"full_name": "Jane Doe", "primary_email": "jane@x.com"}

    def test_normalize_canonical_list(self):
        cfg = parse_config({
            "fields": [{"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}],
        })
        out = project(PROFILE, cfg)
        assert out["skills"] == ["Python", "React"]

    def test_normalize_e164(self):
        cfg = parse_config({"fields": [{"path": "p", "from": "phones[0]", "normalize": "E164"}]})
        assert project(PROFILE, cfg)["p"] == "+14155550132"

    def test_on_missing_null(self):
        cfg = parse_config({"fields": [{"path": "gh", "from": "links.github"}], "on_missing": "null"})
        assert project(PROFILE, cfg) == {"gh": None}

    def test_on_missing_omit(self):
        cfg = parse_config({"fields": [{"path": "gh", "from": "links.github"}], "on_missing": "omit"})
        assert project(PROFILE, cfg) == {}

    def test_on_missing_error(self):
        cfg = parse_config({"fields": [{"path": "gh", "from": "links.github"}], "on_missing": "error"})
        with pytest.raises(ProjectionError):
            project(PROFILE, cfg)

    def test_required_missing_raises(self):
        cfg = parse_config({"fields": [{"path": "gh", "from": "links.github", "required": True}], "on_missing": "null"})
        with pytest.raises(ProjectionError):
            project(PROFILE, cfg)

    def test_nested_output_path(self):
        cfg = parse_config({"fields": [{"path": "contact.email", "from": "emails[0]"}]})
        assert project(PROFILE, cfg) == {"contact": {"email": "jane@x.com"}}

    def test_confidence_included(self):
        cfg = parse_config({
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": True,
        })
        out = project(PROFILE, cfg)
        assert out["overall_confidence"] == 0.82
        assert out["confidence"]["full_name"] == 0.9

    def test_passthrough_drops_confidence_when_off(self):
        cfg = OutputConfig(fields=[], include_confidence=False, include_provenance=False)
        out = project(PROFILE, cfg)
        assert "overall_confidence" not in out
        assert "field_confidence" not in out
