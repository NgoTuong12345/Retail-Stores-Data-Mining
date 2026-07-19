---
name: dkkd-audit
description: DKKD legacy migration audit. Use to check how many legacy/closed stores at the same address were migrated to an active format vs permanently closed.
---

# DKKD Audit

## When to use

Use after classification has been run. Use when the user wants to verify data quality or understand legacy store transitions (e.g. VinMart -> WinMart conversions, closed-store handling).

## Command

```bash
python -m dkkd.cli audit --brand <slug>
```

Requires `postprocess` to have been run first (`brands/<slug>/output/<slug>.csv` must exist).

## Output

`brands/<slug>/output/<slug>_audit_report.md` — markdown report with sections:

- **Summary** — total counts, core operating rate, legacy audited rate
- **Format Distribution** — store count by `Store_Brand_Format`
- **Non-Operating Breakdown** — breakdown of non-core records by type
- **Legacy Migration Audit** — matched legacy/closed stores to active format records by address

## How it works

Matches `<Brand> (Legacy/Closed)` records against active stores using normalized address comparison (exact match first, then substring fallback). Reports how many legacy records have a confirmed active successor vs how many appear permanently closed.

## Gotcha

Only meaningful for brands that have legacy closed-store records (e.g. WinMart/VinMart). For brands like Bach Hoa Xanh, `Total Legacy Audited` will be 0 — this is expected and not an error.

## Next step

If a `backtest:` block exists in the brand config, run the `dkkd-backtest` skill.

## References

- `AGENTS.md` — audit command notes
- `dkkd/postprocess.py` — audit logic
