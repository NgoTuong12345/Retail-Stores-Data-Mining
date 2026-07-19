---
name: dkkd-classify
description: DKKD store classification pipeline. Use after scraping to classify stores into formats (Core_Operating_Store, Store_Brand_Format, Store_Type_MSN) and export the full CSV + standard-schema deliverable.
---

# DKKD Classify

## When to use

Use after scraping has converged. Run this when the user wants to classify stores, generate output CSVs, or interpret classification columns.

## Command

```bash
python -m dkkd.cli postprocess --brand <slug>

# If masothue.com is slow or unavailable:
python -m dkkd.cli postprocess --brand <slug> --skip-date-calibration
```

## Outputs

All files written to `brands/<slug>/output/`:

| File | Contents |
|---|---|
| `<slug>.csv` | All records with classification columns (`Core_Operating_Store`/`Operating_Status` live here — filter this file directly for an operating/non-operating split; backtest.py and audit.py both read it this way) |
| `<slug>_unverified.csv` | Opt-in brands only — rows where `Operating_Status == Unverified`; backtest.py reads this file directly for its report narrative |
| `<slug>_standard_schema.csv` / `.xlsx` | The analyst-facing deliverable — canonical cross-brand schema with `store_brand_name_confidence` and `duplication_status` quality signals |

## Key classification columns

- `Store_Brand_Format` — brand-specific format label (e.g. "WinMart+", "Bach Hoa Xanh")
- `Store_Type_MSN` — MSN investor report category (e.g. "WinMart+ (Supermarket)", "Mini")
- `Core_Operating_Store` — `Yes` / `No` / `Pending`

## Brand-specific config

Classification rules live in `brands/<slug>/config.yaml` under the `classification:` block:
- WinMart has a supermarket-cap second-pass logic for format disambiguation
- Generic brands use `store_type_rules` list with regex-based matching

Modify `classification:` in config.yaml to tune rules; re-run postprocess to regenerate.

## Next step

After classification, run the `dkkd-audit` skill and (if a `backtest:` block exists in config) the `dkkd-backtest` skill.

## References

- `AGENTS.md` — CLI quick-reference and postprocess notes
- `dkkd/postprocess.py` — classification logic source
