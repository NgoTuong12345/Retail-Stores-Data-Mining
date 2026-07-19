# Deduplication & Brand Filtering

**Status:** stable
**Last updated:** 2026-06-30

**TL;DR:** Dedupe **exclusively on the `Id` field** (internal auto-increment PK) — never on
`Enterprise_Code`/`Enterprise_Gdt_Code`. Filter rows on `Name`/`Name_F`, **not** `Title`
(a silent trap that drops 10%+). `brand_regex` alternatives must be anchored to the
distinctive brand token, never a bare generic word.

## Current understanding

<!-- STUB — fill progressively. -->

## Current solution

<!-- STUB -->

## Open Problems

| id | problem | status | impact |
|---|---|---|---|
| — | (none recorded yet) | — | — |

## Ruled out / dead ends

<!-- STUB -->

## Progression Log

- 2026-06-30: page created as a stub.

## Links

- Source docs: `CLAUDE.md` (Target API / hard constraints), `docs/dkkd-vn-brand-scraper-skill-v4.md`
- Code: `dkkd/ingest.py`, `dkkd/engine.py`
- Tests: `tests/test_ingest.py`, `tests/test_btmc_brand_filter.py`, `tests/test_sjc_brand_filter.py`
- Memory slugs: `brand-regex-false-positives`

## Validate / reproduce

<!-- STUB -->
