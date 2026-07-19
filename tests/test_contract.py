"""Tests for dkkd/contract.py — the single source of truth for the operating-
store SQL predicate and the merged column data dictionary.
"""
import duckdb

from dkkd import contract


def test_operating_predicate_is_nonempty_and_references_both_fields():
    assert isinstance(contract.OPERATING_PREDICATE, str)
    assert contract.OPERATING_PREDICATE.strip()
    assert 'core_operating_store' in contract.OPERATING_PREDICATE
    assert 'operating_status' in contract.OPERATING_PREDICATE


def test_data_dictionary_rows_are_3_tuples_with_no_duplicate_columns():
    assert isinstance(contract.DATA_DICTIONARY, list)
    assert len(contract.DATA_DICTIONARY) > 0
    seen = set()
    for row in contract.DATA_DICTIONARY:
        assert len(row) == 3
        column_name, data_source, description = row
        assert isinstance(column_name, str) and column_name
        assert isinstance(data_source, str) and data_source
        assert isinstance(description, str) and description.strip()
        assert column_name not in seen, f"duplicate column_name: {column_name}"
        seen.add(column_name)


def test_operating_predicate_matches_expected_row_count_in_duckdb():
    # Regression test for the 4-copies drift risk: build a tiny in-memory
    # `stores` table mixing source/core_operating_store/operating_status
    # combinations, apply OPERATING_PREDICATE via a view, and check the count
    # against a hand-computed expectation.
    con = duckdb.connect()
    try:
        con.execute("""
            CREATE TABLE stores (
                source VARCHAR, core_operating_store VARCHAR, operating_status VARCHAR
            )
        """)
        rows = [
            ('dkkd', 'Yes', 'Operating'),      # counts
            ('dkkd', 'Yes', 'Closed'),         # no: not Operating
            ('dkkd', 'No', 'Operating'),       # no: not core
            ('dkkd', 'No', 'Closed'),          # no
            ('dkkd', 'Yes', 'Operating'),      # counts
            ('website', None, None),           # no: nulls
            ('website', None, None),           # no: nulls
        ]
        con.executemany("INSERT INTO stores VALUES (?, ?, ?)", rows)

        con.execute(f"""
            CREATE VIEW v_operating_stores AS
            SELECT * FROM stores WHERE source = 'dkkd' AND {contract.OPERATING_PREDICATE}
        """)
        count = con.execute("SELECT count(*) FROM v_operating_stores").fetchone()[0]
        assert count == 2
    finally:
        con.close()
