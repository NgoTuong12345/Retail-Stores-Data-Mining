---
name: dkkd-monthly-update
description: DKKD monthly store location update. Use when doing the monthly update of store locations for all existing brands — re-scrape, classify, audit, and back-test each brand in sequence.
---

# DKKD Monthly Update

## When to use

Use on the monthly cadence when the user says "update store locations", "refresh all brands", or "run the monthly update."

## Step 0: list brands

```bash
python -m dkkd.cli brands
```

## Per-brand sequence (repeat for each brand)

```bash
python -m dkkd.cli loop --brand <slug> --creative   # PLAYBOOK + automated creative phases
python -m dkkd.cli converged --brand <slug>         # verify convergence (exit 0 = converged)
python -m dkkd.cli postprocess --brand <slug>
python -m dkkd.cli audit --brand <slug>
python -m dkkd.cli backtest --brand <slug>          # reference reconciliation OR greenfield quality check
```

The `--creative` flag runs the deterministic PLAYBOOK then automatically cycles the four creative amplifier strategies (token_mining → sort_flip → compound → gdt_bare) to convergence — no manual phases needed in the common case.

## If convergence fails

If `converged` exits 1 even after `--creative`, run individual amplifier phases from AGENTS.md §Strategy Catalog with custom params before proceeding to postprocess:
- Token mining (rare tokens from Ho_Address / Legal_First_Name fields)
- Sort-flip rotation (extra sortField/orderBy params to rotate the 10-row slice)
- gdt_bare sweeps (probe parent MSTs extracted from 14-char Gdt_Codes)

## After all brands

- Review `brands/<slug>/output/<slug>_audit_report.md` for each brand — check for unexpected legacy migration failures
- Review `brands/<slug>/output/<slug>_backtest_report.md` for every brand:
  - **Reference-mode brands** (winmart, coop-food): verify match % is within acceptable tolerance
  - **Greenfield brands**: verify all 5 structural invariants are PASS (any FAIL signals a data-quality regression)
- Commit updated output CSVs and checkpoint files

## Reference

- `AGENTS.md` §Monthly Re-scrape Workflow — full checklist with acceptance criteria
- `AGENTS.md` §Strategy Catalog — amplifier phases to run if convergence fails
