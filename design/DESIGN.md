# Multi-Source Candidate Data Transformer — Technical Design

**Goal.** Turn messy, overlapping, sometimes-malformed candidate inputs into one
canonical profile per candidate — normalized, deduplicated, with provenance and
confidence — and project it into a runtime-configurable output. Core invariant:
*wrong-but-confident is worse than honestly-empty.* Unknown → `null`; never invent
values; every value is traceable.

## Pipeline
`detect → extract → normalize → merge → confidence → project → validate`

- **detect**: source type from extension/content.
- **extract**: one parser per source → `RawRecord` carrying raw values +
  `{source, method}`. Malformed input is logged and skipped, never fatal.
- **normalize**: total, pure functions; unparseable → `null`.
- **merge**: cluster records into candidates, resolve conflicts, union lists.
- **confidence**: deterministic score per field + overall.
- **project**: config-driven output shaping (kept fully separate from canonical).
- **validate**: canonical record vs fixed schema; projected output vs a schema
  derived from the config.

## Canonical schema & normalization formats
Fields per the spec (`candidate_id, full_name, emails[], phones[], location,
links, headline, years_experience, skills[], experience[], education[],
provenance[], overall_confidence`). Formats: **phones** E.164 (`phonenumbers`);
**dates** `YYYY-MM` (+ literal `present`); **country** ISO-3166 alpha-2
(`pycountry` + alias table); **skills** canonical names via an alias map
(`JS→JavaScript`, `k8s→Kubernetes`); emails lowercased + deduped.

## Merge / conflict resolution
- **Matching keys** (union-find, O(n) via hash index): normalized email →
  E.164 phone → (name-key + current company).
- **Winner selection** (scalars): group equal values, score by
  `confidence → source-trust → corroboration count → alphabetical` (last key
  guarantees determinism). List fields (emails/phones/skills) are unioned +
  deduped; experience/education deduped by identity tuple keeping the most
  complete entry.
- **Source trust**: recruiter CSV > ATS JSON > resume (structured data outranks
  parsed free text).
- **Confidence**: `source_trust × method_reliability`, with an agreement boost
  when independent sources concur; unknown skills get a penalty. `overall` =
  mean of per-field confidences. Both winning and losing values stay in
  provenance, so any result is explainable.

## Configurable output (the Twist)
Config selects/renames fields, remaps via a `from` path expression, applies
per-field normalization, toggles confidence/provenance, and sets `on_missing`
(`null | omit | error`). A small **path mini-language** supports `full_name`,
`location.country`, `emails[0]`, `skills[].name`, `experience[0].title`. The
**projection layer** is the only component that knows the output shape; the
canonical record is oblivious, so one engine serves many configs with zero code
changes. The projected result is validated against a JSON schema generated from
the config (types + required), so a config can never silently emit a malformed
record.

## Edge cases
1. **Same person, conflicting email/phone across sources** → clustered, deduped,
   winner by trust/confidence, all variants kept in provenance.
2. **Corrupt PDF / invalid JSON / empty file / junk row** → warned and skipped;
   records with no identity (no name/email/phone) are dropped, not emitted.
3. **Unparseable phone / ambiguous country** → `null` (a local number with no
   country code and no region is dropped rather than guessed).
4. **Required field missing under a config** → raises a clear error; non-required
   missing follows `on_missing`.
5. **Skill aliasing** → `JS`/`react.js` canonicalize; unknown skills are kept
   verbatim at lower confidence (never coerced into a known skill).

## Deliberately descoped (time pressure)
Other sources (recruiter notes, GitHub, LinkedIn, DOCX) — the design is pluggable
(add an extractor + register it), but out of scope here to keep things minimal;
ML/fuzzy entity resolution beyond normalized keys; deep resume layout parsing; a
UI (CLI is the preferred interface).

## Scale & determinism
Lazy streaming extraction + O(n) hash-indexed clustering handle thousands of
candidates per run; sorted processing order + alphabetical tiebreaks make output
byte-for-byte deterministic (covered by a determinism test).
