"""Regenerate docs/data-dictionary.md from the live serving DuckDB schema.

Column names/types are read straight from `data/serving/dashboard.duckdb` via
DuckDB's duckdb_tables()/duckdb_columns() introspection functions, so the
structure is always accurate even as tables are added/dropped. Descriptions
come from the curated TABLE_NOTES/COLUMN_NOTES below (reusing
dkkd/contract.py's DATA_DICTIONARY for the `stores`/`fact_store_snapshot`
columns rather than re-typing it) — a table/column with no curated note just
prints with an empty description instead of erroring, so a newly-added table
still shows up (in an "Other" section) even before someone documents it.

Re-run whenever a table/column is added, renamed, or dropped — in particular
after `python -m dkkd.cli pipeline`:

    python scripts/generate_data_dictionary.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from dkkd import contract
from dkkd.paths import PACKAGE_ROOT

DB_PATH = PACKAGE_ROOT / 'data' / 'serving' / 'dashboard.duckdb'
OUTPUT_PATH = Path(__file__).resolve().parent.parent / 'docs' / 'data-dictionary.md'

# One curated note per table/view. Keys not present in the live DB are
# silently skipped; live tables/views not listed here fall into "Other".
TABLE_NOTES = {
    # --- Core store/license tables ---
    'stores': "Conformed dkkd + website store/license rows, unioned (dkkd/conform.py). One row per license (dkkd) or per locator listing (website) — see CLAUDE.md's License vs. Store distinction before treating a row count as a store count.",
    'benchmarks': "IR-reported reference counts (Masan/MWG disclosures), kept separate from `stores` — never summed together, a different measurement of the same real-world footprint (dkkd/conform.py::extract_ir_benchmarks).",
    'fact_store_snapshot': "Append-only time axis: one row per (store_uid, as_of run date). A narrow projection of `stores`' slow-changing columns only (no name/address/lat/lng) — see docs/archive/superpowers/specs/2026-07-09-data-model-audit-consolidation-design.md. Historical as_of files are frozen once written; only today's is rewritten on re-run.",
    'data_dictionary': "Self-describing: the column-provenance rows for the `stores` table (column_name, data_source, description), loaded from dkkd/contract.py's DATA_DICTIONARY constant.",

    # --- Brand & company master ---
    'dim_brand_master': "Unified brand catalog: curated overlay (brands/_master/brand_master.yaml) x every brand config, classified via dkkd/retail_taxonomy.py's folder crosswalk. See docs/archive/superpowers/specs/2026-07-08-unified-company-brand-master-design.md (dkkd/brand_master.py::assemble_master_rows).",
    'dim_company': "VN MST-grain company dimension, unifying curated owners (brand_master.yaml owner_msts) with observed operators (stores.base_mst) — the two 'legal entity behind a brand' representations.",
    'bridge_brand_entity': "One row per (brand_slug, mst, role): role is 'owner_curated' | 'operator_observed' (or both, resolved to 'owner_operator' in v_brand_entities). n_locations is the observed DKKD license count for that (brand, mst) pair.",

    # --- Marts & views (dashboard/API-facing) ---
    'mart_brand_summary': "Store/license totals per (brand_slug, source), plus operating_count.",
    'mart_geo': "Store/license totals per (province, source), plus operating_count. Unresolved provinces roll up to 'Unknown'.",
    'mart_trend': "Store/license count per (opening year, source) — coarse trend axis over `stores`' current-state opening_date, not a real time series (see mart_store_series for that).",
    'mart_map_points': "Subset of `stores` with non-null lat/lng — dkkd rows never appear here (DKKD has no coordinates); only some website locators populate them.",
    'mart_store_series': "Real time-series axis (unlike mart_trend): totals per (as_of, source, brand_slug) aggregated from the append-only fact_store_snapshot.",
    'v_operating_stores': "The confirmed-operating-store subset: dkkd rows only, filtered by dkkd/contract.py's OPERATING_PREDICATE (core_operating_store='Yes' AND operating_status='Operating'). Use this, not raw `stores`, when a query means 'stores' and not 'licenses'.",
    'mart_brand_ecosystem': "Per-brand rollup (dkkd source only): n_licenses (raw), n_operating_stores (OPERATING_PREDICATE-filtered — never conflate the two), n_legal_entities, n_warehouses, n_corporate.",
    'v_brand_search': "dim_brand_master joined to mart_brand_ecosystem's counts — backs the brand search/typeahead surface.",
    'v_brand_entities': "bridge_brand_entity joined to dim_company, role collapsed to owner_operator when a brand's curated owner MST also shows up as an observed operator.",
    'mart_brand_scorecard': "One row per dkkd_master brand: store footprint (mart_brand_ecosystem) + YTD-opening estimate + top-3 provinces by operating-store count. Feeds /api/sector/top-brands.",

    # --- Macro-focus sources (macro-focus/README.md is the fuller narrative doc) ---
    'nso_sync_run': "NSO PX-Web extraction run metadata: timestamp, row counts.",
    'nso_matrix': "One row per NSO PX-Web matrix (population/labour domain).",
    'nso_dimension': "Ordered dimensions for each NSO matrix.",
    'nso_dimension_value': "Native NSO codes and labels for each dimension.",
    'nso_observation': "One row per NSO matrix cell: normalized year, geography, series label, numeric value, plus the lossless native-dimension JSON. Source contract: docs/api-contracts/nso.gov.vn.md.",
    'v_nso_macro_series': "nso_observation joined to nso_matrix (title, domain) — the shape v_nso_macro_series API-style consumers read.",
    'wb_sync_run': "World Bank Indicators extraction run metadata.",
    'wb_indicator': "One row per configured World Bank indicator (id, name, domain) — ~14-indicator curated core set.",
    'wb_observation': "One row per (indicator, country, year) cell. observation_key is the SHA-1 of indicator_id|country_iso3|year.",
    'v_worldbank_macro_series': "Flat projection of wb_observation — the shape macro/worldbank API routes read.",
    'moit_sync_run': "MOIT monthly report crawl/extraction run metadata.",
    'moit_report': "One row per crawled MOIT report (narrative + appendix); `parsed` flags which were actually parsed. Keyed on the site's own detail-page URL slug.",
    'moit_series': "One row per (report, sheet) pair actually parsed — 5 of ~10-12 appendix sheets per report (see macro-focus/README.md for which, and why the rest are out of scope).",
    'moit_observation': "One row per data cell: dimension (sector/country/category code+label) x metric (native header text, not hand-canonicalized) x value.",
    'v_moit_macro_series': "moit_observation joined to moit_series and moit_report — the flat shape ready for the (not-yet-wired) /api/v1/macro/moit/* routes.",
    'nso_market_sync_run': "NSO market-count (V08.04, classic PX-Web WebForms UI) extraction run metadata: timestamp, table title, row counts.",
    'nso_market_locality': "One row per locality: label, native table ordinal, row_type ('national'|'class_total'|'region_total'|'province'), and for provinces the enclosing region.",
    'nso_market_observation': "One row per (locality, year): market count, is_preliminary flags NSO's provisional latest-year figures. Annual, 2008-2024, province-level only — a count, not a market directory (no names/addresses/coordinates).",
    'v_nso_market_series': "nso_market_observation joined to nso_market_locality — locality x row_type x region x year x value, ready for the (not-yet-wired) /api/v1/macro/nso-market/* routes.",
}

# Per-table column overrides. Falls back to dkkd/contract.py's DATA_DICTIONARY
# (keyed by column name) for any column not listed here, since fact_store_snapshot
# and stores share most of their column meanings.
# "(see OPERATING_PREDICATE above)" reads fine inside contract.py itself (the
# constant is defined right above DATA_DICTIONARY there) but dangles once
# quoted into this standalone doc, so it's pointed at its actual home here.
_STORES_COL_NOTES = {
    name: f"{desc} _(data_source: {src})_".replace(
        '(see OPERATING_PREDICATE above)', "(see dkkd/contract.py's OPERATING_PREDICATE constant)")
    for name, src, desc in contract.DATA_DICTIONARY
}

COLUMN_NOTES = {
    'stores': _STORES_COL_NOTES,
    'fact_store_snapshot': {
        **{c: _STORES_COL_NOTES[c] for c in
           ('store_uid', 'source', 'brand_slug', 'operating_status', 'core_operating_store', 'province')
           if c in _STORES_COL_NOTES},
        'as_of': "Snapshot run date — the grain key alongside store_uid. Historical dates are never rewritten once their Parquet file exists.",
    },
    'benchmarks': {
        'brand_slug': "Brand directory slug.",
        'source': "IR source tag, e.g. 'masan' | 'mwg'.",
        'metric': "Name of the disclosed metric (e.g. a store-count line item).",
        'as_of': "Date the disclosure applies to / was reported.",
        'reported_value': "The disclosed numeric value.",
        'note': "Free-text context from the disclosure (e.g. report title/quarter).",
    },
    'dim_brand_master': {
        'brand_slug': "Brand directory slug — join key to `stores`/dkkd brand configs.",
        'record_source': "Row provenance — always 'dkkd_master' for this repo's brands (all brands come from a DKKD scrape config). See brand_master.py.",
        'canonical_name': "Display name for the brand.",
        'industry': "Top-level sector, from the curated overlay or the brand's config.yaml folder category.",
        'subsector': "Sub-sector, from the curated overlay or the brand's config.yaml folder subcategory.",
        'country_origin': "Brand's country of origin.",
        'domestic_foreign': "'domestic' | 'foreign' classification.",
        'nbo_is_local': "Whether the brand's owner (from domestic_foreign) is a local (Vietnamese) company.",
        'description': "Free-text brand description (curated overlay).",
        'website_slug': "Matching comp_website_scrapper brand slug, if this brand also has a website-locator config; null otherwise.",
        'owner_msts_json': "JSON blob of curated owner MST(s), from brands/_master/brand_master.yaml.",
        'search_blob': "Concatenated searchable text backing v_brand_search.",
        'gics_sector': "GICS-aligned rollup ('Consumer Staples'|'Consumer Discretionary') — dkkd.retail_taxonomy.",
        'retail_subsector': "NAICS/VSIC-aligned product-line rollup (e.g. Food & Beverage Retail) — dkkd.retail_taxonomy.",
        'retail_format': "Global classification leaf (e.g. 'Convenience Stores', 'Pharmacies') — dkkd.retail_taxonomy.",
        'channel_type': "'Retail'|'Foodservice'|'Services' — separates the store universe from foodservice subsectors (coffee/milk-tea chains).",
    },
    'dim_company': {
        'mst': "10-digit VN tax code (company legal-entity key).",
        'company_name': "Curated owner name if present, else a sampled DKKD registration name for this MST.",
        'is_curated_owner': "True if this MST appears in brands/_master/brand_master.yaml's owner_msts.",
        'is_observed': "True if this MST appears as an observed operator (stores.base_mst) in the DKKD scrape.",
    },
    'bridge_brand_entity': {
        'brand_slug': "Brand directory slug.",
        'mst': "10-digit VN tax code — FK to dim_company.mst.",
        'role': "'owner_curated' (from brand_master.yaml) | 'operator_observed' (from stores.base_mst).",
        'n_locations': "Observed DKKD license count for this (brand, mst) pair; only meaningful for operator_observed rows.",
    },
}

# Section title -> ordered list of table/view names. Anything live but not
# listed here falls into "Other" rather than being silently dropped.
SECTIONS = [
    ("Core store/license tables", ['stores', 'benchmarks', 'fact_store_snapshot', 'data_dictionary']),
    ("Brand & company master", ['dim_brand_master', 'dim_company', 'bridge_brand_entity']),
    ("Marts & views (dashboard/API-facing)", [
        'mart_brand_summary', 'mart_geo', 'mart_trend', 'mart_map_points', 'mart_store_series',
        'v_operating_stores', 'mart_brand_ecosystem', 'v_brand_search', 'v_brand_entities',
        'mart_brand_scorecard',
    ]),
    ("Macro-focus sources (see macro-focus/README.md)", [
        'nso_sync_run', 'nso_matrix', 'nso_dimension', 'nso_dimension_value', 'nso_observation', 'v_nso_macro_series',
        'wb_sync_run', 'wb_indicator', 'wb_observation', 'v_worldbank_macro_series',
        'moit_sync_run', 'moit_report', 'moit_series', 'moit_observation', 'v_moit_macro_series',
        'nso_market_sync_run', 'nso_market_locality', 'nso_market_observation', 'v_nso_market_series',
    ]),
]


def _render_table(con, name: str) -> str:
    cols = con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() "
        "WHERE table_name = ? ORDER BY column_index", [name],
    ).fetchall()
    notes = COLUMN_NOTES.get(name, {})
    lines = [f"### `{name}`", "", TABLE_NOTES.get(name, ''), "", "| Column | Type | Description |", "|---|---|---|"]
    for col_name, data_type in cols:
        desc = notes.get(col_name, '')
        lines.append(f"| `{col_name}` | {data_type} | {desc} |")
    return '\n'.join(lines)


def main() -> None:
    if not DB_PATH.exists():
        print(f"error: {DB_PATH} not found — run `python -m dkkd.cli pipeline` first.")
        sys.exit(1)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    live_tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables() WHERE internal = false").fetchall()}
    live_views = {r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE internal = false").fetchall()}
    live = live_tables | live_views

    sectioned = {name for _, names in SECTIONS for name in names}
    leftover = sorted(live - sectioned)
    sections = list(SECTIONS)
    if leftover:
        sections.append(("Other (undocumented — add these to scripts/generate_data_dictionary.py's SECTIONS)", leftover))

    parts = [
        "# Data Dictionary — Serving DuckDB",
        "",
        f"Auto-generated by `scripts/generate_data_dictionary.py` on {date.today().isoformat()} "
        f"from the live schema of `data/serving/dashboard.duckdb`. **Do not hand-edit the "
        f"tables below** — column names/types will be overwritten on the next run; edit "
        f"`TABLE_NOTES`/`COLUMN_NOTES` in the generator script instead, then re-run:",
        "",
        "```powershell",
        "python -m dkkd.cli pipeline   # rebuild the serving DB first if schema changed",
        "python scripts/generate_data_dictionary.py",
        "```",
        "",
        "Only tables/views present in the live DB are listed — an optional source not yet "
        "built (e.g. `dkkd pipeline` hasn't run since a new macro-focus sync) just won't "
        "appear here yet, it isn't a documentation gap.",
        "",
    ]
    for title, names in sections:
        present = [n for n in names if n in live]
        if not present:
            continue
        parts.append(f"## {title}")
        parts.append("")
        for n in present:
            parts.append(_render_table(con, n))
            parts.append("")
    con.close()

    OUTPUT_PATH.write_text('\n'.join(parts), encoding='utf-8')
    print(f"Wrote {OUTPUT_PATH} ({len(live)} tables/views documented)")


if __name__ == '__main__':
    main()
