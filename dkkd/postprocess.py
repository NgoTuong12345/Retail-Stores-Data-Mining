"""Post-scrape classification and enrichment pipeline.

Stages:
  1. Load checkpoint → list[dict]
  2. Status refinement (entity_status map)
  3. Date interpolation (masothue.com calibration)
  4. Store classification (format + MSN + core_operating)
  5. Geo enrichment (city/district/ward parsing)
  6. Export: full CSV, unverified CSV, standard-schema CSV/xlsx

Usage:
  dkkd postprocess --brand winmart
  dkkd postprocess --brand winmart --skip-date-calibration
"""
import json
import csv
from pathlib import Path
from datetime import datetime

import pandas as pd

from dkkd.config import load as load_config
from dkkd.paths import checkpoint_json, output_dir
from dkkd.enrich import (
    build_calibration_model,
    build_global_id_date_model,
    apply_date_interpolation,
    refine_entity_statuses,
    enrich_store_names,
    refine_statuses_from_dpi,
    resolve_format_a_branch_statuses,
)
from dkkd.enrich_masothue import sweep_masothue_urls, fetch_masothue_statuses
from dkkd.classify import classify_all
from dkkd.geo import parse_geo
from dkkd.operating_status import resolve_operating_status, load_locator_pins, _extract_mst
from dkkd.closure_signals import build_closure_signal_map
from dkkd.taxpayer import load_status_cache
from dkkd.schema_export import write_standard_schema



def _load_stores(slug: str, brands_dir: Path | None = None) -> list[dict]:
    """Load store records from checkpoint.json."""
    cp_path = checkpoint_json(slug, brands_dir)
    with open(cp_path, 'r', encoding='utf-8') as f:
        pairs = json.load(f)
    return [item[1] if isinstance(item, list) else item for item in pairs]


def _save_checkpoint(stores: list[dict], slug: str, brands_dir: Path | None = None) -> None:
    """Save enriched stores back to checkpoint.json."""
    cp_path = checkpoint_json(slug, brands_dir)
    pairs = [[r['Id'], r] for r in stores]
    with open(cp_path, 'w', encoding='utf-8') as f:
        json.dump(pairs, f, ensure_ascii=False)


def _ordered_fieldnames(stores: list[dict]) -> list[str]:
    """Return column order: priority columns first, then everything else.

    Priority order mirrors the analyst's expected Excel column layout:
    classification columns → identity → dates → geography → address → legal.
    """
    priority = [
        'Id', 'Store_Brand_Format', 'Store_Type_MSN', 'Core_Operating_Store',
        'Operating_Status', 'Operating_Evidence',
        'Name', 'Name_MST', 'Name_F', 'Short_Name',
        'Enterprise_Code', 'Enterprise_Gdt_Code',
        'Status', 'Establishment_Date', 'Establishment_Year', 'Date_Confidence',
        'City_Id', 'City_Name', 'District_Id', 'District_Name',
        'Ward_Id', 'Ward_Name', 'Region', 'Region_Post_Reform',
        'Ho_Address', 'Ho_Address_F', 'Legal_First_Name',
    ]
    all_keys = []
    seen = set()
    for r in stores:
        for k in r:
            if k not in seen and k != '__type':
                all_keys.append(k)
                seen.add(k)

    ordered = [k for k in priority if k in seen]
    ordered += [k for k in all_keys if k not in set(ordered)]
    return ordered


def _export_csv(stores: list[dict], path: Path, fallback_fields: list[str] | None = None) -> None:
    """Write stores to a CSV with ordered columns and UTF-8 BOM for Excel."""
    if not stores:
        if fallback_fields:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                csv.DictWriter(f, fieldnames=fallback_fields, extrasaction='ignore').writeheader()
        else:
            path.write_text('')
        return
    fields = _ordered_fieldnames(stores)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(stores)


