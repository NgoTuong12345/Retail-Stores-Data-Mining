"""Stage + load the dashboard's data pipeline: conformed rows (dkkd/conform.py)
-> Parquet staging ("silver") -> read-only DuckDB serving DB ("gold").

  build_staging()     conform.py extractors -> data/staging/*.parquet
  build_serving_db()  staging Parquet -> data/serving/dashboard.duckdb (atomic replace)
  run_pipeline()       both, in order

Rebuilds are wholesale each run — incremental upsert is not worth the
complexity at this data's scale (~32K rows).

build_serving_db() also optionally ingests NSO population/labour, World Bank
Indicators, MOIT industrial-production/trade, and NSO market-count source
DBs, if present under data/external/. Missing optional source DBs are
skipped cleanly; their domain routes return 503 until the corresponding
source is built.
"""
import os
from datetime import date
from pathlib import Path

from dkkd import conform, contract
from dkkd.paths import PACKAGE_ROOT

# Optional external source DBs — absent in this extraction-only repo, so every
# _ingest_* below skips cleanly and the serving DB stays DKKD-only.
_EXTERNAL_DIR = PACKAGE_ROOT / 'data' / 'external'

DEFAULT_STAGING_DIR = PACKAGE_ROOT / 'data' / 'staging'
DEFAULT_SERVING_DB_PATH = PACKAGE_ROOT / 'data' / 'serving' / 'dashboard.duckdb'
DEFAULT_NSO_MACRO_DB_PATH = _EXTERNAL_DIR / 'nso_population_labor.duckdb'
DEFAULT_WORLDBANK_DB_PATH = _EXTERNAL_DIR / 'worldbank.duckdb'
DEFAULT_MOIT_MACRO_DB_PATH = _EXTERNAL_DIR / 'moit_industry_trade.duckdb'
DEFAULT_NSO_MARKET_DB_PATH = _EXTERNAL_DIR / 'nso_market.duckdb'


