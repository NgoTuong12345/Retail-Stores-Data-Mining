"""Tests for _build_date_backtest_section (LOO cross-validation of DateInterpolator).

Covers:
- No status file → returns ''
- Fewer than 3 ground-truth points → returns 'Insufficient' message
- Perfect linear data → section contains expected headers
- Stores missing from checkpoint → excluded from LOO count
- Empty ngay_hd entries → excluded from ground truth
- Multiple missing stores still runs when ≥3 valid points remain
"""
import json
import pathlib
import tempfile

from dkkd.backtest import _build_date_backtest_section


def _write_fixtures(brands_dir: pathlib.Path, slug: str,
                    statuses: dict, records: list) -> None:
    brand_dir = brands_dir / slug
    out_dir = brand_dir / 'output'
    out_dir.mkdir(parents=True, exist_ok=True)
    (brand_dir / 'checkpoint.json').write_text(
        json.dumps(records), encoding='utf-8'
    )
    (out_dir / 'masothue_store_statuses.json').write_text(
        json.dumps(statuses), encoding='utf-8'
    )


def _run(statuses: dict, records: list) -> str:
    with tempfile.TemporaryDirectory() as d:
        brands_dir = pathlib.Path(d)
        _write_fixtures(brands_dir, 'test-brand', statuses, records)
        return _build_date_backtest_section('test-brand', brands_dir=brands_dir)


def _linear_fixtures(n: int = 5):
    """n Format B stores on a perfect linear Id→date ramp (100 Ids = 1 year)."""
    records = [
        [None, {'Id': str(100 * (i + 1)), 'Enterprise_Gdt_Code': f'0123456789-{i+1:03d}'}]
        for i in range(n)
    ]
    statuses = {
        f'0123456789-{i+1:03d}': {'ngay_hd': f'{2010 + i}-01-01'}
        for i in range(n)
    }
    return statuses, records


def test_missing_file_returns_empty_string():
    with tempfile.TemporaryDirectory() as d:
        brands_dir = pathlib.Path(d)
        brand_dir = brands_dir / 'test-brand'
        (brand_dir / 'output').mkdir(parents=True)
        (brand_dir / 'checkpoint.json').write_text('[]', encoding='utf-8')
        result = _build_date_backtest_section('test-brand', brands_dir=brands_dir)
        assert result == ''


class TestInsufficientData:
    def test_zero_points_returns_insufficient(self):
        statuses: dict = {}
        records: list = []
        result = _run(statuses, records)
        assert 'Insufficient' in result

    def test_one_point_returns_insufficient(self):
        statuses = {'0123456789-001': {'ngay_hd': '2015-01-01'}}
        records = [[None, {'Id': '100', 'Enterprise_Gdt_Code': '0123456789-001'}]]
        result = _run(statuses, records)
        assert 'Insufficient' in result
        assert '1 ground-truth' in result

    def test_two_points_returns_insufficient(self):
        statuses = {
            '0123456789-001': {'ngay_hd': '2015-01-01'},
            '0123456789-002': {'ngay_hd': '2017-06-01'},
        }
        records = [
            [None, {'Id': '100', 'Enterprise_Gdt_Code': '0123456789-001'}],
            [None, {'Id': '300', 'Enterprise_Gdt_Code': '0123456789-002'}],
        ]
        result = _run(statuses, records)
        assert 'Insufficient' in result
        assert '2 ground-truth' in result


class TestSectionStructure:
    def test_headers_present_with_five_points(self):
        statuses, records = _linear_fixtures(5)
        result = _run(statuses, records)
        assert 'LOO Cross-Validation' in result
        assert '5' in result
        assert 'Interpolated' in result
        assert 'Extrapolated' in result
        assert 'Worst misses' in result
        assert 'MAE' in result

    def test_n_reported_correctly(self):
        statuses, records = _linear_fixtures(7)
        result = _run(statuses, records)
        assert '**7**' in result

    def test_three_points_minimum_runs(self):
        statuses, records = _linear_fixtures(3)
        result = _run(statuses, records)
        assert 'LOO Cross-Validation' in result
        assert 'Insufficient' not in result


