"""Tests for the dashboard ETL pipeline: conform.py extractors + etl.py's
staging Parquet / serving DuckDB build.
"""
import csv
import json
from datetime import date

import duckdb

from dkkd import conform, etl

_DKKD_FIELDNAMES = [
    'Id', 'Name', 'Name_F', 'Enterprise_Code', 'Enterprise_Gdt_Code', 'Status',
    'Store_Brand_Format', 'Store_Type_MSN', 'Core_Operating_Store',
    'Operating_Status', 'Operating_Evidence',
    'City_Id', 'City_Name', 'District_Id', 'District_Name', 'Ward_Id', 'Ward_Name',
    'Ho_Address', 'Ho_Address_F', 'Legal_First_Name',
    'Establishment_Date', 'Establishment_Year', 'Date_Confidence',
]


def _write_dkkd_brand_csv(brands_dir, category, subcategory, slug, rows):
    out_dir = brands_dir / category / subcategory / slug / 'output'
    out_dir.mkdir(parents=True)
    with open(out_dir / f'{slug}.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=_DKKD_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_website_brand(website_dir, slug, records):
    brand_dir = website_dir / slug
    brand_dir.mkdir(parents=True)
    (brand_dir / 'config.yaml').write_text(
        f"brand: {slug}\narchetype: json_national\nendpoint: x\nfield_map:\n  store_key: id\n",
        encoding='utf-8',
    )
    snap_dir = brand_dir / 'snapshots' / '2026-07-04'
    snap_dir.mkdir(parents=True)
    (snap_dir / 'normalized.json').write_text(json.dumps(records), encoding='utf-8')


def _add_website_snapshot(website_dir, slug, as_of, records):
    """Add an extra dated snapshot to a brand already created by
    _write_website_brand (which seeds the '2026-07-04' snapshot)."""
    snap_dir = website_dir / slug / 'snapshots' / as_of
    snap_dir.mkdir(parents=True)
    (snap_dir / 'normalized.json').write_text(json.dumps(records), encoding='utf-8')


def test_canonicalize_province_matches_known_name():
    assert conform.canonicalize_province('Hồ Chí Minh') == 'HỒ CHÍ MINH'


def test_canonicalize_province_opaque_object_id_returns_none():
    # Real gotcha from family-mart's own data: `province` is a raw Mongo
    # ObjectId there, not a resolvable place name.
    assert conform.canonicalize_province('690b79fbcc8c6b334889f5cf') is None


def test_canonicalize_province_empty_returns_none():
    assert conform.canonicalize_province('') is None
    assert conform.canonicalize_province(None) is None


def test_region_for_province_known_provinces():
    assert conform.region_for_province('HỒ CHÍ MINH') == 'Đông Nam Bộ'
    assert conform.region_for_province('HÀ NỘI') == 'Đồng Bằng Sông Hồng'
    assert conform.region_for_province(None) is None


def test_conformed_store_columns_includes_region():
    assert 'region' in conform.CONFORMED_STORE_COLUMNS


def test_snapshot_columns_is_subset_of_conformed_store_columns():
    # Guards schema drift: fact_store_snapshot's frozen historical parquet
    # files project SNAPSHOT_COLUMNS from the same row dicts as
    # CONFORMED_STORE_COLUMNS. If SNAPSHOT_COLUMNS ever names a column not
    # in CONFORMED_STORE_COLUMNS, the projection is broken.
    assert set(conform.SNAPSHOT_COLUMNS) <= set(conform.CONFORMED_STORE_COLUMNS)


def test_extract_dkkd_stores_carries_core_operating_and_base_mst(tmp_path):
    brands_dir = tmp_path / 'brands'
    _write_dkkd_brand_csv(brands_dir, 'F&B', 'mini_supermarket', 'winmart', [{
        'Id': '77', 'Name': 'CN CONG TY WINMART - HN', 'Name_F': 'CN CONG TY WINMART - HN',
        'Enterprise_Code': '0104918404', 'Enterprise_Gdt_Code': '0104918404-005', 'Status': '',
        'Store_Brand_Format': 'WinMart', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Ha Noi', 'District_Id': '1', 'District_Name': 'Q1',
        'Ward_Id': '1', 'Ward_Name': 'P1', 'Ho_Address': 'x', 'Ho_Address_F': 'x',
        'Legal_First_Name': 'A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }])
    rows = conform.extract_dkkd_stores(brands_dir=brands_dir, as_of='2026-07-08')
    assert rows[0]['core_operating_store'] == 'Yes'
    assert rows[0]['base_mst'] == '0104918404'
    assert rows[0]['region'] == 'Đồng Bằng Sông Hồng'
    assert 'core_operating_store' in conform.CONFORMED_STORE_COLUMNS
    assert 'base_mst' in conform.CONFORMED_STORE_COLUMNS


def test_extract_website_stores_region_is_none(tmp_path):
    website_dir = tmp_path / 'website_brands'
    _write_website_brand(website_dir, 'family-mart', [{
        'store_key': 'abc123', 'name': 'FamilyMart - Test', 'address': '1 Test St',
        'lat': 10.5, 'lng': 106.6, 'province': 'Hồ Chí Minh',
        'opening_date': '2025-02-24T11:54:51.647Z',
    }])
    rows = conform.extract_website_stores(website_brands_dir=website_dir)
    assert rows[0]['region'] is None


def test_extract_website_snapshot_history_walks_every_date(tmp_path):
    """Regression test for the bug this task fixes: extract_website_stores
    only reads the LATEST snapshot dir, so history sitting in earlier dated
    dirs was never read. extract_website_snapshot_history must return rows
    for every date, for every brand (one date, or several)."""
    website_dir = tmp_path / 'website_brands'
    # Brand with 2 snapshot dates (mirrors aeon/saigon-coop on the real repo).
    _write_website_brand(website_dir, 'aeon', [{
        'store_key': 'a1', 'name': 'AEON store (day 1)', 'address': 'addr 1',
        'lat': 10.0, 'lng': 106.0, 'province': 'Hồ Chí Minh',
    }])
    _add_website_snapshot(website_dir, 'aeon', '2026-07-07', [{
        'store_key': 'a1', 'name': 'AEON store (day 2)', 'address': 'addr 1',
        'lat': 10.0, 'lng': 106.0, 'province': 'Hồ Chí Minh',
    }, {
        'store_key': 'a2', 'name': 'AEON store 2 (new)', 'address': 'addr 2',
        'lat': 10.1, 'lng': 106.1, 'province': 'Hồ Chí Minh',
    }])
    # Brand with just 1 snapshot date (the common case).
    _write_website_brand(website_dir, 'family-mart', [{
        'store_key': 'fm1', 'name': 'FamilyMart - Test', 'address': '1 Test St',
        'lat': 10.5, 'lng': 106.6, 'province': 'Hồ Chí Minh',
    }])

    rows = conform.extract_website_snapshot_history(website_brands_dir=website_dir)
    as_of_by_brand = {}
    for r in rows:
        as_of_by_brand.setdefault(r['brand_slug'], set()).add(r['as_of'])

    assert as_of_by_brand['aeon'] == {'2026-07-04', '2026-07-07'}
    assert as_of_by_brand['family-mart'] == {'2026-07-04'}

    # Same conformed shape extract_website_stores already emits, per date,
    # including the retail_taxonomy columns (all None for website rows).
    day2_rows = [r for r in rows if r['brand_slug'] == 'aeon' and r['as_of'] == '2026-07-07']
    assert {r['source_native_id'] for r in day2_rows} == {'a1', 'a2'}
    assert all(r['source'] == 'website' for r in day2_rows)
    assert all(r['store_uid'] == f"website:aeon:{r['source_native_id']}" for r in day2_rows)
    assert all(r['gics_sector'] is None and r['retail_format'] is None for r in day2_rows)


def test_build_staging_and_serving_db(tmp_path):
    brands_dir = tmp_path / 'brands'
    _write_dkkd_brand_csv(brands_dir, 'F&B', 'convenience_stores', 'coop-food', [{
        'Id': '1001', 'Name': 'CUA HANG COOP FOOD 1', 'Name_F': 'CUA HANG COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00001', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '1 Nguyen Hue', 'Ho_Address_F': '1 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }, {
        'Id': '1002', 'Name': 'CHI NHANH - KHO COOP FOOD 1', 'Name_F': 'CHI NHANH - KHO COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00002', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'No', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '2 Nguyen Hue', 'Ho_Address_F': '2 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }])

    website_dir = tmp_path / 'website_brands'
    _write_website_brand(website_dir, 'family-mart', [{
        'store_key': 'abc123', 'name': 'FamilyMart - Test', 'address': '1 Test St',
        'lat': 10.5, 'lng': 106.6, 'province': '690b79fbcc8c6b334889f5cf',
        'opening_date': '2025-02-24T11:54:51.647Z',
    }])

    staging_dir = tmp_path / 'staging'
    counts = etl.build_staging(
        staging_dir=staging_dir, brands_dir=brands_dir, website_brands_dir=website_dir,
    )
    # 2 distinct as_of values this run: today's (dkkd) + '2026-07-04' (the
    # website snapshot's own date, from the fixture's 1 snapshot dir).
    assert counts == {'dkkd': 2, 'website': 1, 'benchmarks': 0, 'snapshots': 2}
    assert (staging_dir / 'stores_dkkd.parquet').exists()
    assert (staging_dir / 'stores_website.parquet').exists()
    assert (staging_dir / 'benchmarks_ir.parquet').exists()
    assert (staging_dir / 'snapshots' / 'as_of=2026-07-04.parquet').exists()
    today = date.today().isoformat()
    assert (staging_dir / 'snapshots' / f'as_of={today}.parquet').exists()

    db_path = tmp_path / 'serving' / 'dashboard.duckdb'
    total = etl.build_serving_db(
        db_path=db_path, staging_dir=staging_dir, brands_dir=brands_dir,
        brand_master_path=tmp_path / 'no_overlay.yaml',
    )
    assert total == 3

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        sources = {r[0] for r in con.execute('SELECT DISTINCT source FROM stores').fetchall()}
        assert sources == {'dkkd', 'website'}

        dkkd_row = con.execute(
            "SELECT store_uid, province, lat, store_role FROM stores WHERE store_uid = 'dkkd:1001'"
        ).fetchone()
        assert dkkd_row == ('dkkd:1001', 'HỒ CHÍ MINH', None, 'Retail')

        warehouse_row = con.execute(
            "SELECT store_uid, store_role FROM stores WHERE store_uid = 'dkkd:1002'"
        ).fetchone()
        assert warehouse_row == ('dkkd:1002', 'Warehouse')

        website_row = con.execute(
            "SELECT store_uid, province, lat, store_role FROM stores WHERE source = 'website'"
        ).fetchone()
        assert website_row == ('website:family-mart:abc123', None, 10.5, None)

        geo_rows = con.execute('SELECT * FROM mart_geo').fetchall()
        assert len(geo_rows) >= 1

        dd_count = con.execute('SELECT count(*) FROM data_dictionary').fetchone()[0]
        assert dd_count == len(con.execute('DESCRIBE stores').fetchall())

        snapshot_as_ofs = {r[0] for r in con.execute('SELECT DISTINCT as_of FROM fact_store_snapshot').fetchall()}
        assert snapshot_as_ofs == {today, '2026-07-04'}

        series_rows = {
            (r[0], r[1], r[2]): (r[3], r[4])
            for r in con.execute(
                'SELECT as_of, source, brand_slug, total, operating_count FROM mart_store_series'
            ).fetchall()
        }
        assert series_rows[(today, 'dkkd', 'coop-food')] == (2, 2)
        assert series_rows[('2026-07-04', 'website', 'family-mart')] == (1, 1)
    finally:
        con.close()


def test_build_staging_snapshot_backfill_is_idempotent(tmp_path):
    """A historical (non-today) snapshot file already on disk must survive a
    re-run byte-for-byte; today's file must always be rewritten. This is the
    'self-healing backfill, never clobber a settled historical date' behavior
    from the design doc."""
    brands_dir = tmp_path / 'brands'
    _write_dkkd_brand_csv(brands_dir, 'F&B', 'convenience_stores', 'coop-food', [{
        'Id': '3001', 'Name': 'CUA HANG COOP FOOD 1', 'Name_F': 'CUA HANG COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00001', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '1 Nguyen Hue', 'Ho_Address_F': '1 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }])

    website_dir = tmp_path / 'website_brands'
    _write_website_brand(website_dir, 'aeon', [{
        'store_key': 'a1', 'name': 'AEON store', 'address': 'addr 1',
        'lat': 10.0, 'lng': 106.0, 'province': 'Hồ Chí Minh',
    }])
    _add_website_snapshot(website_dir, 'aeon', '2026-07-07', [{
        'store_key': 'a1', 'name': 'AEON store', 'address': 'addr 1',
        'lat': 10.0, 'lng': 106.0, 'province': 'Hồ Chí Minh',
    }, {
        'store_key': 'a2', 'name': 'AEON store 2', 'address': 'addr 2',
        'lat': 10.1, 'lng': 106.1, 'province': 'Hồ Chí Minh',
    }])

    staging_dir = tmp_path / 'staging'
    counts_1 = etl.build_staging(staging_dir=staging_dir, brands_dir=brands_dir, website_brands_dir=website_dir)
    # 3 distinct as_of: today's (dkkd), 2026-07-04, 2026-07-07 (both from aeon's history).
    assert counts_1['snapshots'] == 3

    day7_path = staging_dir / 'snapshots' / 'as_of=2026-07-07.parquet'
    day4_path = staging_dir / 'snapshots' / 'as_of=2026-07-04.parquet'
    assert day7_path.exists() and day4_path.exists()
    day7_before = day7_path.read_bytes()
    day4_before = day4_path.read_bytes()

    # Re-run: historical files must be byte-identical (untouched); today's
    # file always gets rewritten so it's not part of the "settled" set.
    counts_2 = etl.build_staging(staging_dir=staging_dir, brands_dir=brands_dir, website_brands_dir=website_dir)
    assert counts_2['snapshots'] == 1  # only today's file gets rewritten this time
    assert day7_path.read_bytes() == day7_before
    assert day4_path.read_bytes() == day4_before

    con = duckdb.connect()
    try:
        n_rows_day7 = con.execute(
            f"SELECT count(*) FROM read_parquet('{day7_path.as_posix()}')"
        ).fetchone()[0]
        assert n_rows_day7 == 2  # a1 + a2, not duplicated by the re-run
    finally:
        con.close()


def test_serving_db_has_brand_master_and_ecosystem(tmp_path):
    brands_dir = tmp_path / 'brands'
    _write_dkkd_brand_csv(brands_dir, 'F&B', 'convenience_stores', 'coop-food', [{
        'Id': '2001', 'Name': 'CUA HANG COOP FOOD 1', 'Name_F': 'CUA HANG COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00001', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '1 Nguyen Hue', 'Ho_Address_F': '1 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }, {
        'Id': '2002', 'Name': 'CUA HANG COOP FOOD 2', 'Name_F': 'CUA HANG COOP FOOD 2',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00003', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '2 Nguyen Hue', 'Ho_Address_F': '2 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }, {
        'Id': '2003', 'Name': 'CHI NHANH - KHO COOP FOOD 1', 'Name_F': 'CHI NHANH - KHO COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00002', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'No', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '3 Nguyen Hue', 'Ho_Address_F': '3 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }])
    (brands_dir / 'F&B' / 'convenience_stores' / 'coop-food' / 'config.yaml').write_text(
        'slug: coop-food\nname: Co.op Food\nbrand_regex: Co.op Food\n', encoding='utf-8')

    staging_dir = tmp_path / 'staging'
    etl.build_staging(
        staging_dir=staging_dir, brands_dir=brands_dir,
        website_brands_dir=tmp_path / 'website_brands_missing',
    )
    db_path = tmp_path / 'serving' / 'dashboard.duckdb'
    etl.build_serving_db(
        db_path=db_path, staging_dir=staging_dir, brands_dir=brands_dir,
        brand_master_path=tmp_path / 'no_overlay.yaml',
    )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        eco = con.execute(
            "SELECT n_licenses, n_operating_stores, n_warehouses "
            "FROM mart_brand_ecosystem WHERE brand_slug='coop-food'"
        ).fetchone()
        assert eco == (3, 2, 1)
        assert con.execute(
            "SELECT count(*) FROM dim_brand_master WHERE brand_slug='coop-food'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM v_brand_search WHERE brand_slug='coop-food'"
        ).fetchone()[0] == 1
        ent = con.execute(
            "SELECT count(*) FROM v_brand_entities WHERE brand_slug='coop-food'"
        ).fetchone()[0]
        assert ent >= 1

        # dim_brand_master is typed now, not all-VARCHAR.
        col_types = {r[0]: r[1] for r in con.execute("DESCRIBE dim_brand_master").fetchall()}
        assert col_types['nbo_is_local'] == 'BOOLEAN'

        # dim_company/bridge_brand_entity: coop-food's 3 licenses all resolve
        # to base_mst='0300000001' (5-digit GDT codes fall through to the
        # 10-digit Enterprise_Code, see tenant.base_mst), observed-only (no
        # curated owner_msts in this test's empty overlay).
        bridge = con.execute(
            "SELECT brand_slug, mst, role, n_locations FROM bridge_brand_entity "
            "WHERE brand_slug='coop-food'"
        ).fetchall()
        assert bridge == [('coop-food', '0300000001', 'operator_observed', 3)]
        company = con.execute(
            "SELECT is_curated_owner, is_observed FROM dim_company WHERE mst='0300000001'"
        ).fetchone()
        assert company == (False, True)
    finally:
        con.close()


def test_curated_owner_unifies_with_observed_entity(tmp_path):
    """A curated owner_msts entry for an mst that ALSO appears as an observed
    operator in stores should collapse to one v_brand_entities row with
    role='owner_operator' — the curated name wins for dim_company.company_name."""
    brands_dir = tmp_path / 'brands'
    _write_dkkd_brand_csv(brands_dir, 'F&B', 'convenience_stores', 'coop-food', [{
        'Id': '3001', 'Name': 'CUA HANG COOP FOOD 1', 'Name_F': 'CUA HANG COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00001', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '1 Nguyen Hue', 'Ho_Address_F': '1 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }])
    (brands_dir / 'F&B' / 'convenience_stores' / 'coop-food' / 'config.yaml').write_text(
        'slug: coop-food\nname: Co.op Food\nbrand_regex: Co.op Food\n', encoding='utf-8')

    overlay = tmp_path / 'brand_master.yaml'
    overlay.write_text(
        "- slug: coop-food\n  owner_msts:\n    '0300000001': Saigon Co.op\n",
        encoding='utf-8',
    )

    staging_dir = tmp_path / 'staging'
    etl.build_staging(staging_dir=staging_dir, brands_dir=brands_dir,
                      website_brands_dir=tmp_path / 'website_brands_missing')
    db_path = tmp_path / 'serving' / 'dashboard.duckdb'
    etl.build_serving_db(
        db_path=db_path, staging_dir=staging_dir, brands_dir=brands_dir,
        brand_master_path=overlay,
    )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        company = con.execute(
            "SELECT company_name, is_curated_owner, is_observed FROM dim_company WHERE mst='0300000001'"
        ).fetchone()
        assert company == ('Saigon Co.op', True, True)

        ent = con.execute(
            "SELECT sample_name, role, n_locations FROM v_brand_entities "
            "WHERE brand_slug='coop-food' AND mst='0300000001'"
        ).fetchone()
        assert ent == ('Saigon Co.op', 'owner_operator', 1)
    finally:
        con.close()


def test_scorecard_has_store_and_province_metrics(tmp_path):
    """mart_brand_scorecard must exist and carry store/province/YTD metrics."""
    brands_dir = tmp_path / 'brands'
    _write_dkkd_brand_csv(brands_dir, 'F&B', 'convenience_stores', 'coop-food', [{
        'Id': '6001', 'Name': 'CUA HANG COOP FOOD 1', 'Name_F': 'CUA HANG COOP FOOD 1',
        'Enterprise_Code': '0300000001', 'Enterprise_Gdt_Code': '00001', 'Status': '',
        'Store_Brand_Format': 'Co.op Food', 'Store_Type_MSN': 'Retail',
        'Core_Operating_Store': 'Yes', 'Operating_Status': 'Operating', 'Operating_Evidence': 'legacy-classify',
        'City_Id': '1', 'City_Name': 'Hồ Chí Minh', 'District_Id': '1', 'District_Name': 'Quan 1',
        'Ward_Id': '1', 'Ward_Name': 'Ben Nghe', 'Ho_Address': '1 Nguyen Hue', 'Ho_Address_F': '1 Nguyen Hue',
        'Legal_First_Name': 'Nguyen Van A',
        'Establishment_Date': '2020-01-01', 'Establishment_Year': '2020', 'Date_Confidence': 'high',
    }])
    (brands_dir / 'F&B' / 'convenience_stores' / 'coop-food' / 'config.yaml').write_text(
        'slug: coop-food\nname: Co.op Food\nbrand_regex: Co.op Food\n', encoding='utf-8')

    staging_dir = tmp_path / 'staging'
    etl.build_staging(staging_dir=staging_dir, brands_dir=brands_dir,
                      website_brands_dir=tmp_path / 'website_brands_missing')
    db_path = tmp_path / 'serving' / 'dashboard.duckdb'
    etl.build_serving_db(
        db_path=db_path, staging_dir=staging_dir, brands_dir=brands_dir,
        brand_master_path=tmp_path / 'no_overlay.yaml',
    )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute("""
            SELECT brand_slug, n_operating_stores, top_provinces
            FROM mart_brand_scorecard WHERE brand_slug='coop-food'
        """).fetchone()
        assert row is not None
        assert row[0] == 'coop-food'
        assert row[1] == 1
        assert row[2] == [{'province': 'HỒ CHÍ MINH', 'count': 1}]
    finally:
        con.close()

