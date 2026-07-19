"""DKKD project SessionStart hook — prints skill catalog to context."""

import sys
import io

# Force UTF-8 output for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("""
=== DKKD Scraping Toolkit — Available Skills ===

This is the DKKD multi-brand store-location scraping project.
CLI entrypoint: python -m dkkd.cli
Source of truth: AGENTS.md (strategy catalog, new-brand checklist, monthly workflow)

## 5 Skills (invoke with the Skill tool)

| Skill | Trigger phrases | Core command |
|---|---|---|
| dkkd-scrape-strategy | scrape new brand, brainstorm stores, new brand config | python -m dkkd.cli loop --brand <slug> --creative |
| dkkd-classify | classify stores, postprocess, generate CSVs | python -m dkkd.cli postprocess --brand <slug> |
| dkkd-audit | audit stores, legacy migration, closed stores | python -m dkkd.cli audit --brand <slug> |
| dkkd-backtest | backtest, reconcile report, validate counts, greenfield quality check | python -m dkkd.cli backtest --brand <slug> |
| dkkd-monthly-update | monthly update, refresh all brands, update stores | python -m dkkd.cli loop/postprocess/audit/backtest per brand |

## 2 Entry Workflows

1. MONTHLY UPDATE (existing brands):
   -> Invoke skill: dkkd-monthly-update
   -> Sequence per brand: loop -> converged -> postprocess -> audit -> backtest

2. NEW BRAND BRAINSTORM:
   -> Invoke skill: dkkd-scrape-strategy
   -> Setup config -> loop --creative -> postprocess -> audit -> backtest (greenfield)

## Quick Reference

  python -m dkkd.cli brands              # list all configured brands
  python -m dkkd.cli strategies          # list all scraping strategies
  python -m dkkd.cli loop --brand <slug> --creative   # PLAYBOOK + automated creative phases
  python -m dkkd.cli state --brand <slug>      # inspect scrape progress
  python -m dkkd.cli converged --brand <slug>  # check convergence (exit 0/1)
  python -m dkkd.cli backtest --brand <slug>   # reference reconciliation OR greenfield quality check

See AGENTS.md for strategy catalog, amplifier ladder, and convergence rules.
""")
