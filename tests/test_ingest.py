"""Tests for dkkd.ingest — Ingester.ingest."""
import pytest
from dkkd.config import BrandConfig
from dkkd.ingest import Ingester
from tests.conftest import make_row

# Use Co.op Food regex from the legacy scraper
CF_REGEX = r'CO[\.\\,\-]?\s*OP\s*FOOD|COOPFOOD'

def _make_config():
    return BrandConfig(
        slug='coop-food',
        name='Co.op Food',
        brand_regex=CF_REGEX,
    )

class TestIngester:
    def test_name_matches(self):
        ing = Ingester(_make_config())
        added = ing.ingest([make_row('1', 'CO.OP FOOD store 1')])
        assert added == 1
        assert '1' in ing.store_map

    def test_name_f_matches(self):
        ing = Ingester(_make_config())
        added = ing.ingest([make_row('2', 'Some Store', 'COOPFOOD branch')])
        assert added == 1

    def test_neither_matches_rejected(self):
        ing = Ingester(_make_config())
        added = ing.ingest([make_row('3', 'Bach Hoa Xanh', 'BHX')])
        assert added == 0
        assert '3' not in ing.store_map

    def test_dedup_on_id(self):
        ing = Ingester(_make_config())
        ing.ingest([make_row('1', 'CO.OP FOOD 1')])
        added = ing.ingest([make_row('1', 'CO.OP FOOD 1 duplicate')])
        assert added == 0
        assert len(ing.store_map) == 1

    def test_no_id_skipped(self):
        ing = Ingester(_make_config())
        added = ing.ingest([{'Name': 'CO.OP FOOD', 'Name_F': ''}])
        assert added == 0

    def test_none_row_skipped(self):
        ing = Ingester(_make_config())
        added = ing.ingest([None])
        assert added == 0

    def test_empty_row_skipped(self):
        ing = Ingester(_make_config())
        added = ing.ingest([{}])
        assert added == 0
