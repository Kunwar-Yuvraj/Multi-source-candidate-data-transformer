# Multi-Source Candidate Data Transformer

Turns messy candidate data from many sources into **one clean, canonical profile
per candidate** — normalized, deduplicated across sources, with full
**provenance** (where each value came from) and **confidence** (how much we trust
it). A runtime configuration reshapes the output without any code changes.

Guiding principle: **wrong-but-confident is worse than honestly-empty.** Unknown
values become `null`; we never invent data, and every value is traceable.

---

## Quick start

```bash
# 1. create a virtualenv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. run on the sample inputs (default canonical schema)
PYTHONPATH=src python -m transformer --inputs samples/ --config config/default.json --pretty

# 3. run with a custom output config
PYTHONPATH=src python -m transformer --inputs samples/ --config config/custom_example.json --out output/custom.json --pretty
```

If you `pip install -e .`, the console script `candidate-transformer` is also
available and you can drop the `PYTHONPATH=src` prefix.

### CLI options

```
--inputs, -i     Input files and/or directories (required). Dirs are scanned.
--config, -c     Output config JSON. Omit for the default canonical schema.
--out, -o        Write JSON here. Omit to print to stdout.
--emit-canonical Emit full canonical profiles, ignoring --config projection.
--no-validate    Skip output schema validation (not recommended).
--pretty         Pretty-print JSON.
--log-level      DEBUG | INFO | WARNING | ERROR (default WARNING).
```

---

## Supported sources

| Group | Source | Extractor |
|-------|--------|-----------|
| Structured | Recruiter CSV | `extract/csv_source.py` |
| Structured | ATS JSON blob (own field names) | `extract/ats_json.py` |
| Unstructured | Resume PDF | `extract/resume.py` |

Any source may be missing, empty, or malformed; the pipeline logs a warning and
continues. Sample inputs deliberately include a malformed JSON and a junk CSV row.

---

## How it works

```
detect -> extract -> normalize -> merge -> confidence -> project -> validate
```

1. **detect** (`detect.py`) — identify each input's source type by extension.
2. **extract** (`extract/`) — per-source parsers emit `RawRecord`s carrying raw
   values plus `{source, method}` provenance metadata. Robust to malformed input.
3. **normalize** (`normalize/`) — total, pure functions convert values to
   canonical formats (E.164 phones, `YYYY-MM` dates, ISO-3166 alpha-2 countries,
   canonical skill names). Anything unparseable becomes `null`.
4. **merge** (`merge.py`) — cluster records into candidates (union-find over
   email / phone / name+company), resolve per-field conflicts by source trust
   then confidence, union list fields, and record every contributing value in
   provenance.
5. **confidence** (`confidence.py`) — deterministic score from source trust ×
   method reliability, boosted when independent sources agree.
6. **project** (`project.py`) — the configurable layer; reshapes the canonical
   profile into the requested output. The canonical record never knows about the
   output shape.
7. **validate** (`validate.py`) — the canonical record is checked against
   `canonical_schema.json`; the projected output against a schema derived from
   the config.

Key normalization formats: phones **E.164**, dates **YYYY-MM**, country
**ISO-3166 alpha-2**, skills **canonical names** (alias table). The canonical
schema is in [`src/transformer/canonical_schema.json`](src/transformer/canonical_schema.json).

---

## The configurable output (Required Twist)

A config JSON reshapes the output with **no code changes**. It can select/rename
fields, remap from a canonical path (`from`), apply per-field normalization,
toggle confidence/provenance, and choose missing-value behavior.

```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

- **Path mini-language** for `from`: `full_name`, `location.country`, `emails[0]`,
  `skills[].name`, `experience[0].title`.
- **`on_missing`**: `null` (emit null), `omit` (drop the key), or `error` (fail).
  A `required` field that resolves empty always raises.
- **Normalizers**: `E164`, `canonical`, `iso_country`, `yyyy_mm`, `lower`, `upper`.

Configs provided: [`config/default.json`](config/default.json) (full canonical
schema) and [`config/custom_example.json`](config/custom_example.json) (flattened
with renames + normalization).

---

## Outputs

Pre-generated from the sample inputs:

- [`output/default.json`](output/default.json) — full canonical profiles.
- [`output/custom.json`](output/custom.json) — flattened custom projection.

---

## Tests

```bash
PYTHONPATH=src python -m pytest -q
```

Covers normalizers, the projection path mini-language + `on_missing` policies,
merge/clustering/conflict resolution, an end-to-end run, robustness against
malformed inputs, and determinism.

---

## Design document

The one-page technical design is in [`design/DESIGN.md`](design/DESIGN.md).
Generate the required PDF (named `<FullName>_<Email>_Eightfold.pdf`) with:

```bash
pip install reportlab
python scripts/make_design_pdf.py --name "Your Full Name" --email you@example.com
```

The sample resume PDF can be regenerated with
`pip install reportlab && python scripts/make_sample_resumes.py`.

---

## Assumptions

- A real candidate must have at least one identifying signal (name, email, or
  phone); records with none are dropped as junk rather than emitted anonymously.
- Local phone numbers with no country code and no inferable region are dropped
  rather than guessed.
- A free-text location's country is only set when explicitly present; a city
  name never implies a country.
- Source trust ranking: recruiter CSV > ATS JSON > resume (structured,
  recruiter-maintained data outranks parsed free text).
- `years_experience` is taken from sources, never computed from date math.

## Deliberately descoped (time pressure)

- Other sources (recruiter notes, GitHub, LinkedIn, DOCX resumes): the
  architecture is pluggable (add an extractor + register it in `detect.py`), but
  they are out of scope here to keep the codebase minimal.
- ML-based entity resolution / fuzzy name matching beyond normalized-key matching.
- A UI (CLI only, which was the preferred interface).

## Scale

Extractors stream records lazily and clustering uses an O(n) hash index, so a
single run handles thousands of candidates. Processing order is sorted for
deterministic output.
