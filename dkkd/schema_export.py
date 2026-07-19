"""Standardized cross-brand output schema exporter.

Maps internal pipeline field names (Id, Enterprise_Code, Enterprise_Gdt_Code,
Name, ...) to a canonical analyst-facing schema. This is a read-only view built
on top of the already-postprocessed checkpoint.json — it never renames the
internal fields the engine's own dedupe/filter invariants (AGENTS.md) rely on.

Brand-specific store-type/confidence patterns live in config.yaml under
classification.schema_export; brands without that block get generic defaults.
"""
import csv
import json
import re
from datetime import date
from pathlib import Path

from dkkd.config import BrandConfig, load as load_config
from dkkd.geo import normalize_address_for_matching
from dkkd.paths import checkpoint_json, output_dir

STANDARD_SCHEMA_FIELDS = [
    'DKKD_internal_id', 'DKKD_enterprise_id', 'MST_gdt_code',
    'store_brand_name', 'store_brand_name_confidence', 'store_role', 'host_store', 'store_type',
    'store_name_details', 'store_name_pattern',
    'establishment_date_inferred', 'establishment_date_confidence',
    'establishment_month', 'establishment_quarter', 'establishment_year',
    'province_city_id', 'district_id', 'ward_id', 'full_address',
    'province_city_name', 'district_name', 'ward_name',
    'province_region', 'province_region_post_reform',
    'legal_representative', 'duplication_status', 'duplication_reason',
]

# Doc-level buckets (AGENTS.md's "Terminology" section): Retail -> 'retail_stores
# (operating)', Warehouse -> 'warehouse', everything else (Online/Services/
# Corporate/Other, see classify_store_type() below) -> 'office'.
_DEFAULT_STORE_TYPE_PATTERNS = [
    ('Retail', r'C[ỦƯỬU]A H[ÀA]NG'),
    ('Warehouse', r'\bKHO\b'),
    ('Online', r'\bONLINE\b'),
    ('Services', r'\bFARM\b|NÔNG SẢN'),
]

# Verified against the full BHX corpus (3185 records): BHX's own in-name store
# numbers follow one of two running counters, both near-perfectly correlated
# with DKKD registration order (Spearman >= 0.94) within their own scope —
# 'Province_Sequential' when a place name sits between the brand token and
# 'SỐ' (e.g. "... BÁCH HÓA XANH ĐỒNG NAI SỐ 145" = the 145th BHX store opened
# in Đồng Nai), else 'National_Sequential' for the chain-wide running code
# (e.g. "BÁCH HÓA XANH 30917", or "THANH HOÁ 14515" once the counter is large
# enough that "SỐ" is dropped). Order matters: province-with-SỐ must be tried
# before the bare brand-token rule, since both would otherwise match.
_DEFAULT_NAME_PATTERN_RULES = [
    ('Province_Sequential', r'(B[ÁA]CH H[ÓO]A XANH|BHX)\s+[A-ZÀ-Ỹ][A-ZÀ-Ỹ ]*?\s+S[ỐO]\s+\d+\.?\s*$'),
    ('National_Sequential', r'(B[ÁA]CH H[ÓO]A XANH|BHX)\s*(?:S[ỐO]\s*)?\d+\.?\s*$'),
    ('National_Sequential', r'\d+\.?\s*$'),
]


def _first_match(name: str, patterns: list[tuple[str, str]]) -> str | None:
    n = (name or '').upper()
    for label, pattern in patterns:
        if re.search(pattern, n):
            return label
    return None


def classify_store_type(name: str, patterns: list[tuple[str, str]]) -> str:
    """Categorize a DKKD registration name by function, in pattern priority order.

    Falls back to 'Corporate' when the name has no ' - '/'– ' store-descriptor
    separator at all (a bare company/branch registration always looks like
    that), else 'Other' for names that need manual review.
    """
    label = _first_match(name, patterns)
    if label:
        return label
    if not re.search(r'[-–]', (name or '').upper()):
        return 'Corporate'
    return 'Other'


def classify_store_name_pattern(name: str, store_type: str, patterns: list[tuple[str, str]]) -> str:
    """Label which store-numbering convention a name follows.

    Only meaningful for Retail-type records — non-retail entities (warehouses,
    online fulfillment, bare corporate registrations) don't carry a store
    sequence number at all. A Retail name that doesn't match either running-
    counter pattern is 'Street_Address' — the early rollout named some stores
    after their house-number + street instead of a sequence code.
    """
    if store_type != 'Retail':
        return 'Not_Applicable'
    return _first_match(name, patterns) or 'Street_Address'


