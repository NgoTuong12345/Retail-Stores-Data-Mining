"""Extract + map DKKD, competitor-website, and IR sources into one conformed,
source-tagged store schema. This is the "silver" layer producer — dkkd/etl.py
writes what this module returns to Parquet and then to the serving DuckDB.

No cross-source dedup happens here: `source` tags provenance and rows from
different sources sit side-by-side (see CLAUDE.md's data-architecture plan —
there is no reliable join key between DKKD's `Id` and a website's `store_key`).
"""
import csv
import json
import re
from pathlib import Path

import yaml

from dkkd import retail_taxonomy
from dkkd.data.provinces import PROVINCES, REGION_BY_ACCENTED, REGION_POST_REFORM_BY_ACCENTED, _ascii_fold as ascii_fold
from dkkd.paths import DEFAULT_BRANDS_DIR as DEFAULT_DKKD_BRANDS_DIR, PACKAGE_ROOT
from dkkd.schema_export import classify_store_type, _DEFAULT_STORE_TYPE_PATTERNS
from dkkd.tenant import base_mst as _base_mst

# Original CSV column -> internal license-dict column name (relocated from
# dkkd/sqlite_export.py, since deleted — this module is the sole remaining
# consumer chain: _read_brand_csvs below, and brand_master.py via folder_taxonomy).
COLUMN_MAP = {
    'Id': 'id',
    'Name': 'name',
    'Name_F': 'name_f',
    'Name_MST': 'name_mst',
    'Short_Name': 'short_name',
    'Enterprise_Code': 'enterprise_code',
    'Enterprise_Gdt_Code': 'enterprise_gdt_code',
    'Status': 'dkkd_status',
    'Store_Brand_Format': 'store_brand_format',
    'Store_Type_MSN': 'store_type_msn',
    'Core_Operating_Store': 'core_operating_store',
    'Operating_Status': 'operating_status',
    'Operating_Evidence': 'operating_evidence',
    'City_Id': 'city_id',
    'City_Name': 'city_name',
    'Region': 'region',
    'Region_Post_Reform': 'region_post_reform',
    'District_Id': 'district_id',
    'District_Name': 'district_name',
    'Ward_Id': 'ward_id',
    'Ward_Name': 'ward_name',
    'Ho_Address': 'address',
    'Ho_Address_F': 'address_f',
    'Legal_First_Name': 'legal_first_name',
    # Date-inference columns — renamed to signal they are model output, not raw API data
    'Establishment_Date': 'inferred_date',
    'Establishment_Year': 'inferred_year',
    'Date_Confidence': 'date_confidence',
}

# Columns stored as INTEGER
INT_COLUMNS = {'id', 'inferred_year'}

DEFAULT_WEBSITE_BRANDS_DIR = PACKAGE_ROOT / 'data' / 'external' / 'website_brands'

# No structured IR extract exists yet: it's a live network fetcher / gitignored
# PDF/HTML cache — not something a scheduled local pipeline should depend on.
# This is a documented drop-in path: put a CSV here
# (brand_slug,metric,as_of,reported_value,note) to populate `benchmarks`;
# until then the table is simply empty.
DEFAULT_IR_BENCHMARKS_CSV = PACKAGE_ROOT / 'data' / 'external' / 'ir_benchmarks.csv'

CONFORMED_STORE_COLUMNS = [
    'store_uid', 'source', 'source_native_id',
    'brand_slug', 'brand_category', 'brand_subcategory',
    'store_brand_name', 'store_type', 'store_role',
    'core_operating_store', 'base_mst',
    'name', 'address', 'province', 'region', 'region_post_reform', 'district', 'ward',
    'lat', 'lng',
    'opening_date', 'date_confidence', 'operating_status',
    'enterprise_code', 'enterprise_gdt_code',
    'as_of', 'source_confidence',
    'gics_sector', 'retail_subsector', 'retail_format', 'channel_type',
]
DOUBLE_STORE_COLUMNS = {'lat', 'lng'}

BENCHMARK_COLUMNS = ['brand_slug', 'source', 'metric', 'as_of', 'reported_value', 'note']

