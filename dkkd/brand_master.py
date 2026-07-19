"""Assemble the unified brand master: curated overlay × all brand configs,
classified via dkkd/retail_taxonomy.py's VN folder crosswalk. Pure Python;
dkkd/etl.py materializes the returned rows into dim_brand_master. See
docs/archive/superpowers/specs/2026-07-08-unified-company-brand-master-design.md.
"""
import json
from pathlib import Path

import yaml

from dkkd import retail_taxonomy
from dkkd.data.provinces import _ascii_fold as ascii_fold
from dkkd.conform import folder_taxonomy
from dkkd.paths import PACKAGE_ROOT

_ROOT = PACKAGE_ROOT
DEFAULT_BRANDS_DIR = _ROOT / 'brands'
DEFAULT_MASTER_PATH = _ROOT / 'brands' / '_master' / 'brand_master.yaml'

MASTER_COLUMNS = [
    'brand_slug', 'record_source', 'canonical_name',
    'industry', 'subsector', 'country_origin', 'domestic_foreign', 'nbo_is_local',
    'description', 'website_slug', 'owner_msts_json', 'search_blob',
    'gics_sector', 'retail_subsector', 'retail_format', 'channel_type',
]


def load_overlay(master_path=None) -> dict:
    path = Path(master_path) if master_path else DEFAULT_MASTER_PATH
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or []
    return {r['slug']: r for r in data}


def assemble_curated_entities(master_path=None):
    """Curated half of the brand<->legal-entity bridge, from owner_msts in the
    overlay. dkkd/etl.py's _create_company_dim unions this with the observed
    half (derived in SQL from stores.base_mst) into dim_company/bridge_brand_entity.

    Returns (company_rows, bridge_rows):
      company_rows: [(mst, owner_name)]
      bridge_rows:  [(brand_slug, mst, 'owner_curated', None)]
    """
    overlay = load_overlay(master_path)
    companies, bridge = [], []
    for slug, o in overlay.items():
        for mst, name in (o.get('owner_msts') or {}).items():
            # An unquoted MST starting with 0 whose digits are all 0-7 (e.g.
            # 0301234567) parses as a YAML 1.1 octal int, not a string — the
            # int is a DIFFERENT number, not a fixable typo, so fail loud
            # rather than silently building a company row under a wrong mst.
            if not (isinstance(mst, str) and mst.isdigit() and len(mst) == 10):
                raise ValueError(
                    f"brand_master[{slug}]: owner_msts key {mst!r} must be a quoted "
                    f"10-digit MST string — unquoted values starting with 0 can be "
                    f"misparsed as a YAML octal integer"
                )
            companies.append((mst, name))
            bridge.append((slug, mst, 'owner_curated', None))
    return companies, bridge


def assemble_master_rows(brands_dir=None, master_path=None) -> list[dict]:
    brands_dir = Path(brands_dir) if brands_dir else DEFAULT_BRANDS_DIR
    overlay = load_overlay(master_path)
    rows = []

    for cfg_path in sorted(brands_dir.rglob('config.yaml')):
        industry, subsector, slug = folder_taxonomy(cfg_path.parent, brands_dir)
        cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
        o = overlay.get(slug, {})
        industry = o.get('industry_override') or industry
        subsector = o.get('subsector_override') or subsector

        domestic_foreign = o.get('domestic_foreign')
        name = cfg.get('name') or slug
        owner_msts = o.get('owner_msts') or {}
        blob = ascii_fold(' '.join(filter(None, [name, slug, *owner_msts.values()]))).lower()

        taxonomy = retail_taxonomy.classify_by_folder(subsector)

        rows.append({
            'brand_slug': slug, 'record_source': 'dkkd_master', 'canonical_name': name,
            'industry': industry, 'subsector': subsector,
            'country_origin': o.get('country_origin'), 'domestic_foreign': domestic_foreign,
            'nbo_is_local': (domestic_foreign == 'Domestic') if domestic_foreign else None,
            'description': o.get('description'), 'website_slug': o.get('website_slug'),
            'owner_msts_json': json.dumps(owner_msts, ensure_ascii=False),
            'search_blob': blob,
            **taxonomy,
        })
    return rows