def _enrich_geo(stores: list[dict]) -> None:
    """Resolve city/district/ward names using global GeoLookup with local address parsing fallback."""
    from dkkd.data import get_geo_lookup
    lookup = get_geo_lookup()

    # Collect any custom local mappings from this sweep for newly created/unmapped IDs
    local_cities = {}
    local_dists = {}
    local_wards = {}

    for r in stores:
        addr = r.get('Ho_Address') or r.get('Ho_Address_F')
        city, dist, ward = parse_geo(addr)
        cid, did, wid = r.get('City_Id'), r.get('District_Id'), r.get('Ward_Id')
        if cid and city:
            local_cities[str(cid)] = city.strip()
        if did and dist:
            local_dists[str(did)] = dist.strip()
        if wid and ward:
            local_wards[str(wid)] = ward.strip()

    resolved_cities = 0
    resolved_districts = 0
    resolved_wards = 0

    for r in stores:
        cid = str(r.get('City_Id', ''))
        did = str(r.get('District_Id', ''))
        wid = str(r.get('Ward_Id', ''))

        # 1. City name
        city_name = lookup.get_city_name(cid) if cid else None
        if not city_name and cid:
            city_name = local_cities.get(cid)
        r['City_Name'] = city_name or ''
        if city_name:
            resolved_cities += 1

        # 1b. Region: traditional (this province's own region) and
        # post-reform (region of whatever it merged into in July 2025) —
        # see dkkd.data.provinces module docstring for why both exist.
        r['Region'] = (lookup.get_region(cid) if cid else None) or ''
        r['Region_Post_Reform'] = (lookup.get_region_post_reform(cid) if cid else None) or ''

        # 2. District name
        dist_name = lookup.get_district_name(did) if did else None
        if not dist_name and did:
            dist_name = local_dists.get(did)
        r['District_Name'] = dist_name or ''
        if dist_name:
            resolved_districts += 1

        # 3. Ward name
        ward_name = lookup.get_ward_name(wid) if wid else None
        if not ward_name and wid:
            ward_name = local_wards.get(wid)
        r['Ward_Name'] = ward_name or ''
        if ward_name:
            resolved_wards += 1

    print(f"  [postprocess] Resolved (Lookup + Local Fallback): "
          f"{resolved_cities} cities, {resolved_districts} districts, {resolved_wards} wards")