def _write_parquet(con, rows: list[dict], columns: list[str], double_cols: set, path: Path) -> int:
    ddl = ', '.join(f"{c} {'DOUBLE' if c in double_cols else 'TEXT'}" for c in columns)
    con.execute(f"CREATE OR REPLACE TABLE _stage ({ddl})")
    if rows:
        col_list = ', '.join(columns)
        placeholders = ', '.join('?' for _ in columns)
        con.executemany(
            f"INSERT INTO _stage ({col_list}) VALUES ({placeholders})",
            [[row.get(c) for c in columns] for row in rows],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY _stage TO '{path.as_posix()}' (FORMAT PARQUET)")
    con.execute("DROP TABLE _stage")
    return len(rows)


def _write_snapshot_parquets(con, dkkd_rows: list[dict], website_history_rows: list[dict],
                              today: str, snapshots_dir: Path) -> int:
    """One Parquet per distinct `as_of` found across today's dkkd rows and
    every historical website snapshot date. Idempotent: a historical
    (non-today) as_of file already on disk is left byte-untouched — the
    website snapshot it was built from is a settled point-in-time capture
    that never changes retroactively. Today's file is always rewritten so a
    same-day re-run reflects the latest scrape state.

    Returns the number of files actually (re)written this call.
    """
    by_as_of: dict[str, list[dict]] = {}
    for r in dkkd_rows:
        by_as_of.setdefault(r.get('as_of'), []).append(r)
    for r in website_history_rows:
        by_as_of.setdefault(r.get('as_of'), []).append(r)

    n_written = 0
    for as_of, rows in by_as_of.items():
        if not as_of:
            continue
        path = snapshots_dir / f'as_of={as_of}.parquet'
        if path.exists() and as_of != today:
            continue
        _write_parquet(con, rows, conform.SNAPSHOT_COLUMNS, set(), path)
        n_written += 1
    return n_written


def build_staging(
    staging_dir: Path | None = None,
    brands_dir: Path | None = None,
    website_brands_dir: Path | None = None,
    ir_csv: Path | None = None,
    verbose: bool = True,
) -> dict:
    """Run the per-source extractors and write one conformed Parquet file each,
    plus one snapshot Parquet per distinct as_of (see _write_snapshot_parquets)."""
    import duckdb

    staging_dir = Path(staging_dir or DEFAULT_STAGING_DIR)
    as_of = date.today().isoformat()

    dkkd_rows = conform.extract_dkkd_stores(brands_dir, as_of=as_of)
    website_rows = conform.extract_website_stores(website_brands_dir)
    website_history_rows = conform.extract_website_snapshot_history(website_brands_dir)
    ir_rows = conform.extract_ir_benchmarks(ir_csv)

    con = duckdb.connect()
    try:
        n_dkkd = _write_parquet(
            con, dkkd_rows, conform.CONFORMED_STORE_COLUMNS, conform.DOUBLE_STORE_COLUMNS,
            staging_dir / 'stores_dkkd.parquet',
        )
        n_website = _write_parquet(
            con, website_rows, conform.CONFORMED_STORE_COLUMNS, conform.DOUBLE_STORE_COLUMNS,
            staging_dir / 'stores_website.parquet',
        )
        n_ir = _write_parquet(
            con, ir_rows, conform.BENCHMARK_COLUMNS, set(),
            staging_dir / 'benchmarks_ir.parquet',
        )
        n_snapshots = _write_snapshot_parquets(
            con, dkkd_rows, website_history_rows, as_of, staging_dir / 'snapshots',
        )
    finally:
        con.close()

    if verbose:
        print(f"  Staging -> {staging_dir}")
        print(f"    dkkd stores:      {n_dkkd}")
        print(f"    website stores:   {n_website}")
        print(f"    ir benchmarks:    {n_ir}")
        print(f"    snapshot files:   {n_snapshots}")

    return {'dkkd': n_dkkd, 'website': n_website, 'benchmarks': n_ir, 'snapshots': n_snapshots}


def _create_marts(con) -> None:
    con.execute("""
        CREATE VIEW mart_brand_summary AS
        SELECT brand_slug, source, count(*) AS total,
               sum(CASE WHEN operating_status = 'Operating' THEN 1 ELSE 0 END) AS operating_count
        FROM stores GROUP BY brand_slug, source
    """)
    con.execute("""
        CREATE VIEW mart_geo AS
        SELECT coalesce(nullif(trim(province), ''), 'Unknown') AS province, source,
               count(*) AS count,
               sum(CASE WHEN operating_status = 'Operating' THEN 1 ELSE 0 END) AS operating_count
        FROM stores GROUP BY 1, 2
    """)
    con.execute("""
        CREATE VIEW mart_trend AS
        SELECT substr(opening_date, 1, 4) AS year, source, count(*) AS count
        FROM stores
        WHERE opening_date IS NOT NULL AND length(opening_date) >= 4
        GROUP BY 1, 2
    """)
    con.execute("""
        CREATE VIEW mart_map_points AS
        SELECT * FROM stores WHERE lat IS NOT NULL AND lng IS NOT NULL
    """)
    # Trend axis over fact_store_snapshot (append-only time series), not
    # `stores` (current-state only). Looser `operating_status = 'Operating'`
    # predicate, not contract.OPERATING_PREDICATE — core_operating_store is
    # null for website rows and this mart spans both sources.
    con.execute("""
        CREATE VIEW mart_store_series AS
        SELECT as_of, source, brand_slug, count(*) AS total,
               sum(CASE WHEN operating_status = 'Operating' THEN 1 ELSE 0 END) AS operating_count
        FROM fact_store_snapshot GROUP BY 1, 2, 3
    """)


def _create_data_dictionary(con) -> None:
    con.execute("""
        CREATE TABLE data_dictionary (
            column_name TEXT PRIMARY KEY,
            data_source TEXT,
            description TEXT
        )
    """)
    con.executemany(
        'INSERT INTO data_dictionary (column_name, data_source, description) VALUES (?, ?, ?)',
        contract.DATA_DICTIONARY,
    )


# dim_brand_master column types — only the columns that differ from VARCHAR
# (etl.py used to stringify every column; brand_master.assemble_master_rows
# already emits native bool for this one, so the table can just carry it typed).
MASTER_COLUMN_TYPES = {
    'nbo_is_local': 'BOOLEAN',
}


def _create_company_dim(con, brand_master_module, brand_master_path=None) -> None:
    """dim_company (VN-MST grain) + bridge_brand_entity (brand x mst x role):
    unifies curated owners (brand_master.yaml's owner_msts) with observed
    operators (stores.base_mst) — the two "legal entity behind a brand"
    representations that used to live in an owner_msts_json blob and a
    separate v_brand_entities GROUP BY, with no join between them.
    """
    con.execute("""
        CREATE TABLE bridge_brand_entity (
            brand_slug VARCHAR, mst VARCHAR, role VARCHAR, n_locations INTEGER
        )
    """)
    con.execute("""
        INSERT INTO bridge_brand_entity
        SELECT brand_slug, base_mst, 'operator_observed', count(*)
        FROM stores WHERE source = 'dkkd' AND base_mst <> ''
        GROUP BY brand_slug, base_mst
    """)

    curated_companies, curated_bridge = brand_master_module.assemble_curated_entities(brand_master_path)
    if curated_bridge:
        con.executemany("INSERT INTO bridge_brand_entity VALUES (?, ?, ?, ?)", curated_bridge)

    con.execute("CREATE TABLE _curated_company (mst VARCHAR, company_name VARCHAR)")
    if curated_companies:
        con.executemany("INSERT INTO _curated_company VALUES (?, ?)", curated_companies)

    con.execute("""
        CREATE TABLE dim_company AS
        WITH obs AS (
            SELECT base_mst AS mst, min(name) AS sample_name
            FROM stores WHERE source = 'dkkd' AND base_mst <> ''
            GROUP BY base_mst
        ),
        cur AS (SELECT mst, any_value(company_name) AS company_name FROM _curated_company GROUP BY mst)
        SELECT coalesce(obs.mst, cur.mst) AS mst,
               coalesce(cur.company_name, obs.sample_name) AS company_name,
               cur.mst IS NOT NULL AS is_curated_owner,
               obs.mst IS NOT NULL AS is_observed
        FROM obs FULL OUTER JOIN cur ON obs.mst = cur.mst
    """)
    con.execute("DROP TABLE _curated_company")


def _ingest_nso_macro(con, source_path: Path | None = None) -> None:
    """Copy the normalized NSO population/labour source into the serving DB.

    The source is rebuilt independently by an external sync job. A wholesale
    copy keeps the serving database self-contained and read-only.
    """
    source_path = Path(source_path) if source_path else DEFAULT_NSO_MACRO_DB_PATH
    if not source_path.exists():
        print(f"[etl] {source_path} absent — skipping NSO macro ingest; /api/v1/macro/nso/* will 503")
        return

    con.execute(f"ATTACH '{source_path.as_posix()}' AS nso (READ_ONLY)")
    tables = [
        'nso_sync_run',
        'nso_matrix',
        'nso_dimension',
        'nso_dimension_value',
        'nso_observation',
    ]
    try:
        for table in tables:
            con.execute(f'CREATE TABLE {table} AS SELECT * FROM nso."{table}"')
    finally:
        con.execute("DETACH nso")

    con.execute("""
        CREATE VIEW v_nso_macro_series AS
        SELECT o.matrix_id, m.title, m.domain, o.observation_key,
               o.year, o.year_label, o.geography, o.geography_dimension,
               o.series_label, o.value, o.dimensions_json,
               m.source_url, o.fetched_at
        FROM nso_observation o
        JOIN nso_matrix m USING (matrix_id)
    """)


def _ingest_worldbank(con, source_path: Path | None = None) -> None:
    """Copy the World Bank Indicators source (Vietnam + regional peers) into
    the serving DB. The source is rebuilt independently by an external sync
    job. Same wholesale-copy pattern as ``_ingest_nso_macro``.
    """
    source_path = Path(source_path) if source_path else DEFAULT_WORLDBANK_DB_PATH
    if not source_path.exists():
        print(f"[etl] {source_path} absent — skipping World Bank ingest; /api/v1/macro/worldbank/* will 503")
        return

    con.execute(f"ATTACH '{source_path.as_posix()}' AS wb (READ_ONLY)")
    tables = ['wb_sync_run', 'wb_indicator', 'wb_observation']
    try:
        for table in tables:
            con.execute(f'CREATE TABLE {table} AS SELECT * FROM wb."{table}"')
    finally:
        con.execute("DETACH wb")

    con.execute("""
        CREATE VIEW v_worldbank_macro_series AS
        SELECT o.indicator_id, o.indicator_name, o.domain,
               o.country_iso3, o.country_name, o.year, o.value,
               o.unit, o.obs_status, o.fetched_at
        FROM wb_observation o
    """)


def _ingest_moit_macro(con, source_path: Path | None = None) -> None:
    """Copy the MOIT monthly industrial-production/trade statistics source
    into the serving DB. The source is rebuilt independently by an external
    sync job. Same wholesale-copy pattern as
    ``_ingest_nso_macro``/``_ingest_worldbank``.
    """
    source_path = Path(source_path) if source_path else DEFAULT_MOIT_MACRO_DB_PATH
    if not source_path.exists():
        print(f"[etl] {source_path} absent — skipping MOIT macro ingest; /api/v1/macro/moit/* will 503")
        return

    con.execute(f"ATTACH '{source_path.as_posix()}' AS moit (READ_ONLY)")
    tables = ['moit_sync_run', 'moit_report', 'moit_series', 'moit_observation']
    try:
        for table in tables:
            con.execute(f'CREATE TABLE {table} AS SELECT * FROM moit."{table}"')
    finally:
        con.execute("DETACH moit")

    con.execute("""
        CREATE VIEW v_moit_macro_series AS
        SELECT o.observation_key, s.series_id, s.sheet_code, s.sheet_title,
               s.report_year, s.report_month,
               o.dimension_code, o.dimension_label, o.metric_label, o.value,
               r.title AS report_title, r.detail_url, s.fetched_at
        FROM moit_observation o
        JOIN moit_series s USING (series_id)
        JOIN moit_report r USING (report_key)
    """)


def _ingest_nso_market(con, source_path: Path | None = None) -> None:
    """Copy the NSO "number of markets by class and province" source into the
    serving DB. The source is rebuilt independently by an external sync job.
    Same wholesale-copy pattern as
    ``_ingest_nso_macro`` — kept as its own source DB (not merged into
    ``nso_observation``) since it comes from a different NSO backend (the
    classic PX-Web postback UI, not the REST API `nso_observation` is sourced
    from) and has a fixed one-matrix shape rather than the generic
    matrix/dimension model.
    """
    source_path = Path(source_path) if source_path else DEFAULT_NSO_MARKET_DB_PATH
    if not source_path.exists():
        print(f"[etl] {source_path} absent — skipping NSO market ingest")
        return

    con.execute(f"ATTACH '{source_path.as_posix()}' AS nso_market (READ_ONLY)")
    tables = ['nso_market_sync_run', 'nso_market_locality', 'nso_market_observation']
    try:
        for table in tables:
            con.execute(f'CREATE TABLE {table} AS SELECT * FROM nso_market."{table}"')
    finally:
        con.execute("DETACH nso_market")

    con.execute("""
        CREATE VIEW v_nso_market_series AS
        SELECT o.observation_key, o.locality_label, l.row_type, l.region,
               o.year, o.year_label, o.is_preliminary, o.value, o.fetched_at
        FROM nso_market_observation o
        JOIN nso_market_locality l ON l.locality_label = o.locality_label
    """)


def _create_brand_master(
    con,
    brands_dir: Path | None = None,
    brand_master_path: Path | None = None,
) -> None:
    """Materialize dim_brand_master (curated overlay x configs, see
    dkkd/brand_master.py) plus the ecosystem rollup, the company/entity
    bridge, and the search/entities views that federate it with stores.
    """
    from dkkd import brand_master

    # Ecosystem rollups — dkkd source only; license-vs-store invariant enforced
    # (n_operating_stores requires BOTH core_operating_store='Yes' AND
    # operating_status='Operating'; n_licenses is the raw count, kept separate).
    con.execute(f"""
        CREATE VIEW mart_brand_ecosystem AS
        SELECT brand_slug,
               count(*) AS n_licenses,
               count(*) FILTER (WHERE {contract.OPERATING_PREDICATE}) AS n_operating_stores,
               count(DISTINCT base_mst) FILTER (WHERE base_mst <> '') AS n_legal_entities,
               count(*) FILTER (WHERE store_role = 'Warehouse') AS n_warehouses,
               count(*) FILTER (WHERE store_role = 'Corporate') AS n_corporate
        FROM stores WHERE source = 'dkkd'
        GROUP BY brand_slug
    """)

    master_rows = brand_master.assemble_master_rows(
        brands_dir=brands_dir, master_path=brand_master_path,
    )
    cols = brand_master.MASTER_COLUMNS
    ddl = ', '.join(f"{c} {MASTER_COLUMN_TYPES.get(c, 'VARCHAR')}" for c in cols)
    con.execute(f"CREATE TABLE dim_brand_master ({ddl})")
    if master_rows:
        placeholders = ', '.join(['?'] * len(cols))
        con.executemany(
            f"INSERT INTO dim_brand_master VALUES ({placeholders})",
            [[r[c] for c in cols] for r in master_rows],
        )

    _create_company_dim(con, brand_master, brand_master_path)

    con.execute("""
        CREATE VIEW v_brand_search AS
        SELECT m.*, e.n_licenses, e.n_operating_stores, e.n_legal_entities,
               e.n_warehouses, e.n_corporate
        FROM dim_brand_master m
        LEFT JOIN mart_brand_ecosystem e USING (brand_slug)
    """)

    # One row per (brand, mst), joined to dim_company so a curated owner MST
    # and its observed store count are the same row, not two disconnected
    # representations. role is provenance: owner_curated | operator_observed
    # | owner_operator (both — the curated owner also shows up in stores).
    con.execute("""
        CREATE VIEW v_brand_entities AS
        SELECT b.brand_slug, b.mst, c.company_name AS sample_name,
               CASE WHEN bool_or(b.role = 'owner_curated') AND bool_or(b.role = 'operator_observed')
                      THEN 'owner_operator'
                    WHEN bool_or(b.role = 'owner_curated') THEN 'owner_curated'
                    ELSE 'operator_observed' END AS role,
               max(b.n_locations) AS n_locations
        FROM bridge_brand_entity b
        JOIN dim_company c USING (mst)
        GROUP BY b.brand_slug, b.mst, c.company_name
    """)


def _create_scorecard(con) -> None:
    """mart_brand_scorecard: one row per dkkd_master brand, joining its store
    footprint (mart_brand_ecosystem), YTD opening estimate, and top-3
    provinces by operating-store count. Feeds /api/sector/top-brands.
    """
    # CREATE VIEW can't take a bound parameter (DuckDB: "can't be prepared"),
    # and the year must re-evaluate as "this calendar year" on every pipeline
    # rebuild, not freeze to the year etl.py last ran — so it's inlined as a
    # SQL date-part expression, not a Python-computed literal.
    con.execute(f"""
        CREATE VIEW mart_brand_scorecard AS
        SELECT m.brand_slug, m.canonical_name, m.industry, m.subsector,
               m.gics_sector, m.retail_subsector, m.retail_format, m.channel_type,
               m.country_origin, m.domestic_foreign,
               e.n_operating_stores,
               o.openings_ytd_est, p.top_provinces
        FROM dim_brand_master m
        LEFT JOIN mart_brand_ecosystem e USING (brand_slug)
        LEFT JOIN (
            SELECT brand_slug, count(*) AS openings_ytd_est
            FROM stores
            WHERE source = 'dkkd' AND {contract.OPERATING_PREDICATE}
              AND opening_date >= date_trunc('year', current_date)::DATE::VARCHAR
            GROUP BY brand_slug
        ) o USING (brand_slug)
        LEFT JOIN (
            SELECT brand_slug,
                   list({{'province': province, 'count': operating_count}} ORDER BY operating_count DESC)[1:3]
                       AS top_provinces
            FROM (
                SELECT brand_slug, province, count(*) AS operating_count
                FROM stores
                WHERE source = 'dkkd' AND {contract.OPERATING_PREDICATE}
                  AND province IS NOT NULL AND province <> ''
                GROUP BY brand_slug, province
            )
            GROUP BY brand_slug
        ) p USING (brand_slug)
        WHERE m.record_source = 'dkkd_master'
    """)


def build_serving_db(
    db_path: Path | None = None,
    staging_dir: Path | None = None,
    brands_dir: Path | None = None,
    brand_master_path: Path | None = None,
    nso_macro_db_path: Path | None = None,
    worldbank_db_path: Path | None = None,
    moit_macro_db_path: Path | None = None,
    verbose: bool = True,
) -> int:
    """Build the read-only serving DuckDB from staging Parquet. Builds to a
    `.tmp` file and atomically replaces the live DB so a concurrently-open
    read connection is never handed a half-built file.
    """
    import duckdb

    db_path = Path(db_path or DEFAULT_SERVING_DB_PATH)
    staging_dir = Path(staging_dir or DEFAULT_STAGING_DIR)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = db_path.with_suffix(db_path.suffix + '.tmp')
    if tmp_path.exists():
        tmp_path.unlink()

    con = duckdb.connect(str(tmp_path))
    try:
        dkkd_parquet = (staging_dir / 'stores_dkkd.parquet').as_posix()
        website_parquet = (staging_dir / 'stores_website.parquet').as_posix()
        ir_parquet = (staging_dir / 'benchmarks_ir.parquet').as_posix()

        con.execute(f"""
            CREATE TABLE stores AS
            SELECT * FROM read_parquet(['{dkkd_parquet}', '{website_parquet}'])
        """)
        con.execute(f"CREATE TABLE benchmarks AS SELECT * FROM read_parquet('{ir_parquet}')")

        snapshot_files = sorted((staging_dir / 'snapshots').glob('*.parquet'))
        if snapshot_files:
            snapshot_list = ', '.join(f"'{f.as_posix()}'" for f in snapshot_files)
            con.execute(f"CREATE TABLE fact_store_snapshot AS SELECT * FROM read_parquet([{snapshot_list}])")
        else:
            snapshot_ddl = ', '.join(f"{c} TEXT" for c in conform.SNAPSHOT_COLUMNS)
            con.execute(f"CREATE TABLE fact_store_snapshot ({snapshot_ddl})")

        con.execute("CREATE INDEX idx_stores_source ON stores(source)")
        con.execute("CREATE INDEX idx_stores_brand ON stores(brand_slug)")
        con.execute("CREATE INDEX idx_stores_province ON stores(province)")

        # Relocates the SQLite `licenses`-table v_operating_stores view's
        # functionality here ahead of that database's removal — same
        # confirmed-operating-store subset, over the serving `stores` table.
        con.execute(f"""
            CREATE VIEW v_operating_stores AS
            SELECT * FROM stores WHERE source = 'dkkd' AND {contract.OPERATING_PREDICATE}
        """)

        _create_marts(con)
        _create_data_dictionary(con)
        _create_brand_master(con, brands_dir, brand_master_path)
        _ingest_nso_macro(con, nso_macro_db_path)
        _ingest_worldbank(con, worldbank_db_path)
        _ingest_moit_macro(con, moit_macro_db_path)
        _ingest_nso_market(con)
        _create_scorecard(con)

        total = con.execute("SELECT count(*) FROM stores").fetchone()[0]
    finally:
        con.close()

    if db_path.exists():
        db_path.unlink()
    os.replace(tmp_path, db_path)

    if verbose:
        print(f"  Serving DB -> {db_path} ({total} rows)")

    return total


def run_pipeline(
    staging_dir: Path | None = None,
    db_path: Path | None = None,
    brands_dir: Path | None = None,
    website_brands_dir: Path | None = None,
    ir_csv: Path | None = None,
    brand_master_path: Path | None = None,
    verbose: bool = True,
) -> int:
    """Rebuild staging then the serving DB. Returns the total stores row count."""
    build_staging(staging_dir, brands_dir, website_brands_dir, ir_csv, verbose)
    return build_serving_db(
        db_path, staging_dir, brands_dir, brand_master_path, verbose=verbose,
    )