def compute_duplication_info(stores: list[dict]) -> dict[str, dict[str, str]]:
    """Map each record's Id to its duplication_status and duplication_reason.

    Reuses the same normalized-address matching the legacy-migration audit
    already relies on (dkkd.geo.normalize_address_for_matching), and the same
    exact-vs-substring confidence split dkkd.audit.audit_legacy_migration uses
    — so this is a second lens on the same signal, not a new heuristic. The
    point is to flag likely duplicates without dropping any row: a record
    marked here still shows up everywhere else in the export, and the reason
    names the other Id(s) responsible so a reviewer can go verify it directly.

    'high'   = another record has the exact same normalized address.
    'medium' = another record's normalized address is a substring match (one
               contains the other, len > 10, matching the audit's fuzzy-match
               threshold) — likely the same location written with more/less
               detail, less certain than an exact match.
    'low'    = no other record's address matches this one at all; reason is
               blank since there is nothing to explain.
    """
    ids = [r.get('Id', '') for r in stores]
    norms = [
        normalize_address_for_matching(r.get('Ho_Address') or r.get('Ho_Address_F') or '')
        for r in stores
    ]

    exact_ids: dict[str, list[str]] = {}
    for rid, n in zip(ids, norms):
        if n:
            exact_ids.setdefault(n, []).append(rid)

    info: dict[str, dict[str, str]] = {}
    for rid, n in zip(ids, norms):
        if not n:
            info[rid] = {'status': 'low', 'reason': ''}
            continue

        exact_others = [i for i in exact_ids[n] if i != rid]
        if exact_others:
            info[rid] = {
                'status': 'high',
                'reason': f"Exact address match with Id {', '.join(exact_others)}",
            }
            continue

        substring_others: list[str] = []
        if len(n) > 10:
            for other_norm, other_ids in exact_ids.items():
                if other_norm != n and (n in other_norm or other_norm in n):
                    substring_others.extend(other_ids)
        if substring_others:
            info[rid] = {
                'status': 'medium',
                'reason': f"Address partially overlaps with Id {', '.join(substring_others)}",
            }
        else:
            info[rid] = {'status': 'low', 'reason': ''}
    return info


def classify_brand_confidence(name: str, high_patterns: list[str], low_patterns: list[str]) -> str:
    """Rate how confidently a record's Name is the brand's own official entity.

    'high' = matches a known official/legacy-parent entity phrase.
    'low' = matches a structurally different entity form (e.g. a TNHH company)
            known to collide with the brand's search keywords.
    'medium' = neither — a same-brand-ish but unverified entity; must not be
               silently folded into high or low.
    """
    n = (name or '').upper()
    if any(re.search(p, n) for p in high_patterns):
        return 'high'
    if any(re.search(p, n) for p in low_patterns):
        return 'low'
    return 'medium'


def _quarter_from_month(month: int) -> int:
    return (month - 1) // 3 + 1


def _month_and_quarter(establishment_date: str | None) -> tuple:
    if not establishment_date or len(establishment_date) < 7 or establishment_date[4] != '-':
        return '', ''
    try:
        month = int(establishment_date[5:7])
    except ValueError:
        return '', ''
    return month, _quarter_from_month(month)


def build_standard_schema(config: BrandConfig, stores: list[dict]) -> list[dict]:
    """Build the canonical schema rows from postprocessed internal records."""
    rules = config.classification.get('schema_export', {})
    store_type_patterns = (
        [tuple(p) for p in rules.get('store_type_patterns', [])]
        or _DEFAULT_STORE_TYPE_PATTERNS
    )
    high_patterns = rules.get('official_entity_patterns', [])
    low_patterns = rules.get('low_confidence_patterns', [])
    name_pattern_rules = (
        [tuple(p) for p in rules.get('name_pattern_rules', [])]
        or _DEFAULT_NAME_PATTERN_RULES
    )
    dup_info = compute_duplication_info(stores)

    rows = []
    for r in stores:
        name = r.get('Name', '')
        est_date = r.get('Establishment_Date')
        month, quarter = _month_and_quarter(est_date)
        store_type = classify_store_type(name, store_type_patterns)
        rows.append({
            'DKKD_internal_id': r.get('Id', ''),
            'DKKD_enterprise_id': r.get('Enterprise_Code', ''),
            'MST_gdt_code': r.get('Enterprise_Gdt_Code', ''),
            'store_brand_name': config.name,
            'store_brand_name_confidence': classify_brand_confidence(name, high_patterns, low_patterns),
            'store_role': r.get('store_role', 'own_store'),
            'host_store': r.get('host_store', ''),
            'store_type': store_type,
            'store_name_details': (name or '').strip(),
            'store_name_pattern': classify_store_name_pattern(name, store_type, name_pattern_rules),
            'establishment_date_inferred': est_date or '',
            'establishment_date_confidence': r.get('Date_Confidence', ''),
            'establishment_month': month,
            'establishment_quarter': quarter,
            'establishment_year': r.get('Establishment_Year', ''),
            'province_city_id': r.get('City_Id', ''),
            'district_id': r.get('District_Id', ''),
            'ward_id': r.get('Ward_Id', ''),
            'full_address': r.get('Ho_Address', ''),
            'province_city_name': r.get('City_Name', ''),
            'district_name': r.get('District_Name', ''),
            'ward_name': r.get('Ward_Name', ''),
            'province_region': r.get('Region', ''),
            'province_region_post_reform': r.get('Region_Post_Reform', ''),
            'legal_representative': r.get('Legal_First_Name', ''),
            'duplication_status': dup_info.get(r.get('Id', ''), {}).get('status', 'low'),
            'duplication_reason': dup_info.get(r.get('Id', ''), {}).get('reason', ''),
        })
    return rows


