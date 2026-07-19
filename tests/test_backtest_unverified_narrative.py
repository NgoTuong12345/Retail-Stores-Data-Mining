"""Tests for the Unverified-Locations line in reference-mode backtest reports.

Follows the fixture pattern from tests/test_backtest_greenfield.py's _setup
helper, but with a `backtest:` config block (reference mode) instead of
greenfield mode, plus a `{slug}.csv` full dataset (required by reference mode)
and an optional `{slug}_unverified.csv`.
"""
import json

import pandas as pd

from dkkd.backtest import run_backtest


_CONFIG_WITH_BACKTEST = (
    "slug: test-ref-brand\n"
    "name: Test Ref Brand\n"
    "brand_regex: 'TEST\\ ?BRAND'\n"
    "spelling_variants:\n"
    "  - 'TEST BRAND'\n"
    "backtest:\n"
    "  report_label: 'Official website'\n"
    "  expected_total: 2\n"
)

_FULL_CSV_ROWS = [
    {'Id': '1', 'Name': 'TEST BRAND 1', 'Core_Operating_Store': 'Yes',
     'Store_Type_MSN': 'Standard', 'Store_Brand_Format': 'Test Brand',
     'Ho_Address': '123 Đường A, Quận 1, TP. Hồ Chí Minh'},
    {'Id': '2', 'Name': 'TEST BRAND 2', 'Core_Operating_Store': 'Yes',
     'Store_Type_MSN': 'Standard', 'Store_Brand_Format': 'Test Brand',
     'Ho_Address': '456 Đường B, Quận Hoàn Kiếm, Hà Nội'},
]

_UNVERIFIED_ROWS = [
    {'Id': '3', 'Name': 'TEST BRAND 3 (unverified)', 'Ho_Address': '789 Đường C, TP. Đà Nẵng'},
    {'Id': '4', 'Name': 'TEST BRAND 4 (unverified)', 'Ho_Address': '10 Đường D, TP. Đà Nẵng'},
]


def _setup(tmp_path, slug='test-ref-brand', with_unverified=False):
    bd = tmp_path / slug
    (bd / 'output').mkdir(parents=True)
    (bd / 'config.yaml').write_text(_CONFIG_WITH_BACKTEST, encoding='utf-8')
    (bd / 'state.json').write_text(json.dumps({'phase_history': [], 'convergence': {}}), encoding='utf-8')
    (bd / 'checkpoint.json').write_text(json.dumps([]), encoding='utf-8')
    pd.DataFrame(_FULL_CSV_ROWS).to_csv(bd / 'output' / f'{slug}.csv', index=False)
    if with_unverified:
        pd.DataFrame(_UNVERIFIED_ROWS).to_csv(bd / 'output' / f'{slug}_unverified.csv', index=False)
    return bd / 'output' / f'{slug}_backtest_report.md'


def test_unverified_line_present_with_count_when_file_exists(tmp_path):
    report_path = _setup(tmp_path, with_unverified=True)
    run_backtest('test-ref-brand', brands_dir=tmp_path)
    text = report_path.read_text(encoding='utf-8')
    assert 'Unverified Locations' in text
    assert '2' in text
    lines = [l for l in text.splitlines() if 'Unverified Locations' in l]
    assert any('2' in l for l in lines)


def test_unverified_line_absent_when_no_unverified_csv(tmp_path):
    report_path = _setup(tmp_path, with_unverified=False)
    run_backtest('test-ref-brand', brands_dir=tmp_path)
    text = report_path.read_text(encoding='utf-8')
    assert 'Unverified Locations' not in text
