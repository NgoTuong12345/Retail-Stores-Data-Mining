---
name: dkkd-scrape-strategy
description: DKKD new-brand scraping strategy. Use when brainstorming how to scrape a new brand's store locations from dkkd.gov.vn, setting up a new brand config, running the sweep, applying the amplifier ladder, or checking convergence.
---

# DKKD Scrape Strategy

## When to use

Use when the user wants to scrape a new brand's stores from DKKD, or asks "how do I find all X stores?" or "set up a new brand."

## Setup (brand-specific)

Create `brands/<slug>/config.yaml` with at minimum:

```yaml
slug: <slug>
name: <Brand Display Name>
brand_regex: "<regex matching all brand name variants>"
spelling_variants:
  - "<Variant 1>"
  - "<Variant 2>"
seed_parent_msts: []
```

See existing brand configs (`brands/F&B/supermarket/winmart/config.yaml`, `brands/F&B/mini_supermarket/bach-hoa-xanh/config.yaml`) for full structure with classification and backtest blocks.

## Command sequence

```bash
python -m dkkd.cli loop --brand <slug> --creative   # PLAYBOOK + automated creative phases
python -m dkkd.cli state --brand <slug>             # inspect progress and current store count
python -m dkkd.cli converged --brand <slug>         # exit 0 if converged, exit 1 if not
python -m dkkd.cli backtest --brand <slug>          # greenfield quality check (no config needed)
```

The `--creative` flag automatically runs the four amplifier strategies (token_mining → sort_flip → compound → gdt_bare) with parameters derived from live state signals, so you usually don't need manual `dkkd run` phases.

## If creative loop doesn't converge

Run individual amplifier phases from AGENTS.md §Strategy Catalog with custom params:
- Token mining (rare tokens from Ho_Address / Legal_First_Name)
- Sort-flip rotation (extra sortField/orderBy params)
- gdt_bare sweeps (parent MST probes from 14-char Gdt_Codes)
- Unicode Vietnamese district/ward names

```bash
python -m dkkd.cli run --brand <slug> --strategy compound --params amplifiers=Bình Dương,Đồng Nai
```

## Key constraint

The API returns exactly 10 rows per query — no pagination, no offset, no filters. Keyword diversity is the only way to increase coverage. See `AGENTS.md` and `docs/dkkd-vn-brand-scraper-skill-v4.md` for the full amplifier strategy list.

## Convergence rule

Stop when 3 consecutive amplifier phases yield 0 new rows. Re-run Unicode diacritics and `+N` Solr escape phases if stuck — these have the highest marginal yield.

## Next step

After convergence, run the `dkkd-classify` skill. Then run `dkkd-backtest` — for a new greenfield brand it validates structural data quality (dedup, brand-filter compliance, GDT coverage) even without an external reference report.

## References

- `AGENTS.md` — CLI quick-reference and full strategy catalog
- `docs/dkkd-vn-brand-scraper-skill-v4.md` — API mechanics and all amplifier strategies