class TestGroundTruthFiltering:
    def test_gdt_not_in_checkpoint_excluded(self):
        statuses = {
            '0123456789-001': {'ngay_hd': '2010-01-01'},
            '0123456789-002': {'ngay_hd': '2012-01-01'},
            '0123456789-003': {'ngay_hd': '2014-01-01'},
            '0123456789-999': {'ngay_hd': '2020-01-01'},  # NOT in records
        }
        records = [
            [None, {'Id': '100', 'Enterprise_Gdt_Code': '0123456789-001'}],
            [None, {'Id': '300', 'Enterprise_Gdt_Code': '0123456789-002'}],
            [None, {'Id': '500', 'Enterprise_Gdt_Code': '0123456789-003'}],
        ]
        result = _run(statuses, records)
        # 3 valid points (not 4) → LOO runs, reports 3
        assert '**3**' in result

    def test_empty_ngay_hd_excluded(self):
        statuses = {
            '0123456789-001': {'ngay_hd': '2010-01-01'},
            '0123456789-002': {'ngay_hd': ''},           # excluded
            '0123456789-003': {'ngay_hd': '2014-01-01'},
        }
        records = [
            [None, {'Id': '100', 'Enterprise_Gdt_Code': '0123456789-001'}],
            [None, {'Id': '300', 'Enterprise_Gdt_Code': '0123456789-002'}],
            [None, {'Id': '500', 'Enterprise_Gdt_Code': '0123456789-003'}],
        ]
        result = _run(statuses, records)
        # Only 2 valid → insufficient
        assert 'Insufficient' in result
        assert '2 ground-truth' in result

    def test_missing_ngay_hd_key_excluded(self):
        statuses = {
            '0123456789-001': {'ngay_hd': '2010-01-01'},
            '0123456789-002': {'tinh_trang': 'active'},  # no ngay_hd key at all
            '0123456789-003': {'ngay_hd': '2014-01-01'},
        }
        records = [
            [None, {'Id': '100', 'Enterprise_Gdt_Code': '0123456789-001'}],
            [None, {'Id': '300', 'Enterprise_Gdt_Code': '0123456789-002'}],
            [None, {'Id': '500', 'Enterprise_Gdt_Code': '0123456789-003'}],
        ]
        result = _run(statuses, records)
        assert 'Insufficient' in result

    def test_records_with_non_integer_id_skipped_gracefully(self):
        statuses = {
            '0123456789-001': {'ngay_hd': '2010-01-01'},
            '0123456789-002': {'ngay_hd': '2012-01-01'},
            '0123456789-003': {'ngay_hd': '2014-01-01'},
            '0123456789-004': {'ngay_hd': '2016-01-01'},
        }
        records = [
            [None, {'Id': '100',  'Enterprise_Gdt_Code': '0123456789-001'}],
            [None, {'Id': 'XXXX', 'Enterprise_Gdt_Code': '0123456789-002'}],  # non-int
            [None, {'Id': '500',  'Enterprise_Gdt_Code': '0123456789-003'}],
            [None, {'Id': '700',  'Enterprise_Gdt_Code': '0123456789-004'}],
        ]
        result = _run(statuses, records)
        # 3 valid points (002 skipped) → LOO runs
        assert 'LOO Cross-Validation' in result
        assert '**3**' in result


class TestPerfectLinearAccuracy:
    """On perfectly collinear data, LOO predictions should be exact."""

    def test_mae_row_present_and_numeric(self):
        statuses, records = _linear_fixtures(6)
        result = _run(statuses, records)
        # Section must include the accuracy stats row for all points
        assert '**All**' in result
        # The MAE value in the table should be a number (we just check it renders)
        assert 'days)' in result

    def test_within_30_days_row_present(self):
        statuses, records = _linear_fixtures(5)
        result = _run(statuses, records)
        assert '≤ 30 days' in result
        assert '≤ 90 days' in result