def sort_chronologically(rows: list[dict]) -> list[dict]:
    """Sort standard-schema rows oldest-first by establishment_date_inferred.

    Rows with no inferred date sort last — an unknown date is not the same as
    the oldest possible one. Ties break on DKKD_internal_id for determinism.
    """
    def _key(row):
        date = row.get('establishment_date_inferred') or ''
        return (date == '', date, row.get('DKKD_internal_id') or '')

    return sorted(rows, key=_key)


def _load_stores(slug: str, brands_dir: Path | None = None) -> list[dict]:
    with open(checkpoint_json(slug, brands_dir), encoding='utf-8') as f:
        pairs = json.load(f)
    return [item[1] if isinstance(item, list) else item for item in pairs]


# Columns that look numeric but must never be type-inferred: leading zeros
# (MST_gdt_code Format A, e.g. '00520') and embedded dashes (Format B, e.g.
# '0310471746-315') are both significant. Excel silently mangles these the
# moment the .csv is opened/saved in it (see docs memory pipeline-csv-excel-
# corruption) — the .xlsx sibling below pins them to Text format so that
# can't happen regardless of how the file is opened.
_TEXT_FORMAT_FIELDS = ('DKKD_internal_id', 'DKKD_enterprise_id', 'MST_gdt_code')


def _write_xlsx_copy(rows: list[dict], path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(STANDARD_SCHEMA_FIELDS)

    text_cols = [i for i, f in enumerate(STANDARD_SCHEMA_FIELDS, start=1) if f in _TEXT_FORMAT_FIELDS]
    for row in rows:
        ws.append([row.get(f, '') for f in STANDARD_SCHEMA_FIELDS])

    for col in text_cols:
        for cell in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            c = cell[0]
            c.number_format = '@'
            if c.value is not None:
                c.value = str(c.value)

    wb.save(path)


def write_metadata(config: BrandConfig, row_count: int, out_dir: Path, slug: str) -> Path:
    """Write a metadata.json summarizing this export run (slug, row count, when)."""
    out_path = out_dir / 'metadata.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'brand_slug': slug,
            'brand_name': config.name,
            'generated_at': date.today().isoformat(),
            'row_count': row_count,
            'source_checkpoint': 'checkpoint.json',
        }, f, indent=2, ensure_ascii=False)
    return out_path


def write_standard_schema(config: BrandConfig, stores: list[dict], out_dir: Path, slug: str) -> Path:
    """Build standard-schema rows from already-loaded config/stores and write CSV + xlsx.

    Also writes a `.xlsx` sibling with ID/code columns pinned to Text format —
    open that copy (not the .csv) in Excel to avoid leading-zero/dash corruption —
    and a metadata.json summarizing the export run.
    """
    rows = sort_chronologically(build_standard_schema(config, stores))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{slug}_standard_schema.csv'
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=STANDARD_SCHEMA_FIELDS)
        w.writeheader()
        w.writerows(rows)

    _write_xlsx_copy(rows, out_dir / f'{slug}_standard_schema.xlsx')
    write_metadata(config, len(rows), out_dir, slug)
    return out_path


def export_standard_schema(slug: str, brands_dir: Path | None = None) -> Path:
    """Load a brand's postprocessed checkpoint and write the standard-schema CSV."""
    config = load_config(slug, brands_dir)
    stores = _load_stores(slug, brands_dir)
    return write_standard_schema(config, stores, output_dir(slug, brands_dir), slug)
