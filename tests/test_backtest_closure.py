"""Tests for the closure-signal accuracy backtest section."""
import pytest

from dkkd.backtest import run_backtest
from tests.conftest import setup_test_brand


def _setup(tmp_path, records, ground_truth=None):
    setup_test_brand(tmp_path, records, ground_truth=ground_truth)


def _report_text(tmp_path):
    return (tmp_path / 'test-brand' / 'output' / 'test-brand_backtest_report.md').read_text(
        encoding='utf-8')


def test_closure_section_absent_without_ground_truth_file(tmp_path):
    records = [
        ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
               'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '123, TP. HCM',
               'Operating_Status': 'Operating', 'Operating_Evidence': 'locator:Unique'}],
    ]
    _setup(tmp_path, records)
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert 'Closure Signal Accuracy' not in text


def test_closure_section_insufficient_ground_truth_under_three_points(tmp_path):
    records = [
        ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
               'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '123, TP. HCM',
               'Operating_Status': 'Closed', 'Operating_Evidence': 'structural:parent-dissolved'}],
    ]
    ground_truth = {'1': {'label': 'Closed', 'status_raw': 'Chấm dứt hoạt động'}}
    _setup(tmp_path, records, ground_truth)
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert 'Insufficient ground truth' in text


def test_closure_section_confusion_matrix_and_metrics(tmp_path):
    records = [
        ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
               'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '1',
               'Operating_Status': 'Closed', 'Operating_Evidence': 'structural:parent-dissolved'}],
        ['2', {'Id': '2', 'Name': 'CO.OP FOOD 2', 'Name_F': 'co op food 2',
               'Enterprise_Gdt_Code': '0309129418-002', 'Ho_Address': '2',
               'Operating_Status': 'Closed', 'Operating_Evidence': 'structural:superseded:9'}],
        ['3', {'Id': '3', 'Name': 'CO.OP FOOD 3', 'Name_F': 'co op food 3',
               'Enterprise_Gdt_Code': '0309129418-003', 'Ho_Address': '3',
               'Operating_Status': 'Operating', 'Operating_Evidence': 'locator:Unique'}],
        ['4', {'Id': '4', 'Name': 'CO.OP FOOD 4', 'Name_F': 'co op food 4',
               'Enterprise_Gdt_Code': '0309129418-004', 'Ho_Address': '4',
               'Operating_Status': 'Unverified', 'Operating_Evidence': 'licensed-unverified'}],
    ]
    ground_truth = {
        '1': {'label': 'Closed', 'status_raw': 'Chấm dứt hoạt động'},
        '2': {'label': 'Operating', 'status_raw': 'Đang hoạt động'},
        '3': {'label': 'Closed', 'status_raw': 'Chấm dứt hoạt động'},
        '4': {'label': 'Operating', 'status_raw': 'Đang hoạt động'},
    }
    _setup(tmp_path, records, ground_truth)
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert '1 (TP)' in text
    assert '1 (FP)' in text
    assert '1 (FN)' in text
    assert '1 (TN)' in text
    assert 'Precision | 50.0%' in text
    assert 'Recall | 50.0%' in text


def test_closure_section_per_evidence_rung_precision(tmp_path):
    records = [
        ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
               'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '1',
               'Operating_Status': 'Closed', 'Operating_Evidence': 'structural:parent-dissolved'}],
        ['2', {'Id': '2', 'Name': 'CO.OP FOOD 2', 'Name_F': 'co op food 2',
               'Enterprise_Gdt_Code': '0309129418-002', 'Ho_Address': '2',
               'Operating_Status': 'Closed', 'Operating_Evidence': 'structural:parent-dissolved'}],
        ['3', {'Id': '3', 'Name': 'CO.OP FOOD 3', 'Name_F': 'co op food 3',
               'Enterprise_Gdt_Code': '0309129418-003', 'Ho_Address': '3',
               'Operating_Status': 'Closed', 'Operating_Evidence': 'structural:superseded:9'}],
    ]
    ground_truth = {
        '1': {'label': 'Closed', 'status_raw': 'Chấm dứt hoạt động'},
        '2': {'label': 'Closed', 'status_raw': 'Chấm dứt hoạt động'},
        '3': {'label': 'Operating', 'status_raw': 'Đang hoạt động'},
    }
    _setup(tmp_path, records, ground_truth)
    run_backtest('test-brand', brands_dir=tmp_path)
    text = _report_text(tmp_path)
    assert '| structural:parent-dissolved | 2 | 100.0%' in text
    assert '| structural:superseded:9 | 1 | 0.0%' in text
