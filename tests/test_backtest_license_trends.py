"""Tests for the license-trends backtest section."""
import json

from dkkd.backtest import run_backtest
from tests.conftest import setup_test_brand, _CONVERGED_STATE, _MINIMAL_CONFIG


def _setup(tmp_path, records):
    setup_test_brand(tmp_path, records)


def _report_text(tmp_path):
    return (tmp_path / 'test-brand' / 'output' / 'test-brand_backtest_report.md').read_text(
        encoding='utf-8')


def _rec(id_, gdt, year=None):
    r = {'Id': id_, 'Name': 'CO.OP FOOD ' + id_, 'Name_F': 'co op food ' + id_,
         'Enterprise_Gdt_Code': gdt, 'Ho_Address': id_}
    if year is not None:
        r['Establishment_Year'] = year
    return r


def test_license_trends_section_absent_when_checkpoint_missing(tmp_path):
    bd = tmp_path / 'test-brand'
    bd.mkdir()
    (bd / 'output').mkdir()
    (bd / 'config.yaml').write_text(_MINIMAL_CONFIG, encoding='utf-8')
    (bd / 'state.json').write_text(json.dumps(_CONVERGED_STATE), encoding='utf-8')
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert 'License Trends' not in text


def test_license_trends_section_shows_distribution_and_growth_curve(tmp_path):
    records = [
        ['1', _rec('1', '0309129418-001', year=2018)],
        ['2', _rec('2', '0309129418-002', year=2018)],
        ['3', _rec('3', '0309129418-003', year=2020)],
        ['4', _rec('4', '9999999999-001')],
    ]
    _setup(tmp_path, records)
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert 'License Trends' in text
    assert '| 0309129418 | 3 |' in text
    assert '| 9999999999 | 1 |' in text
    assert 'MST `0309129418` (3 stores)' in text
    assert '| 2018 | 2 |' in text
    assert '| 2020 | 1 |' in text
    # Single-store MST must not get a growth-curve subsection of its own.
    assert 'MST `9999999999`' not in text.split('MST `0309129418`')[1]


def test_license_trends_section_single_store_msts_only_has_no_growth_curve(tmp_path):
    records = [
        ['1', _rec('1', '1111111111-001')],
        ['2', _rec('2', '2222222222-001')],
    ]
    _setup(tmp_path, records)
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert 'License Trends' in text
    assert 'openings per year' not in text
