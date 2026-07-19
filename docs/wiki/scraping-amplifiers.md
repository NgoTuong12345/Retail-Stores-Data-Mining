# Scraping Amplifiers & Convergence

**Status:** stable
**Last updated:** 2026-07-19

**TL;DR:** The search API returns exactly 10 rows per query (no pagination/filters), so full
coverage comes only from **keyword diversity**. An amplifier ladder (brand spelling variants,
numeric probes, `+N` Solr escape, Unicode diacritics, 2-letter sweep, district names,
parent-MST sweep, token mining, sort-flip) widens the slice. Stop when 3 consecutive
amplifier phases yield 0 new rows.

## Current understanding

**The Accent Placement Gotcha (HÓA vs HOÁ)** [empirical]: Vietnamese diacritics allow different
placement of tone marks on compound vowels (e.g., `oá` vs `óa`). The DKKD Solr backend returns
different result sets depending on the exact character sequence of the search query.
- `HÓA` (accent on `o`, e.g. `BÁCH HÓA XANH`) is the older spelling convention.
- `HOÁ` (accent on `a`, e.g. `BÁCH HOÁ XANH`) is the newer standard.

**SOP:** always write `brand_regex`/`spelling_variants` in `config.yaml` to include **both**
accent versions (e.g. `brand_regex: 'BÁCH HÓA XANH|BÁCH HOÁ XANH|...'`). Failure to do so
discards up to 10-15% of valid stores during ingestion.

**The zero-yield convergence heuristic can false-positive** [empirical]: Co.op Food's
deterministic loop declared convergence (3 consecutive zero-yield phases) at 478 stores; the
true ceiling, reached only via the LLM creative loop's stricter probe-grounded exit condition
(see `AGENTS.md` "Convergence Proof Rule"), was 611. Don't trust the 3-zero-phase heuristic
alone for brands the creative strategies haven't fully exhausted.

**Re-scrape delta for actively-expanding brands** [empirical]: a brand registering new stores
daily (e.g. Bách Hóa Xanh in 2026, ~1 store/day in Northern Vietnam) can outpace a single scrape
pass — the creative loop alone took 30+ minutes, during which new stores were filed. Run a
second deterministic pass (`dkkd loop --brand <slug>`) right after the creative phases finish to
catch anything registered mid-sweep; this caught 174 additional BHX stores.

## Current solution

<!-- STUB -->

## Open Problems

| id | problem | status | impact |
|---|---|---|---|
| — | (none recorded yet) | — | — |

## Ruled out / dead ends

**`Ho_Address` is not indexed for unstructured search** [empirical] on the DKKD Solr backend.
Querying a street name (e.g. `Bình Giã`) or a full address (`1003 Bình Giã`) returns `0 results`
unless that text is also part of the primary `Name` field. Never search by physical address —
only via branch sequences (`parent_mst`), counter codes (`solr_escape`/`gdt_bare`), or
province/city amplifiers (`compound`).

| Dead end | Why it failed |
|---|---|
| Direct numeric ID search (`CO.OP FOOD 800`) | Numeric IDs are internal relational keys, not Solr-indexed text |
| Detail page scraping (`/Single.aspx?Id=N`) | reCAPTCHA gated |
| Pagination parameters (`offset`, `page`, `skip`, `rows`) | Silently ignored; 10-row cap is server-side |
| Field-qualified Solr queries (`Name:FOOD`) | Evaluated as literal text, returns 0 |
| Wildcards (`*Food`, `?FOOD`) | Parsed as literal characters, returns 0 |
| Special-char prefixes other than `+` (`-N`, `*N`, `%N`) | Checked across N=1..100 for all common symbols, 0 hits |
| Searching by store address (`1003 Bình Giã`) | The address field is not indexed for unstructured text search |
| `sort_flip` (rotating `sortField`) | 0 yield across 21 runs; Solr window already saturated |
| `high_branch_sweep` | 0 yield across 15+ runs |

## Progression Log

- 2026-06-30: page created as a stub.
- 2026-07-19: migrated the diacritic-accent SOP, the address-search dead end, and the
  "Proven Dead Ends" table in from `AGENTS.md` — this is where that content belongs per the
  wiki's own link-don't-duplicate rule. AGENTS.md now links here instead of embedding it.
- 2026-07-19: migrated the Co.op Food false-convergence case and the BHX re-scrape-delta lesson
  in from `AGENTS.md` (Convergence Proof Rule section, Monthly Re-Scrape Workflow section) —
  same reasoning, AGENTS.md keeps only the generic rule/workflow and links here for the
  brand-specific evidence.

## Links

- Code: `dkkd/strategies/`, `dkkd/loop.py`, `dkkd/engine.py`, `dkkd/convergence` logic
- Source docs: `AGENTS.md` (strategy catalog / amplifier ladder), `docs/dkkd-vn-brand-scraper-skill-v4.md`,
  `docs/archive/walkthrough.md`, `scraper/run-coopfood.md`
- Tests: `tests/test_strategies.py`, `tests/test_convergence.py`, `tests/test_hierarchy_walk.py`
- Memory slugs: `feedback-hierarchy-walk`

## Validate / reproduce

<!-- STUB -->
