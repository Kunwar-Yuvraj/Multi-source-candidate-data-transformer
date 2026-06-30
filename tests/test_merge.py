from transformer.models import RawRecord
from transformer.pipeline import build_profiles


def _csv_jane():
    r = RawRecord(source="recruiter_csv", source_ref="csv#1")
    r.full_name = "Jane Doe"
    r.emails = ["jane.doe@example.com"]
    r.phones = ["+1 415-555-0132"]
    r.skills = ["JS", "Python"]
    r.method_map = {
        "full_name": "recruiter_csv:column:name",
        "skills": "recruiter_csv:column:skills",
    }
    return r


def _ats_jane():
    r = RawRecord(source="ats_json", source_ref="ats#0")
    r.full_name = "Jane A. Doe"
    r.emails = ["jane.doe@example.com"]
    r.skills = ["React.js", "Python"]
    return r


def _resume_other():
    r = RawRecord(source="resume", source_ref="resume#1")
    r.full_name = "Bob Stone"
    r.emails = ["bob@example.com"]
    return r


class TestClusteringAndMerge:
    def test_same_email_merges(self):
        profiles = build_profiles([_csv_jane(), _ats_jane(), _resume_other()])
        assert len(profiles) == 2
        jane = [p for p in profiles if "jane.doe@example.com" in p.emails][0]
        # canonical name from highest-trust source (csv) wins
        assert jane.full_name == "Jane Doe"

    def test_skill_dedup_and_corroboration(self):
        profiles = build_profiles([_csv_jane(), _ats_jane()])
        jane = profiles[0]
        names = {s.name for s in jane.skills}
        assert "Python" in names and "JavaScript" in names and "React" in names
        python = [s for s in jane.skills if s.name == "Python"][0]
        # corroborated by two sources -> higher confidence than single-source
        assert len(python.sources) == 2
        assert python.confidence > 0.8

    def test_phone_normalized_in_profile(self):
        profiles = build_profiles([_csv_jane()])
        assert profiles[0].phones == ["+14155550132"]

    def test_provenance_present_for_every_field(self):
        profiles = build_profiles([_csv_jane(), _ats_jane()])
        jane = profiles[0]
        fields_with_prov = {p.field for p in jane.provenance}
        assert {"full_name", "emails", "skills"} <= fields_with_prov

    def test_no_identity_dropped(self):
        junk = RawRecord(source="recruiter_csv", source_ref="csv#x")
        junk.skills = ["bogus"]
        profiles = build_profiles([junk])
        assert profiles == []
