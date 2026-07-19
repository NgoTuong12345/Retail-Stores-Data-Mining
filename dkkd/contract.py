"""Single source of truth for two things that used to drift across
dkkd/etl.py (3 copies) and the now-deleted dkkd/sqlite_export.py (1 copy):

  OPERATING_PREDICATE  SQL boolean expression deciding whether a dkkd row
                        counts as an operating store (see AGENTS.md's
                        "Terminology: License vs. Store"). Interpolate this
                        into a WHERE/FILTER clause instead of retyping the
                        literal `core_operating_store = 'Yes' AND
                        operating_status = 'Operating'`.
  DATA_DICTIONARY      Merged column-provenance rows for the serving DuckDB
                        `stores` table, describing what survives past the
                        sqlite `licenses` table's removal.

This module is deliberately just two literal constants — no class hierarchy,
no plugin registry.
"""

OPERATING_PREDICATE = "core_operating_store = 'Yes' AND operating_status = 'Operating'"


# DATA_DICTIONARY: one row per `stores` table column, as
# (column_name, data_source, description). Carried over from etl.py's former
# file-local _DATA_DICTIONARY_ROWS (columns of the serving `stores` table,
# which survives), not merged with the now-deleted sqlite_export.py's
# DATA_DICTIONARY_ROWS (columns of the `licenses` table, which was dropped
# along with that module) — the two dictionaries described different tables
# with mostly non-overlapping column names, so rows aren't force-merged
# one-per-concept.
#
# Naming traps — same concept, different column names across layers. Kept as
# comments (not fake rows) so they don't pollute the real data_dictionary
# table that gets loaded into the serving DuckDB / exposed via the API.
#
# 1. store_type/store_role swap: the analyst standard_schema CSV
#    (dkkd/schema_export.py, STANDARD_SCHEMA_FIELDS + the row-building loop
#    around line 206-215) uses store_type for the function classification
#    (Retail/Warehouse/Online/Services/Corporate/Other, from
#    classify_store_type()) and store_role for an own-store/host-franchise
#    concept (r.get('store_role', 'own_store')). The serving DuckDB `stores`
#    table (dkkd/conform.py:120-121) uses the SAME two column names for
#    SWAPPED concepts: store_type = the MSN classification (store_type_msn),
#    store_role = the function classification (the same classify_store_type()
#    call the CSV puts under store_type). Don't assume store_type means the
#    same thing in both places.
#
# 2. MST_gdt_code/DKKD_enterprise_id inversion: in the analyst
#    standard_schema CSV (dkkd/schema_export.py:209-210), DKKD_enterprise_id
#    holds the actual 10-digit MST (tax code) and MST_gdt_code holds the GDT
#    branch code — which is NOT an MST despite the column name. The
#    serving/sqlite layers name these more plainly (enterprise_code = MST,
#    enterprise_gdt_code = GDT code). The analyst CSV is frozen and can't be
#    renamed; don't assume MST_gdt_code contains an MST.
#
# 3. The inferred/opening date has 4 name-sets for one concept:
#    Establishment_Date/Establishment_Year/Date_Confidence (internal
#    per-brand CSV) -> inferred_date/inferred_year/date_confidence (was:
#    sqlite `licenses` table) -> opening_date/date_confidence (serving
#    `stores` table, year dropped) -> establishment_date_inferred/
#    establishment_year/establishment_date_confidence (analyst
#    standard_schema CSV). Same underlying model output throughout.
DATA_DICTIONARY = [
    ('store_uid', 'conform', "Synthetic PK: 'dkkd:<id>' or 'website:<slug>:<store_key>'."),
    ('source', 'conform', "'dkkd' | 'website' — provenance tag. No cross-source dedup is attempted."),
    ('source_native_id', 'conform', 'The id native to that source (DKKD Id, or the locator store_key).'),
    ('brand_slug', 'conform', 'Brand directory slug.'),
    ('brand_category', 'conform', 'Top-level sector (dkkd source only; null for website rows).'),
    ('brand_subcategory', 'conform', 'Sub-sector (dkkd source only; null for website rows).'),
    ('store_brand_name', 'conform', 'Human brand label (store_brand_format for dkkd; brand display name for website).'),
    ('store_type', 'conform', 'MSN store-type classification (dkkd source only; null for website rows).'),
    ('store_role', 'conform', "Function classification from the raw registration name: 'Retail'|'Warehouse'|'Online'|'Services'|'Corporate'|'Other' (dkkd source only; null for website rows). Doc-level buckets (AGENTS.md's 'Terminology' section): Retail='retail_stores (operating)', Warehouse='warehouse', everything else='office'. See dkkd.schema_export.classify_store_type."),
    ('core_operating_store', 'postprocess', "'Yes'|'No' — whether this license counts in the active footprint (dkkd source only; null for website rows). Combine with operating_status='Operating' (see OPERATING_PREDICATE above) for the core-footprint filter; never count raw licenses as stores. Note this is still an *unverified* inference (locator-pin/GDT-signal evidence, not a captcha-fetched detail page) — see AGENTS.md's 'Terminology' section."),
    ('base_mst', 'postprocess', "10-digit operator MST derived from enterprise_gdt_code/enterprise_code (dkkd source only; '' if none encoded, null for website rows). See dkkd.tenant.base_mst."),
    ('name', 'raw', 'Store/registration name, in the source\'s own casing/language.'),
    ('address', 'raw', 'Full address string, in the source\'s own format.'),
    ('province', 'conform', 'Canonicalized against the 63-province list where resolvable; passthrough otherwise; null if opaque (e.g. a locator ObjectId).'),
    ('region', 'conform', "Traditional (pre-2025-reform) region of the canonicalized province (dkkd source only; null for website rows — no equivalent traditional-region concept for a locator's raw province string). Null if province did not resolve."),
    ('region_post_reform', 'conform', "Region (post-July-2025-reform mapping) of the canonicalized province. Derived (not a pre-merge/raw field) because a raw address string can't distinguish an old vs new province name, so only 'region of whatever this resolves to today' is answerable for both dkkd and website rows. Null if province did not resolve."),
    ('district', 'raw', 'Parsed district name (dkkd source only; null for website rows).'),
    ('ward', 'raw', 'Parsed ward name (dkkd source only; null for website rows).'),
    ('lat', 'raw', 'Latitude. Null for all dkkd rows (DKKD has no coordinates). Populated for website rows only where that locator scraper extracts it.'),
    ('lng', 'raw', 'Longitude. Same caveat as lat.'),
    ('opening_date', 'model/raw', 'dkkd: model-inferred (date_inference, +/- months). website: the locator\'s own date field, treated as verified where present.'),
    ('date_confidence', 'model/raw', "dkkd: 'high'|'medium'|'low'|'exact'. website: 'verified' or null."),
    ('operating_status', 'model/raw', "dkkd: 'Operating'|'Closed'|'Unverified' — an inferred confidence tier from the evidence ladder (dkkd/operating_status.py), not captcha-verified ground truth; treat 'Operating'/'Closed' here as unverified until confirmed via dkkd-fetch-details. website: always 'Operating' (a live listing implies operating)."),
    ('enterprise_code', 'raw', 'DKKD MST tax code (dkkd source only).'),
    ('enterprise_gdt_code', 'raw', 'DKKD GDT branch code (dkkd source only).'),
    ('as_of', 'conform', 'dkkd: pipeline-run date (no natural per-record export date upstream). website: the real snapshot capture date.'),
    ('source_confidence', 'conform', 'dkkd: the operating_evidence note. website: currently unused (null).'),
    ('gics_sector', 'conform', "GICS-aligned rollup: 'Consumer Staples'|'Consumer Discretionary' (dkkd source only, via brand_subcategory crosswalk; null for website rows). See dkkd.retail_taxonomy."),
    ('retail_subsector', 'conform', 'NAICS/VSIC-aligned product-line rollup, e.g. Food & Beverage Retail, Health & Personal Care Retail (dkkd source only; null for website rows).'),
    ('retail_format', 'conform', "Global classification leaf from the retail taxonomy crosswalk, e.g. 'Convenience Stores', 'Pharmacies' (dkkd source only; null for website rows). See dkkd.retail_taxonomy."),
    ('channel_type', 'conform', "'Retail'|'Foodservice'|'Services' — separates the store universe from foodservice-classified subsectors like coffee/milk-tea chains, which sit outside the retail-only category tree (dkkd source only; null for website rows)."),
]
