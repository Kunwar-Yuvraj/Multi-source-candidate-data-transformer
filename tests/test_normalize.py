from transformer.normalize import (
    canonical_skill,
    normalize_country,
    normalize_email,
    normalize_month,
    normalize_phone,
    normalize_year,
    parse_location,
)
from transformer.normalize.names import normalize_name, name_key


class TestEmails:
    def test_lowercases_and_trims(self):
        assert normalize_email("  Jane.DOE@Example.com ") == "jane.doe@example.com"

    def test_strips_mailto_and_brackets(self):
        assert normalize_email("<mailto:a@b.co>") == "a@b.co"

    def test_rejects_garbage(self):
        assert normalize_email("not-an-email") is None
        assert normalize_email("oops@") is None
        assert normalize_email("") is None
        assert normalize_email(None) is None


class TestPhones:
    def test_e164_with_country_code(self):
        assert normalize_phone("+1 415-555-0132") == "+14155550132"

    def test_e164_with_region_hint(self):
        assert normalize_phone("(415) 555-0132", default_region="US") == "+14155550132"

    def test_uk_number(self):
        assert normalize_phone("+44 20 7946 0958") == "+442079460958"

    def test_unparseable_returns_none(self):
        assert normalize_phone("call-me") is None
        assert normalize_phone("12345") is None  # too short / invalid
        assert normalize_phone(None) is None

    def test_no_region_no_guess(self):
        # local number with no country code and no region -> we refuse to guess
        assert normalize_phone("555-0132") is None


class TestDates:
    def test_iso_month(self):
        assert normalize_month("2021-03") == "2021-03"

    def test_month_name_year(self):
        assert normalize_month("Mar 2021") == "2021-03"
        assert normalize_month("January 2020") == "2020-01"

    def test_year_only(self):
        assert normalize_month("2018") == "2018"

    def test_present(self):
        assert normalize_month("present") == "present"
        assert normalize_month("Current") == "present"

    def test_garbage(self):
        assert normalize_month("someday") is None
        assert normalize_month(None) is None

    def test_year_extraction(self):
        assert normalize_year("Class of 2016") == 2016
        assert normalize_year("n/a") is None


class TestCountry:
    def test_aliases(self):
        assert normalize_country("USA") == "US"
        assert normalize_country("uk") == "GB"

    def test_alpha3(self):
        assert normalize_country("IND") == "IN"

    def test_full_name(self):
        assert normalize_country("Germany") == "DE"

    def test_unknown(self):
        assert normalize_country("Atlantis") is None
        assert normalize_country(None) is None

    def test_parse_location(self):
        loc = parse_location("San Francisco, CA, USA")
        assert loc == {"city": "San Francisco", "region": "CA", "country": "US"}

    def test_parse_location_no_country_guess(self):
        loc = parse_location("Bengaluru")
        assert loc["country"] is None
        assert loc["city"] == "Bengaluru"


class TestSkills:
    def test_known_aliases(self):
        assert canonical_skill("JS") == ("JavaScript", True)
        assert canonical_skill("react.js") == ("React", True)
        assert canonical_skill("k8s") == ("Kubernetes", True)

    def test_unknown_kept_verbatim(self):
        name, known = canonical_skill("Underwater Basket Weaving")
        assert name == "Underwater Basket Weaving"
        assert known is False


class TestNames:
    def test_collapses_whitespace(self):
        assert normalize_name("  jane   doe ") == "Jane Doe"

    def test_rejects_email_like(self):
        assert normalize_name("a@b.com") is None

    def test_key_is_stable(self):
        assert name_key("Jane Doe") == name_key("JANE  DOE")
