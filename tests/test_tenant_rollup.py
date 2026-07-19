# tests/test_tenant_rollup.py
"""Tests for the per-host tenant-count rollup."""
import csv

from dkkd.tenant import host_rollup, write_host_effectiveness


def _tenant(host, date):
    return {'store_role': 'in_brand_tenant', 'host_store': host, 'Establishment_Date': date}


class TestHostRollup:
    def test_groups_by_folded_host_and_counts(self):
        stores = [
            _tenant('CO.OPXTRA SƯ VẠN HẠNH', '2020-08-22'),
            _tenant('Co.opXtra Sư Vạn Hạnh', '2017-12-17'),
            _tenant('Co.opXtra Crescent Mall', '2023-03-19'),
        ]
        rows = host_rollup(stores)
        by_count = {r['tenant_count'] for r in rows}
        assert by_count == {2, 1}
        top = rows[0]
        assert top['tenant_count'] == 2
        assert top['first_tenant_date'] == '2017-12-17'
        assert top['last_tenant_date'] == '2020-08-22'

    def test_excludes_own_store_and_unrelated(self):
        stores = [
            {'store_role': 'own_store', 'host_store': '', 'Establishment_Date': '2016-01-01'},
            {'store_role': 'unrelated', 'host_store': '', 'Establishment_Date': '2012-01-01'},
            _tenant('Co.opXtra ABC', '2020-01-01'),
        ]
        rows = host_rollup(stores)
        assert len(rows) == 1
        assert rows[0]['host_store'] == 'Co.opXtra ABC'

    def test_unattributed_bucket_sorts_last(self):
        stores = [
            _tenant('', '2020-01-01'),
            _tenant('Co.opXtra ABC', '2019-01-01'),
            _tenant('Co.opXtra ABC', '2021-01-01'),
        ]
        rows = host_rollup(stores)
        assert rows[-1]['host_store'] == '(unattributed)'
        assert rows[-1]['tenant_count'] == 1


def test_write_host_effectiveness_writes_csv(tmp_path):
    stores = [
        {'store_role': 'in_brand_tenant', 'host_store': 'Co.opXtra ABC', 'Establishment_Date': '2020-01-01'},
        {'store_role': 'in_brand_tenant', 'host_store': 'Co.opXtra ABC', 'Establishment_Date': '2021-01-01'},
    ]
    path = tmp_path / 'he.csv'
    write_host_effectiveness(stores, path)
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['host_store'] == 'Co.opXtra ABC'
    assert rows[0]['tenant_count'] == '2'
    assert list(rows[0].keys()) == ['host_store', 'tenant_count', 'first_tenant_date', 'last_tenant_date']
