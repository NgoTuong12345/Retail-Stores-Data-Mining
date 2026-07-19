# GDT Registration Format & MST Fragmentation

**Status:** active
**Last updated:** 2026-07-19

**TL;DR:** Vietnamese retail chains register stores in two parallel GDT code formats — Format A
(5-digit counter) and Format B (parent MST + branch suffix). Format B records are often filed
under the parent company name only, invisible to keyword search. Whether `parent_mst`/
`hierarchy_walk` are worth running depends on a brand's MST fragmentation ratio.

## Current understanding

**Dual-Format GDT Registration Pattern** [documented] (see `AGENTS.md` Strategy Catalog):

| Format | Pattern | Example | Discovery strategy |
|---|---|---|---|
| **Format A** (Business Locations) | 5-digit counter `00001`–`00NNN` | `00073` | `solr_escape`, `gdt_bare` |
| **Format B** (Branches) | Parent MST + 3-digit suffix `-001`–`-NNN` | `0313330856-045` | `parent_mst`, `hierarchy_walk` |

**Critical insight** [empirical]: Format B records are often registered under the **parent
company name only** (e.g. `CÔNG TY CỔ PHẦN SEVEN SYSTEM VIỆT NAM`) without any brand keyword
(`7-Eleven`) — invisible to keyword-based strategies (`brand_variants`, `solr_escape`,
`token_mining`).

**MST Fragmentation Pattern (BHX lesson)** [empirical]: brands vary widely in MST structure.
- *Centralized* brands (Co.op Food, WinMart) — few parent MSTs, many branches each.
  `parent_mst`/`hierarchy_walk` are high-yield.
- *Fragmented* brands (BHX: 2,930 unique MSTs for 3,309 stores, ratio 0.89) register each store
  as its own legal entity — branch-walking yields near-zero.

Use `mst_fragmentation_ratio` (= unique_msts / total_records, from `state.json.derived`) to
size `hierarchy_walk` caps:
- Ratio > 0.8 (fragmented): reduce `min_branch_cap` to 50.
- Ratio < 0.3 (centralized): keep `min_branch_cap` at 200+.

## Current solution

- `parent_mst` (deterministic loop): global branch cap `max(max_branch_seq × 1.2, 60)`.
- `hierarchy_walk` (creative loop): replaces the `parent_mst` re-sweep with **per-parent** caps
  `max(per_parent_max × 1.5, 200)` — guarantees a 200-branch floor per parent and handles
  parents with different branch counts correctly.
- Both strategies are required to find Format B records: `parent_mst` runs first in the
  deterministic loop, `hierarchy_walk` runs in the creative loop with enriched state and
  automatically picks up parent MSTs discovered by earlier phases — no manual config update
  needed.

### Strategy Efficiency Benchmarks (BHX reference)

Empirical efficiency data from the BHX scrape (3,309 records, 35 phases, 62,000+ probes).
Use to prioritize strategy ordering and set expectations for new brands.

| Strategy | Probes | Added | Efficiency | Notes |
|---|---|---|---|---|
| `raw` (diacritic province probes) | 57 | 44 | **77.2%** | Targeted diacritic+province probes for expansion regions |
| `compound` | 525 | 146 | **27.8%** | Province amplifiers; `Việt Nam` alone yielded 10 |
| `brand_variants` | 128 | 19 | **14.8%** | Low cost, good first pass |
| `solr_escape` | 27,770 | 2,984 | **10.8%** | Workhorse — highest absolute yield |
| `custom_high_sweep` | 3,055 | 40 | **1.3%** | Extended counter/branch range beyond defaults |
| `parent_mst` | 7,653 | 31 | **0.4%** | Low for fragmented-MST brands (ratio 0.89) |
| `token_mining` | 15,000 | 44 | **0.3%** | One-shot amplifier; re-runs without new data yield 0 |
| `hierarchy_walk` | 2,803 | 1 | **0.04%** | Near-zero for fragmented-MST brands |
| `gdt_bare` | 2,966 | 0 | **0.0%** | Redundant when `solr_escape(full)` covers counter range |
| `sort_flip` | 36 | 0 | **0.0%** | Confirmed dead end |

**Key takeaway:** for large fragmented brands, the yield ladder is `solr_escape` (workhorse) →
`compound` (targeted) → `raw` (surgical) → `token_mining` (one-shot) → everything else
(diminishing returns).

## Open Problems

| id | problem | status | impact |
|---|---|---|---|
| — | (none recorded yet) | — | — |

## Ruled out / dead ends

- `sort_flip` (rotating `sortField`) — 0 yield across 21 runs; confirmed dead end, no longer registered in `dkkd strategies`.

## Progression Log

- 2026-07-19: page created, migrating the "Dual-Format GDT Registration Pattern," "MST
  Fragmentation Pattern (BHX lesson)," and "Strategy Efficiency Benchmarks (BHX reference)"
  sections in from `AGENTS.md`. AGENTS.md keeps only the Format A/B table (needed inline
  context for the Strategy Catalog) and links here for the rest.

## Links

- Code: `dkkd/strategies/hierarchy_walk.py`, `dkkd/strategies/parent_mst.py` (per-parent vs.
  global branch caps), `dkkd/state_report.py` (`mst_fragmentation_ratio` derivation)
- Tests: `tests/test_hierarchy_walk.py`, `tests/test_strategies.py`
- Source docs: `AGENTS.md` (Strategy Catalog, Format A/B summary), `docs/archive/walkthrough.md`
- Related pages: [scraping-amplifiers](scraping-amplifiers.md)

## Validate / reproduce

- `dkkd state --brand <slug>` — check `derived.mst_fragmentation_ratio` and `discovered.parent_msts`.
- `dkkd run --brand <slug> --strategy hierarchy_walk --params min_branch_cap=50` — for fragmented brands.