def run_pipeline(slug: str, *, brands_dir: Path | None = None,
                 skip_date_calibration: bool = False,
                 cap: int | None = None,
                 dpi_status_file: str | None = None,
                 masothue_status: bool = False) -> dict:
    """Execute the full post-scrape pipeline.

    Args:
        slug: Brand slug (e.g. 'winmart')
        brands_dir: Override brands directory
        skip_date_calibration: If True, skip masothue.com HTTP calls
                              (uses existing Establishment_Date values)

    Returns:
        Summary dict with counts by format.
    """
    config = load_config(slug, brands_dir)
    cls_rules = config.classification
    opt_in = bool(cls_rules.get('operating_status', {}).get('enabled'))

    print(f"{'='*60}")
    print(f"Post-Scrape Classification Pipeline: {config.name}")
    print(f"{'='*60}")

    # ── Stage 1: Load checkpoint ──
    stores = _load_stores(slug, brands_dir)
    print(f"\n[Stage 1] Loaded {len(stores)} records from checkpoint")

    # ── Stage 1b: Audit filter ──
    from dkkd.audit_stores import apply_audit_filter
    stores, n_rejected = apply_audit_filter(stores, slug, brands_dir)
    if n_rejected:
        print(f"[Stage 1b] Filtered {n_rejected} audit-rejected records "
              f"({len(stores)} remaining)")

    # ── Stage 1.5: masothue.com per-store status sweep (opt-in) ──
    # Runs before Stage 2 so its statuses flow through load_status_cache
    # (which reads masothue_store_statuses.json) into the resolver chain.
    if masothue_status:
        print(f"[Stage 1.5] Sweeping masothue.com for per-store operating status...")
        url_map = sweep_masothue_urls(stores, seed_parent_msts=set(config.seed_parent_msts or []))
        statuses = fetch_masothue_statuses(url_map)
        ms_path = output_dir(slug, brands_dir) / 'masothue_store_statuses.json'
        ms_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ms_path, 'w', encoding='utf-8') as f:
            json.dump(statuses, f, ensure_ascii=False, indent=2)
        print(f"[Stage 1.5] Wrote {len(statuses)} masothue statuses → {ms_path.name}")

    # Load masothue status cache once — used by Stage 3 for calibration and
    # exact ngay_hd overrides. Reads from file whether Stage 1.5 just wrote it
    # or it was produced by a prior postprocess run.
    ms_path = output_dir(slug, brands_dir) / 'masothue_store_statuses.json'
    masothue_statuses: dict = {}
    if ms_path.exists():
        with open(ms_path, encoding='utf-8') as f:
            masothue_statuses = json.load(f)

    ed_path = output_dir(slug, brands_dir) / 'enterprise_details.json'
    enterprise_details: dict = {}
    if ed_path.exists():
        with open(ed_path, encoding='utf-8') as f:
            enterprise_details = json.load(f)
        print(f"[Stage 3 pre] Loaded {len(enterprise_details)} enterprise_details records")

    # ── Stage 2: Status refinement ──
    entity_status = cls_rules.get('entity_status', {})
    gdt_cache = {}
    if entity_status:
        refine_entity_statuses(stores, entity_status)
        active = sum(1 for r in stores if r.get('Status') == 'NNT đang hoạt động')
        print(f"[Stage 2] Refined entity statuses ({active} active, "
              f"{len(stores) - active} ceased/inactive)")
    else:
        # Fallback to the GDT cache file
        gdt_cache = load_status_cache(slug, brands_dir)
        
        # Get parent status from config seed parent MSTs
        parent_msts = config.seed_parent_msts or []
        parent_status = None
        for pmst in parent_msts:
            if pmst in gdt_cache:
                status = gdt_cache[pmst].get('status')
                if status == 'NNT đang hoạt động':
                    parent_status = status
                    break
        if not parent_status and parent_msts:
            # Fallback to the first parent status in cache if none are active
            for pmst in parent_msts:
                if pmst in gdt_cache:
                    parent_status = gdt_cache[pmst].get('status')
                    break
        
        active = 0
        for r in stores:
            gdt = str(r.get('Enterprise_Gdt_Code') or '')
            code = str(r.get('Enterprise_Code') or '')
            mst = _extract_mst(r) or ''

            if gdt and gdt in gdt_cache:
                r['Status'] = gdt_cache[gdt].get('status')
            elif code and code in gdt_cache:
                r['Status'] = gdt_cache[code].get('status')
            elif mst and mst in gdt_cache and not mst.startswith('00'):
                r['Status'] = gdt_cache[mst].get('status')
            elif not opt_in and (not mst or mst.startswith('00') or len(mst) < 10) and parent_status:
                r['Status'] = parent_status
            else:
                r['Status'] = None
                
            if r.get('Status') == 'NNT đang hoạt động':
                active += 1
                
        print(f"[Stage 2] Mapped entity status from GDT cache file ({active} active, "
              f"{len(stores) - active} ceased/inactive/unchecked)")

    # ── Stage 2.1: Format A branch status resolution (opt-in brands) ──
    # Format A stores (5-digit 00XXX GDT code) have no individual GDT tax code.
    # Map them to their parent regional branch via "TẠI [CITY]" in the Name field,
    # then inherit that branch's status from the VietQR branch cache.
    if opt_in:
        slug_us = slug.replace('-', '_')
        vietqr_path = output_dir(slug, brands_dir) / f'vietqr_{slug_us}_branches.json'
        branch_statuses: dict = {}
        if vietqr_path.exists():
            with open(vietqr_path, encoding='utf-8') as f:
                branch_statuses = json.load(f)
        # Merge gdt_cache so parent MSTs are available for the no-city fallback
        for k, v in gdt_cache.items():
            if k not in branch_statuses:
                branch_statuses[k] = v
        n_a = resolve_format_a_branch_statuses(
            stores, branch_statuses, config.seed_parent_msts or []
        )
        print(f"[Stage 2.1] Format A branch resolution: {n_a} stores resolved")

    # ── Stage 2.5: Name enrichment from MST ──
    n_enriched = enrich_store_names(stores, config)
    if n_enriched > 0:
        print(f"[Stage 2.5] Enriched {n_enriched} vague store names from masothue.com")
    else:
        print(f"[Stage 2.5] Skipped (no name_enrichment config or no vague names)")

    # ── Stage 2.7: DPI Open-Data Registry Verification (Zero-Fee Offline Lookup) ──
    if dpi_status_file:
        refine_statuses_from_dpi(stores, dpi_status_file, config)

    # ── Stage 3: Date interpolation ──
    if not skip_date_calibration:
        print(f"[Stage 3] Building date interpolation model...")
        # Global cross-brand Id→date curve: the DKKD Id is a national registry
        # clock, so this beats the degenerate per-brand 2-point fallback for any
        # brand without its own masothue/manual calibration (date-inference P6).
        global_fallback = build_global_id_date_model(brands_dir)
        model = build_calibration_model(config, stores,
                                        masothue_statuses=masothue_statuses or None,
                                        global_fallback=global_fallback)
        min_date = cls_rules.get('date_calibration_min_date', '2010-01-01')
        apply_date_interpolation(stores, model, min_date,
                                 masothue_statuses=masothue_statuses or None,
                                 enterprise_details=enterprise_details or None)
        print(f"[Stage 3] Applied date interpolation to all records")
    else:
        print(f"[Stage 3] Skipped (--skip-date-calibration)")

    # ── Stage 4: Geo enrichment ──
    _enrich_geo(stores)
    print(f"[Stage 4] Geographic enrichment complete")

    # ── Stage 5: Classification ──
    # Pass 1: Run format classification (skip deduplication for now)
    classify_all(stores, config)
    print(f"[Stage 5] Classified formats for all stores")

    # Dedup/cap pass (non-opt-in only) and resolver call
    if opt_in:
        pins = load_locator_pins(slug, brands_dir)
        structural_signals_enabled = bool(
            cls_rules.get('operating_status', {}).get('structural_signals_enabled')
        )
        closure_signals = (
            build_closure_signal_map(stores, seed_parent_msts=set(config.seed_parent_msts))
            if structural_signals_enabled else None
        )
        resolve_operating_status(stores, config, locator_pins=pins, gdt_cache=gdt_cache,
                                  closure_signals=closure_signals)
    else:
        if config.slug == 'winmart':
            from dkkd.classify import resolve_supermarket_operating_status
            rules = config.classification
            final_cap = cap if cap is not None else rules.get('active_supermarket_cap', 130)
            resolve_supermarket_operating_status(stores, final_cap)
        else:
            from dkkd.classify import resolve_operating_cap, resolve_address_deduplication
            if cap is not None:
                resolve_operating_cap(stores, cap)
            else:
                resolve_address_deduplication(stores, config.name)
        resolve_operating_status(stores, config)

    # ── Stage 5.5: Tenant role tagging (own_store / in_brand_tenant / unrelated) ──
    from dkkd.tenant import tag_roles
    tag_roles(stores, config)
    ts_enabled = bool(cls_rules.get('tenant_separation', {}).get('enabled'))
    if ts_enabled:
        role_counts = {}
        for r in stores:
            role_counts[r['store_role']] = role_counts.get(r['store_role'], 0) + 1
        print(f"[Stage 5.5] Tenant roles: {role_counts}")

    # ── Stage 6: Export ──
    _save_checkpoint(stores, slug, brands_dir)

    out = output_dir(slug, brands_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Derive field order once from the full stores list (used for fallback headers)
    all_fields = _ordered_fieldnames(stores)

    # Full dataset
    full_path = out / f'{slug}.csv'
    _export_csv(stores, full_path)

    # Counts for the summary (Core_Operating_Store/Operating_Status stay as
    # internal fields on the full CSV/checkpoint — backtest.py and audit.py
    # read them from there, not from a dedicated split file).
    core_stores = [r for r in stores if r.get('Core_Operating_Store') == 'Yes']
    non_core = [r for r in stores if r.get('Operating_Status') == 'Closed']

    # Unverified (opt-in brands only; empty for non-opt-in) — kept as its own
    # file because backtest.py reads it directly for the report narrative.
    unverified = [r for r in stores if r.get('Operating_Status') == 'Unverified']
    unverified_path = out / f'{slug}_unverified.csv'
    _export_csv(unverified, unverified_path, fallback_fields=all_fields)

    # Standard-schema export: the one analyst-facing deliverable, replacing
    # the old per-status split CSVs with store_brand_name_confidence /
    # duplication_status quality signals instead of a binary file split.
    schema_path = write_standard_schema(config, stores, out, slug)

    # Host-effectiveness rollup (opt-in supermarket/mall brands only)
    if ts_enabled:
        from dkkd.tenant import write_host_effectiveness
        he_path = out / f'{slug}_host_effectiveness.csv'
        write_host_effectiveness(stores, he_path)
        print(f"  Host effectiveness: {he_path}")

    # Build summary
    df = pd.DataFrame(stores)
    format_counts = {}
    if 'Store_Type_MSN' in df.columns:
        format_counts = df['Store_Type_MSN'].value_counts().to_dict()

    n_operating = len(core_stores)
    n_closed = len(non_core)
    n_unverified = len(unverified)

    summary = {
        'total_records': len(stores),
        'unverified': n_unverified,
        'core_operating': n_operating,
        'non_operating': n_closed,
        'format_counts': format_counts,
        'output_files': {
            'full': str(full_path),
            'unverified': str(unverified_path),
            'standard_schema': str(schema_path),
        },
        'generated_at': datetime.now().isoformat(),
    }

    print(f"\n{'='*60}")
    print(f"[Stage 6] Export complete")
    print(f"  Full dataset:      {full_path} ({len(stores)} records)")
    print(f"  Unverified:        {unverified_path} ({n_unverified} records)")
    print(f"  Standard schema:   {schema_path}")
    print(f"\n  3-state: {n_operating} Operating + {n_closed} Closed + {n_unverified} Unverified = {n_operating + n_closed + n_unverified} total")
    if n_operating + n_closed + n_unverified != len(stores):
        print(f"  WARNING: 3-state sum ({n_operating + n_closed + n_unverified}) != total ({len(stores)})")
    print(f"\nFormat distribution:")
    for fmt, count in format_counts.items():
        print(f"  {fmt}: {count}")
    print(f"{'='*60}")

    return summary
