# DKKD Multi-Brand Scraper — Agent Operating Manual

> **Audience:** the coding agent — the orchestrating reasoning loop. This file is your
> standing knowledge; don't re-derive it per brand.
>
> **Always use the project-local `.venv`** (`.venv/Scripts/python.exe` on Windows,
> `.venv/bin/python` elsewhere). `dkkd` is installed editable there against *this* repo;
> the system `python` has a rival editable `dkkd` pointing at a sibling repo, so running
> with it silently scrapes the wrong repo's code against the wrong DuckDB. Bootstrap if
> missing: `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
> (the `dev` extra adds `pytest` + the `dkkd` console script). Verify:
> `python -c "import dkkd; print(dkkd.__file__)"` points here, not the sibling.
>
> **`python -m pytest -q` must be green before every commit.** A commit on red is a defect.

---

## Quick Reference

```
dkkd run      --brand <slug> --strategy <name> [--params k=v,k=v]   # one phase
dkkd loop     --brand <slug>                                         # deterministic playbook
dkkd loop     --brand <slug> --creative                              # PLAYBOOK + automated creative phases
dkkd state    --brand <slug>                                         # JSON snapshot → reason about
dkkd converged --brand <slug>                                        # exit 0 = done, 1 = keep going
dkkd export   --brand <slug> [--format json|csv]
dkkd brands                                                          # list available brands
dkkd strategies                                                      # list registered strategies
dkkd backtest --brand <slug>                                         # reference reconciliation OR greenfield quality check
```

> **Living problem wiki:** `docs/wiki/README.md` — before working a known problem (dates,
> dedup, status, captcha-fetch, amplifiers), read its page; check Open Problems and Ruled-out
> first, and append to its Progression Log when you learn something.

---

## Terminology: License vs. Store

- **License** — one row in `checkpoint.json` / `<slug>.csv`: one DKKD registration = one
  physical location (the address on file). That location fact is settled once the row exists;
  its *function* and whether it's *still trading* are separate questions, below.
- **Function classification** — what the location is *for*, from the registration name
  (`classify_store_type()`, postprocess Stages 4–5.5). Three buckets:
  `retail_stores (operating)` (a storefront), `warehouse`, `office` (everything else —
  online / services / corporate / unclassifiable).
- **Verified vs. unverified — the primary status axis.** Every license starts **unverified**
  and stays so by default — *including* ones the 7-rung evidence ladder
  (`dkkd/operating_status.py`) inferred as `Operating`/`Closed`; that's a confidence-scored
  guess, not ground truth. A license becomes **verified** only once its EnterpriseInfo.aspx
  detail page is fetched past the reCAPTCHA gate (`dkkd-fetch-details` skill) and confirms
  status directly. See `docs/wiki/status-resolution.md`.
- **Store** — a license with *evidence*: `Core_Operating_Store == 'Yes'`. Safe-by-default:
  promoted only on a locator-pin match or independent active-GDT signal
  (`dkkd/operating_status.py`); everything else, including `Operating_Status == 'Unverified'`,
  stays `'No'` rather than being guessed into "store."
- **Rule of thumb:** a raw scrape count is a *license* count. It's a *store* count only when
  filtered to `Core_Operating_Store == 'Yes'` (the `v_operating_stores` view in
  `data/serving/dashboard.duckdb`, not the base `stores` table) — and even then it's
  unverified-by-default until run through `dkkd-fetch-details`.

---

## Operating Principles

You are the reasoning loop — these keep you from wrong assumptions and overcomplicating the scrape.

1. **Think before acting — read state, don't guess.** Always `dkkd state --brand <slug>` before
   choosing a strategy. Let `derived` (max_counter_seq, discovered_msts), `convergence`
   (zero_new_phases), and `hints` drive the decision. The hard API invariants below (10-row cap,
   dedupe on `Id`, filter on `Name`/`Name_F`, both diacritic forms) are non-negotiable — verify
   against them before assuming a query will work. A silent wrong assumption drops 10–15% of stores.
2. **Simplicity first.** Prefer `dkkd loop --creative` over hand-assembling phases. Drop to manual
   `dkkd run` only when a state signal shows a gap the automated phases can't close. Don't invent
   new strategies when an existing one with different params will do.
3. **Surgical changes.** When editing a brand `config.yaml`, change only the field the task needs
   (a new `seed_parent_mst`, a `backtest:` block). Don't rewrite `brand_regex` or reorder variants
   unless that's the task. `config.yaml` is authoritative; auto-discovered data goes to
   `discovered.json` via `cfg.enrich` — never hand-edit discovered values into the yaml.
4. **Goal-driven execution.** Success is defined, not vibed: scrape success = convergence
   (3 consecutive zero-yield phases); data-quality success = backtest PASS. Run to those criteria,
   then stop. Don't probe past convergence; don't declare done before backtest passes.

---

## File Placement & Naming Rules

Wrong-place files are defects. Before creating ANY file, find its row here:

| You are creating… | It goes… |
|---|---|
| A test | `tests/test_<module>.py`, mirroring `dkkd/<module>.py` |
| A brand-specific regression | A new row in `tests/test_brand_regressions.py`'s `BRANDS` table — NEVER a new file |
| A one-off analysis script | Session scratchpad. If it must survive: `scripts/` (reusable, docstring + usage line) |
| A findings write-up / report | `docs/archive/YYYY-MM-DD-<topic>.md` |
| Living reference documentation | `docs/wiki/` (check for an existing page first) |
| A repo maintenance tool | `scripts/` — `dkkd/` is importable pipeline code only |
| Brand data | Only the pipeline writes under `brands/<industry>/<subsector>/<slug>/`. Never at industry or subsector level. |
| Sector-specific pipeline code (keyword taxonomy, discovery strategy, sector report) | `dkkd/sectors/<sector>/` — one module per concern (`keywords.py`, `discovery.py`, `report.py`). NEVER a `<sector>_`-prefixed file in `dkkd/` root, `dkkd/data/`, or `dkkd/strategies/`. |
| Anything at repo root | Don't. Root is frozen: `pyproject.toml`, `AGENTS.md`, `README.md`, `vn_retail_system.json`. |

Naming: `snake_case.py`; kebab-case dated `.md` in archive. No "final", "v2", "new", "temp" in names.

---

## The Loop

The **deterministic playbook** (`dkkd loop`) runs:
`brand_variants → solr_escape(scout) → solr_escape(full) → parent_mst`.
The **creative playbook** (`dkkd loop --creative`) appends:
`corporate_sweep → compound → gdt_bare → token_mining → hierarchy_walk`.
All params derive from live state signals — no hardcoding.

**Convergence rule:** 3 consecutive phases with `added == 0`. Governs both playbooks. It is
*insufficient for tail coverage* — a brand can falsely converge short of its true ceiling (see
`docs/wiki/scraping-amplifiers.md`); the LLM loop (Option C) uses a stricter exit.

**Option A — fully automated (most brands):**
```
dkkd loop --brand <slug> --creative
```
Runs deterministic then creative phases off live state; stops on 3 consecutive zero-yield phases.

**Option B — manual creative phases (fine-grained control):**
1. `dkkd loop --brand <slug>` — deterministic playbook to its plateau.
2. `dkkd state --brand <slug>` — read `total_records`, `phase_history`, `discovered`, `derived`, `convergence`, `hints`.
3. If not converged: pick from `hints.untried_strategies` (or re-run with new params) →
   `dkkd run --brand <slug> --strategy <name> --params k=v`.
4. `dkkd converged --brand <slug>` after each phase — exit 0 = stop.
5. Repeat until converged, then `dkkd export`.

**Option C — agent-driven creative loop (tail coverage after creative phases plateau):**
Entry: `dkkd converged` exits 1 AND all five creative strategies appear in `phase_history`.
The agent reads `state.json` + `brands/<slug>/assumptions.json`, decides the next probe, runs it
via `dkkd run`, reflects on yield, updates `assumptions.json`. Exit condition + schema: see
"## LLM Creative Loop (Option C)" below.

Manual `dkkd run` is only needed when a strategy warrants custom params beyond what state signals
provide (e.g. `compound` with a hand-curated amplifier list).

---

## Two Pipelines: Discovery vs. Pre-Determined Brands

**Pipeline 1 — Greenfield Discovery** (`dkkd discover`). Used when a sector has no curatable brand
list (e.g. gold: thousands of independent shops). Sweeps sector keywords × provinces, clusters raw
hits by parent MST, filters known chains, and writes reviewable `config.yaml` stubs to
`brands/_discovered/`. Code lives entirely under `dkkd/sectors/<sector>/`: `keywords.py`,
`discovery.py` (the `@strategy` probe generator), `orchestrator.py` (sweep→cluster→filter→stubs),
`report.py` (sector rollup). Gold is the only sector using this today. Classification safety rules
for its output: "## Greenfield Brand Discovery & Classification Safety Rules" below.

**Pipeline 2 — Pre-Determined Brands** ("The Loop", above). Used for any brand with a known
`config.yaml`. Fully sector-agnostic: `dkkd/engine.py` + the strategy registry (`dkkd/strategies/*`)
+ `dkkd/config.py`. Every sector — including gold's known chains (pnj, doji, sjc, …) — is scraped
this way. Once a Pipeline 1 stub is reviewed and accepted, it becomes a normal `config.yaml`
scraped by Pipeline 2.

---

## Strategy Catalog

| Strategy | Purpose | Params | When to Use |
|---|---|---|---|
| `brand_variants` | Permute separators/case on the brand name to discover spelling variants (e.g. `CO.OPFOOD`) | — | Always first; deterministic loop runs it automatically. |
| `solr_escape` | Probe `+1..+N` — triggers Solr required-term match on numeric tokens, rotating the 10-row window | `phase=scout` (1–50) or `phase=full` (1–cap, cap = max(counter, branch) × 1.2) | After brand_variants; scout first, then full once you know the counter range. |
| `parent_mst` | Union all known parent MSTs (seed + discovered), emit bare MST + branch probes `MST-001..NNN` | — | After solr_escape; deterministic loop runs it. |
| `hierarchy_walk` | Per-parent BFS: for each parent MST in state + config, emit bare MST + branches to per-parent cap = max(observed_max × 1.5, 200). Seeds dynamically from all Format B records in state. | `min_branch_cap=200` | Creative loop (after gdt_bare). Replaces the `parent_mst` re-sweep — auto-includes newly discovered parents with per-parent caps. |
| `gdt_bare` | Probe bare 5-digit GDT counter sequences directly to bypass Solr window overflow limits | `cap=280` (override cap) | When spelling-variant queries match too many records and overflow the 10-row search limit. |
| `token_mining` | Mine rare tokens from collected `Name` fields, combine with brand variants | `max_freq=3` (default: tokens appearing ≤3 times) | Creative phase after deterministic loop plateaus. Check `state.json` sample_records for clues. |
| `compound` | Brand variant + amplifier word (surnames, address words, etc.). Default amplifier list always includes `Việt Nam;VIET NAM` (proven universal catch-all — yield data in `docs/wiki/gdt-format-patterns.md`). | `amplifiers=Nguyen,Tran,...` | Creative phase; use Vietnamese surnames or address words from the records. |
| `corporate_sweep` | Sweep for corporate entities (warehouses, HQs, logistics, online) via parent company names + brand-variant×corporate-keyword combos | — | First creative strategy; runs automatically in `--creative`. Also accepts records by parent-MST match. |
| `gold_discovery` | Probe keyword × province matrix to discover unknown gold chains | — | Phase 2 of gold stores nationwide scrape. |
| `raw` | Execute a caller-supplied keyword list verbatim — no brand-variant joining | `probes=kw1;kw2;kw3` | LLM Creative Loop only — for novel one-off probes (ward names, manager names, ad-hoc address fragments) no catalog strategy can express. |

> **`compound_all_provinces` is proposed, not registered** (won't appear in `dkkd strategies`).
> Automated `compound` only probes provinces already in the dataset, missing new-expansion
> provinces. Until implemented, replicate via `raw` with a hand-built 63-province probe list
> (both diacritic placements + ASCII forms). Rationale/empirical case: `docs/wiki/gdt-format-patterns.md`.

---

## How to Read `state.json`

```json
{
  "total_records": 611,
  "phase_history": [{"strategy": "brand_variants", "added": 580, ...}, ...],
  "discovered": {
    "spelling_variants": ["CO.OP FOOD", "COOPFOOD", ...],
    "parent_msts": ["0309129418", ...],
    "sibling_brands": []
  },
  "derived": {
    "max_counter_seq": 611,
    "max_branch_seq": 188,
    "discovered_msts": ["0309129418", "0305767459", ...]
  },
  "convergence": {"converged": false, "zero_new_phases": 1, "rule": "3 consecutive..."},
  "hints": {
    "untried_strategies": ["token_mining", "compound"],
    "suggested_next": "token_mining",
    "rationale": "2 strategies not yet tried"
  }
}
```

**Key signals:** `max_counter_seq` → `solr_escape` full-phase cap · `discovered_msts` → auto-fed
into `parent_mst` · `zero_new_phases` → distance to convergence (3 = done) · `untried_strategies`
→ what the deterministic loop hasn't touched.

---

## Hard API Constraints

1. **10-row hard cap** — every `GetSearch` call returns at most 10 records. No pagination params exist (`offset`, `page`, `skip`, `rows` — all silently ignored).
2. **No field-qualified queries** — `Name:FOOD` or `City_Id:122` parse as literal strings (0 results).
3. **No wildcards** — `*`, `?` are literal characters (0 results).
4. **Only `+` works as Solr operator** — `-`, `*`, `%`, and all other special-char prefixes return 0 results.
5. **Detail pages are reCAPTCHA-gated** — `/Single.aspx?Id=N` cannot be scraped.
6. **Rate-limit politeness** — preserve throttle cadence (60ms base, 250ms every 40th, no concurrency).
7. **Token expiry** — `h_token` expires; engine auto-refreshes every 150 queries + keepalive every 120.

---

## Corporate Entity Collection (Warehouses, HQs, Logistics, Online)

> [!IMPORTANT]
> **The Ingester accepts a record on EITHER criterion (OR logic):**
> 1. `Name` or `Name_F` matches `brand_regex`, or
> 2. `Enterprise_Gdt_Code` starts with a known parent MST (seed or discovered).
>
> This captures warehouses, corporate offices, logistics centers, and online ops registered
> under the *parent company* name (invisible to store-name search).

The `corporate_sweep` strategy (first creative phase) searches: explicit `corporate_names` from
config (if set) → bare parent-MST queries → brand variants × corporate keywords (KHO, VĂN PHÒNG,
LOGISTICS, ONLINE…). `classify_store` uses `DEFAULT_CORPORATE_KEYWORDS` as a fallback, so **all
brands** classify warehouses/HQs as `(Corporate/Logistics)` with `Core_Operating_Store: "No"` even
without config.

**Optional config.yaml overrides:**
```yaml
corporate_names: ["Dược phẩm An Khang Pharma", "An Khang Pharma"]   # auto-generated if omitted
classification:
  corporate_keywords: ['KHO', 'VĂN PHÒNG', 'TRUNG TÂM PHÂN PHỐI']   # else DEFAULT_CORPORATE_KEYWORDS
  corporate_regexes: ['^CHI NHÁNH CÔNG TY.*$']
```

---

## LLM Creative Loop (Option C)

`brands/<slug>/assumptions.json` — created by the `agy` LLM agent on first LLM-loop run (via its
`write_to_file` tool). **Append-only**; never reset between sessions.

**Exit condition — stricter than the Python convergence rule.** The agent may only
`declare_exhausted` when `exhaustion_evidence[]` holds **≥3 specific, probe-grounded** entries,
each naming: (1) the strategy run, (2) the exact probe range (e.g. `+1..+450` or `MST-001..MST-220`),
(3) the consecutive-empty count at the tail.
- **Valid:** `"Format A (gdt_bare) probed to 450 with 15 consecutive empties past counter max 335"` ·
  `"All 12 parent MSTs enumerated to branch -220, 18 consecutive empties at tail"`
- **Invalid (no range/count):** `"I've tried everything"` · `"All strategies exhausted"` · `"sort_flip yielded 0"`

**Schema:**
```json
{
  "brand": "<slug>",
  "updated_at": "<ISO 8601 timestamp>",
  "hypotheses": [
    {
      "id": "h1",
      "claim": "GDT counter sequence extends beyond the observed max of 280",
      "status": "unverified | confirmed | refuted",
      "evidence": "<specific probe result that changed status>",
      "created_at": "<ISO timestamp>",
      "updated_at": "<ISO timestamp>"
    }
  ],
  "dead_ends": [
    {
      "strategy": "sort_flip",
      "params": {},
      "added": 0,
      "reason": "Solr window already saturated — rotating sortField returns same 10 rows",
      "recorded_at": "<ISO timestamp>"
    }
  ],
  "proven_amplifiers": [
    {
      "strategy": "token_mining",
      "params": {"max_freq": 3},
      "added": 72,
      "notes": "Second-highest single-phase yield; rare tokens in Name field",
      "recorded_at": "<ISO timestamp>"
    }
  ],
  "exhaustion_evidence": [
    "Format A (gdt_bare) probed to 450 with 15 consecutive empties past counter max 335",
    "All 12 parent MSTs enumerated to branch -220, 18 consecutive empties at tail",
    "token_mining at max_freq=1 (singletons) — 0 added from 512 unique singleton tokens"
  ]
}
```

**Field rules:** `hypotheses` — claims about the brand's index structure; tested via probes, updated
confirmed/refuted. `dead_ends` — strategy+params that provably yielded 0 for a principled reason;
don't retry. `proven_amplifiers` — strategies that yielded >0; record params+yield for re-run with
variants. `exhaustion_evidence` — burden of proof for `declare_exhausted` (see exit condition above).

---

> **Diacritic placement & address-search constraints:** see `docs/wiki/scraping-amplifiers.md`
> — HÓA/HOÁ accent variants, and why `Ho_Address` can't be searched directly.

---

## Global Geographic Lookup Database

Pre-compiled lookup of all **65 cities, 724 districts, 5,834 wards** with internal DB IDs and
parent-child relations. Data: `dkkd/data/geo_lookup.json`; utility: `dkkd/data/geo_lookup.py`
(via `dkkd.data.get_geo_lookup`).

**SOP — never hand-roll location matching:**
- Don't write custom regexes for location names in address sweeps — use
  `get_geo_lookup().generate_regex(name, level)`, which handles prefix variants
  (`Quận`/`Q.`/`Huyện`/`Xã`/`Phường`/`P.`/`TP.`), tone-mark placement (`HÓA`/`HOÁ`), and
  ASCII-folded forms (`Cau Giay`, `Ho Chi Minh`).
- Don't guess `City_Id`/`District_Id`/`Ward_Id` — resolve via `get_geo_lookup().resolve_address_ids(address_string)`.
- `postprocess.py` falls back to parsing `Ho_Address` on the fly for newly created admin units.

---

## Dual-Format GDT Registration Pattern

> [!IMPORTANT]
> **Vietnamese retail chains register stores in TWO parallel GDT code formats:**
>
> | Format | Pattern | Example | Discovery Strategy |
> |--------|---------|---------|-------------------|
> | **Format A** (Business Locations) | 5-digit counter `00001`–`00NNN` | `00073` | `solr_escape`, `gdt_bare` |
> | **Format B** (Branches) | Parent MST + 3-digit suffix `-001`–`-NNN` | `0313330856-045` | `parent_mst`, `hierarchy_walk` |
>
> Format B records are often registered under the parent company name only, invisible to keyword
> search. See `docs/wiki/gdt-format-patterns.md` for the MST fragmentation ratio (drives
> `hierarchy_walk` branch caps) and per-strategy efficiency benchmarks.

---

## Proven Dead Ends — DO NOT RETRY

- `high_branch_sweep` — 0 yield across 15+ runs; unregistered (removed, see git history).
- `sort_flip` — 0 yield across 21 runs (Solr window saturated; rotating sortField returns the same 10 rows); unregistered.
- **Full list** (numeric-ID search, detail-page scraping, pagination params, field-qualified
  queries, wildcards, non-`+` prefixes, address search): `docs/wiki/scraping-amplifiers.md` →
  "Ruled out / dead ends."

---

## New Brand Checklist

1. Create `brands/<slug>/config.yaml` with minimal seed:
   ```yaml
   slug: <slug>
   name: <Brand Name>
   brand_regex: '<REGEX>'
   spelling_variants: ['<VARIANT1>', '<VARIANT2>']
   seed_parent_msts: []
   default_store_type: '<Brand Name>'
   ```
2. `dkkd loop --brand <slug> --creative` — deterministic + creative phases in one command.
3. `dkkd converged --brand <slug>` — verify exit 0.
4. `dkkd backtest --brand <slug>` — greenfield quality check (no config needed).
5. `dkkd export --brand <slug>`.

If creative phases don't converge, run manual amplifiers via `dkkd run --brand <slug> --strategy <name>`
then re-check state.

---

## Monthly Re-Scrape Workflow

Four-command sequence per brand.

### Step 1 — Scrape
```bash
dkkd loop --brand <slug>
# ... check state, run creative strategies if needed ...
dkkd converged --brand <slug>
```
> [!TIP]
> **Re-scrape delta for active-expansion brands:** a brand registering new stores daily can outpace
> a single pass (the creative loop alone can take 30+ min, during which new stores get filed). After
> `--creative` completes, run a second deterministic pass (`dkkd loop --brand <slug>`) to catch
> anything registered mid-sweep. Empirical case: `docs/wiki/scraping-amplifiers.md`.

### Step 2 — Post-Process
```bash
dkkd postprocess --brand <slug>
```
6-stage pipeline:
1. **Status refinement** — maps parent entity MSTs to GDT tax status.
2. **Date interpolation** — builds ID→date model from masothue.com calibration.
3. **Store classification** — assigns Store_Brand_Format, Store_Type_MSN, Core_Operating_Store.
4. **Geo enrichment** — parses City/District/Ward from addresses.
5. **Export** — writes to `brands/<slug>/output/`:
   - `<slug>.csv` — full dataset (keeps `Core_Operating_Store`/`Operating_Status` for backtest/audit).
   - `<slug>_unverified.csv` — opt-in brands only (backtest.py reads it for its report narrative).
   - `<slug>_standard_schema.csv`/`.xlsx` — analyst deliverable, using
     `store_brand_name_confidence`/`duplication_status` quality signals instead of a binary
     operating/non-operating file split.

   These small JSON/CSV/XLSX files *are* the project's data — there is no database. `dkkd pipeline`'s
   Parquet/DuckDB under `data/` is an optional, gitignored, fully regenerable dashboard layer on top.

Skip masothue.com HTTP calls (reuse existing dates): `dkkd postprocess --brand <slug> --skip-date-calibration`.

Optionally refresh the DPI dissolution cross-reference first — pull the current month's GIẢI THỂ
notices from the public E-Gazette bulletin into a CSV via your own scraper, then pass it:
`dkkd postprocess --brand <slug> --dpi-status-file dissolution_<date>.csv`.

### Step 3 — Audit (optional integrity check)
```bash
dkkd audit --brand <slug>
```
Generates `<slug>_audit_report.md` with legacy migration analysis.

### Step 4 — Back-test (dual-mode, auto-selected)
```bash
dkkd backtest --brand <slug>
```
**Reference mode** (a `backtest:` block exists in the brand's `config.yaml`): compares scraped
core-operating counts against external report figures. Generates `<slug>_backtest_report.md` with
network size, format breakdown, and regional distribution tables.

**Greenfield mode** (no `backtest:` block — all other brands): runs 5 structural quality invariants
on `state.json` + `checkpoint.json`, PASS/FAIL each:
1. Convergence reached (3 consecutive zeros in history).
2. Dedup integrity (all checkpoint Ids unique).
3. Brand filter compliance (all records match `brand_regex`).
4. GDT branch coverage (≥1 branch-format `XXXXXXXXXX-NNN` code found).
5. Playbook completeness (all 4 PLAYBOOK strategy names in phase_history).

Add reference counts by putting a `backtest:` block in `config.yaml`:
```yaml
backtest:
  report_label: "Source label"
  expected_total: <N>
```
When an external reference source publishes updated counts, edit the affected `config.yaml` fields
directly (e.g. `backtest.expected_total`, or classification caps/keywords under `classification:`)
then re-run `dkkd postprocess --brand <slug>`. `config.yaml` is the authoritative per-brand source
for this tuning (Operating Principle #3); it doesn't belong in this file.

> **Strategy efficiency benchmarks** (per-strategy yield + the strategy-ordering ladder from a
> large-scale reference scrape): `docs/wiki/gdt-format-patterns.md`.

---

## Greenfield Brand Discovery & Classification Safety Rules

To prevent false positives and classification errors when implementing greenfield brands or new sector sweeps:

1. **Avoid substring over-matching in `brand_regex`:** don't include bare common words, locations,
   or short abbreviations (e.g. `'PHÚ NHUẬN'`) — they pull in unrelated companies (real estate,
   schools, local services) sharing the place name. Match corporate name prefix/suffixes or the
   sector-specific brand abbreviation explicitly (e.g. `'VÀNG BẠC ĐÁ QUÝ PHÚ NHUẬN'`).
2. **Null/missing field safe handling:**
   - Missing GDT codes: cast safely to avoid `None` → `'None'`: `gdt = str(record.get('Enterprise_Gdt_Code') or '')`.
   - HQ/corporate detection: don't assume a hyphen-less GDT is corporate when empty/falsy —
     guard: `or (gdt and '-' not in gdt and not gdt.isdigit())`.
   - Missing status: fall back with `or`, not `dict.get(key, default)`: `status = record.get('Status') or 'NNT đang hoạt động'`.
3. **Ingestion post-audit:** for any newly scraped greenfield brand, run a name audit on unique
   checkpoint records to flag non-retail keywords (`MEDIA`, `FARMING`, `VINA`, `PAINT`, `GAS`,
   `BẤT ĐỘNG SẢN`, `XÂY DỰNG`, `GIÁO DỤC`) and add them to the brand's `corporate_keywords`.

---

## Skills ↔ Workflow (Claude Code)

Six project-local Claude Code skills map to the deterministic CLI:

| Skill | Invoke when | CLI anchor |
|---|---|---|
| `dkkd-scrape-strategy` | New brand to scrape, brainstorming coverage | `dkkd loop` + amplifier phases |
| `dkkd-classify` | Post-scrape classification and CSV split | `dkkd postprocess` |
| `dkkd-fetch-details` | Per-store detail fetch when search API Status is insufficient | `EnterpriseInfo.aspx` via browser-harness (user solves CAPTCHA) |
| `dkkd-audit` | Legacy migration integrity check | `dkkd audit` |
| `dkkd-backtest` | Reconcile counts against external report | `dkkd backtest` |
| `dkkd-monthly-update` | Monthly cadence update of all brands | Full pipeline per brand |

This file (`AGENTS.md`) is the workflow source of truth; `.claude/skills/` layers project-local
Claude Code skills on top of the same CLI commands.
