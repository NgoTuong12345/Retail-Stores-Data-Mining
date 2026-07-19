---
name: dkkd-backtest
description: DKKD back-test reconciliation. Validates scraped store data — reference mode (compare against external report) for brands with a backtest config, or greenfield mode (5 structural quality invariants) for all other brands.
---

# DKKD Backtest

## Command

```bash
python -m dkkd.cli backtest --brand <slug>
```

Mode is auto-selected — no flag needed.

## Reference mode (brands with `backtest:` config)

Use after `dkkd postprocess` when an external report exists (MSN investor report, analyst disclosure, etc.).

Output: `brands/<slug>/output/<slug>_backtest_report.md` with:
- **Network Size** — scraped total vs report total, delta and match %
- **Store Format Breakdown** — per-format count vs report expectation
- **Geographic Distribution** — regional breakdown vs report split

Config required in `brands/<slug>/config.yaml`:
```yaml
backtest:
  report_label: "MSN May 2026 Investor Report"
  expected_total: 2500
  expected_by_format:
    WinMart (Supermarket): 70
    WinMart+: 2430
  expected_by_region:
    North: 1200
    South: 1300
```

Currently configured: `winmart` (MSN May 2026), `coop-food` (known baseline 2026-06-27, 817 stores).

## Greenfield mode (brands without `backtest:` config)

Use after `dkkd loop` for any brand — no config needed. Reads `state.json` and `checkpoint.json` directly (no live API).

Runs 5 structural invariants and reports PASS/FAIL:

| Invariant | Pass condition |
|---|---|
| Convergence reached | `state.json → convergence.converged == true` |
| Dedup integrity | All checkpoint Ids unique |
| Brand filter compliance | All records match `brand_regex` |
| GDT branch coverage | ≥1 record with branch-format GDT code (`^\d{10}-\d{3}$`) |
| Playbook completeness | brand_variants, solr_escape, parent_mst, high_branch_sweep all in phase_history |

Output: same path `brands/<slug>/output/<slug>_backtest_report.md`.

## References

- `AGENTS.md` §Monthly Re-Scrape Workflow — Step 4 backtest dual-mode
- `brands/F&B/supermarket/winmart/config.yaml` — reference implementation of `backtest:` block