# fact_store_snapshot grain (see dkkd/etl.py's snapshot backfill): a narrow
# projection of CONFORMED_STORE_COLUMNS, one row per (store_uid, as_of).
# Deliberately excludes slow-changing attributes (name, address, lat/lng) —
# those stay in `stores` only.
# ponytail: historical as_of parquet files are frozen once written (never
# rewritten) and DKKD history has no backfill path — changing this list
# breaks read_parquet's schema union across old vs new files; if you must
# change it, delete data/staging/snapshots/*.parquet and let it rebuild
# (website history re-backfills from normalized.json; dkkd history is lost).
SNAPSHOT_COLUMNS = ['store_uid', 'source', 'brand_slug', 'as_of', 'operating_status', 'core_operating_store', 'province']

_OBJECT_ID_RE = re.compile(r'^[0-9a-fA-F]{24}$')
_ADMIN_PREFIX_RE = re.compile(r'^(?:TINH|THANH PHO|TP\.?)\s+')
_PUNCT_RE = re.compile(r'[^A-Z0-9\s]')


def canonicalize_province(raw: str | None) -> str | None:
    """Match a raw city/province string against the 63-province list, returning
    the canonical ALL-CAPS accented form used by dkkd.data.provinces.

    Returns None for empty input or an opaque, non-resolvable value — e.g.
    FamilyMart's `province` field is a raw Mongo ObjectId, and ~36% of those
    don't even resolve against the site's own current location list. Anything
    else unrecognized is passed through unchanged rather than silently dropped.
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw or _OBJECT_ID_RE.match(raw):
        return None
    folded = ascii_fold(raw).upper()
    for p in PROVINCES:
        if folded == p.plain:
            return p.accented
    for p in PROVINCES:
        if p.plain in folded or folded in p.plain:
            return p.accented
    # DKKD's own City_Name carries an official "Tỉnh "/"Thành phố " prefix and
    # sometimes punctuation (e.g. "Bà Rịa - Vũng Tàu", "Thành phố Huế") that
    # defeats the substring checks above — strip both and retry once.
    stripped = _PUNCT_RE.sub(' ', _ADMIN_PREFIX_RE.sub('', folded))
    stripped = re.sub(r'\s+', ' ', stripped).strip()
    if stripped and stripped != folded:
        for p in PROVINCES:
            if stripped == p.plain or p.plain in stripped or stripped in p.plain:
                return p.accented
    return raw


def region_post_reform_for_province(canonical_province: str | None) -> str | None:
    """Look up the post-2025-reform region for a province already canonicalized
    by canonicalize_province(). Returns None for unresolved/foreign values
    that pass through canonicalize_province unchanged (not one of PROVINCES).

    Uses the post-reform mapping (not dkkd.data.provinces' traditional
    `region`) because this function serves BOTH DKKD rows and competitor-
    website rows, and a website's raw province string reflects whatever
    it's called today — old or new name, indistinguishable from the string
    alone — so only the "region of whatever this resolves to today" question
    is answerable uniformly across both sources.
    """
    if not canonical_province:
        return None
    return REGION_POST_REFORM_BY_ACCENTED.get(canonical_province)


def region_for_province(canonical_province: str | None) -> str | None:
    """Look up the traditional (pre-2025-reform) region for a province already
    canonicalized by canonicalize_province(). Returns None for unresolved
    values, same as region_post_reform_for_province() above.
    """
    if not canonical_province:
        return None
    return REGION_BY_ACCENTED.get(canonical_province)


def _null(val: str) -> str | None:
    """Convert empty string to None (SQL NULL). Relocated from sqlite_export.py."""
    return val if val.strip() else None


def folder_taxonomy(path: Path, brands_dir: Path):
    """(industry, subsector, slug) from brands/<industry>/<subsector>/<slug>/...
    The single canonical brand-taxonomy deriver — every consumer of the
    brands/ folder layout (this module, brand_master.py) routes through this
    instead of re-parsing the path independently. Relocated from sqlite_export.py."""
    parts = path.relative_to(brands_dir).parts
    return (parts[0] if len(parts) > 0 else None,
            parts[1] if len(parts) > 1 else None,
            parts[2] if len(parts) > 2 else None)


def _read_brand_csvs(brands_dir: Path) -> list[dict]:
    """Scan brands dir for full output CSVs and return list of license dicts.
    Relocated from sqlite_export.py."""
    skip_suffixes = {
        '_core_operating', '_non_operating', '_unverified',
        '_core_operating_raw', '_store_mapping',
    }
    rows: list[dict] = []
    seen_ids: set[int] = set()

    for csv_path in sorted(brands_dir.rglob('*.csv')):
        stem = csv_path.stem
        if any(stem.endswith(s) for s in skip_suffixes):
            continue
        # Expect path: brands/<category>/<subcategory>/<slug>/output/<slug>.csv
        rel = csv_path.relative_to(brands_dir)
        parts = rel.parts
        if len(parts) != 5 or parts[3] != 'output':
            continue
        category, subcategory, slug = folder_taxonomy(csv_path, brands_dir)

        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for raw in reader:
                mapped: dict[str, object] = {
                    'brand_slug': slug,
                    'brand_category': category,
                    'brand_subcategory': subcategory,
                }
                for src_col, dst_col in COLUMN_MAP.items():
                    val = _null(raw.get(src_col, ''))
                    if val is not None:
                        if dst_col in INT_COLUMNS:
                            try:
                                val = int(val)
                            except (ValueError, TypeError):
                                val = None
                    mapped[dst_col] = val

                store_id = mapped.get('id')
                if store_id is None:
                    continue
                if store_id in seen_ids:
                    continue  # cross-brand duplicate (same DKKD Id)
                seen_ids.add(store_id)
                rows.append(mapped)

    return rows


def extract_dkkd_stores(brands_dir: Path | None = None, as_of: str | None = None) -> list[dict]:
    """Conform every brand's full output CSV (via this module's own CSV
    walker — no duplicate discovery logic) into the shared store schema.
    """
    rows = _read_brand_csvs(brands_dir or DEFAULT_DKKD_BRANDS_DIR)
    out = []
    for r in rows:
        store_id = r.get('id')
        province = canonicalize_province(r.get('city_name'))
        taxonomy = retail_taxonomy.classify_by_folder(r.get('brand_subcategory'))
        out.append({
            'store_uid': f"dkkd:{store_id}",
            'source': 'dkkd',
            'source_native_id': str(store_id) if store_id is not None else None,
            'brand_slug': r.get('brand_slug'),
            'brand_category': r.get('brand_category'),
            'brand_subcategory': r.get('brand_subcategory'),
            **taxonomy,
            'store_brand_name': r.get('store_brand_format'),
            'store_type': r.get('store_type_msn'),
            'store_role': classify_store_type(r.get('name'), _DEFAULT_STORE_TYPE_PATTERNS),
            'core_operating_store': r.get('core_operating_store'),
            'base_mst': _base_mst({
                'Enterprise_Gdt_Code': r.get('enterprise_gdt_code'),
                'Enterprise_Code': r.get('enterprise_code'),
            }),
            'name': r.get('name'),
            'address': r.get('address'),
            'province': province,
            'region': region_for_province(province),
            'region_post_reform': region_post_reform_for_province(province),
            'district': r.get('district_name'),
            'ward': r.get('ward_name'),
            'lat': None,
            'lng': None,
            'opening_date': r.get('inferred_date'),
            'date_confidence': r.get('date_confidence'),
            'operating_status': r.get('operating_status'),
            'enterprise_code': r.get('enterprise_code'),
            'enterprise_gdt_code': r.get('enterprise_gdt_code'),
            'as_of': as_of,
            'source_confidence': r.get('operating_evidence'),
        })
    return out


def _to_float(value) -> float | None:
    """Coerce a locator's lat/lng value to float. Some scrapers (e.g. aeon)
    store these as strings, including empty string for unresolved records —
    treat both None and '' as missing rather than erroring.
    """
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_dirs(brand_dir: Path) -> list[Path]:
    """Every dated snapshot dir for a brand, oldest first."""
    snapshots_dir = brand_dir / 'snapshots'
    if not snapshots_dir.exists():
        return []
    return sorted(d for d in snapshots_dir.iterdir() if d.is_dir())


def _latest_snapshot_dir(brand_dir: Path) -> Path | None:
    dated = _snapshot_dirs(brand_dir)
    return dated[-1] if dated else None


def _brand_display_name(brand_dir: Path, slug: str) -> str:
    config_path = brand_dir / 'config.yaml'
    if config_path.exists():
        try:
            brand_cfg = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
            return brand_cfg.get('brand') or slug
        except yaml.YAMLError:
            pass
    return slug


def _conform_website_snapshot(slug: str, brand_name: str, snapshot_dir: Path) -> list[dict]:
    """Map one brand's one dated snapshot dir's normalized.json into the
    shared store schema. Shared by extract_website_stores (latest dir only)
    and extract_website_snapshot_history (every dir) so the per-record
    mapping logic lives in exactly one place.
    """
    normalized_path = snapshot_dir / 'normalized.json'
    if not normalized_path.exists():
        return []
    try:
        records = json.loads(normalized_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []

    as_of = snapshot_dir.name
    out = []
    for rec in records:
        store_key = rec.get('store_key')
        if not store_key:
            continue
        province = canonicalize_province(rec.get('province'))
        out.append({
            'store_uid': f"website:{slug}:{store_key}",
            'source': 'website',
            'source_native_id': str(store_key),
            'brand_slug': slug,
            'brand_category': None,
            'brand_subcategory': None,
            'gics_sector': None,
            'retail_subsector': None,
            'retail_format': None,
            'channel_type': None,
            'store_brand_name': brand_name,
            'store_type': None,
            'store_role': None,
            'core_operating_store': None,
            'base_mst': None,
            'name': rec.get('name'),
            'address': rec.get('address'),
            'province': province,
            'region': None,
            'region_post_reform': region_post_reform_for_province(province),
            'district': None,
            'ward': None,
            'lat': _to_float(rec.get('lat')),
            'lng': _to_float(rec.get('lng')),
            'opening_date': rec.get('opening_date'),
            'date_confidence': 'verified' if rec.get('opening_date') else None,
            'operating_status': 'Operating',
            'enterprise_code': None,
            'enterprise_gdt_code': None,
            'as_of': as_of,
            'source_confidence': None,
        })
    return out


def extract_website_stores(website_brands_dir: Path | None = None) -> list[dict]:
    """Conform each brand's latest store-locator snapshot (normalized.json)
    into the shared store schema. `as_of` is the real snapshot date, not the
    pipeline-run date — this data is a point-in-time capture.
    """
    base = website_brands_dir or DEFAULT_WEBSITE_BRANDS_DIR
    if not base.exists():
        return []

    out = []
    for brand_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        slug = brand_dir.name
        latest = _latest_snapshot_dir(brand_dir)
        if latest is None:
            continue
        brand_name = _brand_display_name(brand_dir, slug)
        out.extend(_conform_website_snapshot(slug, brand_name, latest))
    return out


def extract_website_snapshot_history(website_brands_dir: Path | None = None) -> list[dict]:
    """Same conformed row shape as extract_website_stores, but walks EVERY
    dated snapshot dir per brand instead of just the latest. Feeds
    fact_store_snapshot's historical backfill (dkkd/etl.py::build_staging) —
    most website brands have exactly 1 snapshot date today, but a brand
    re-scraped more than once (e.g. aeon, saigon-coop) has history sitting
    in earlier dated dirs that extract_website_stores never reads.

    Returns a flat list; each row's own `as_of` is its snapshot dir's date.
    """
    base = website_brands_dir or DEFAULT_WEBSITE_BRANDS_DIR
    if not base.exists():
        return []

    out = []
    for brand_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        slug = brand_dir.name
        brand_name = _brand_display_name(brand_dir, slug)
        for snapshot_dir in _snapshot_dirs(brand_dir):
            out.extend(_conform_website_snapshot(slug, brand_name, snapshot_dir))
    return out


def extract_ir_benchmarks(csv_path: Path | None = None) -> list[dict]:
    """Read manually-curated IR reference counts, if any exist yet. See
    DEFAULT_IR_BENCHMARKS_CSV's docstring above for why this is opt-in.
    """
    path = csv_path or DEFAULT_IR_BENCHMARKS_CSV
    if not path.exists():
        return []
    out = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            reported = row.get('reported_value')
            out.append({
                'brand_slug': row.get('brand_slug'),
                'source': 'ir',
                'metric': row.get('metric') or 'store_count',
                'as_of': row.get('as_of'),
                'reported_value': int(reported) if reported else None,
                'note': row.get('note'),
            })
    return out
