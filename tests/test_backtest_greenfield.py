"""Tests for greenfield invariant backtest mode (no external benchmark)."""
import pytest

from dkkd.backtest import run_backtest
from tests.conftest import setup_test_brand, _CONVERGED_STATE

_GOOD_RECORDS = [
    ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
           'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '123, TP. HCM'}],
    ['2', {'Id': '2', 'Name': 'CO.OP FOOD 2', 'Name_F': 'co op food 2',
           'Enterprise_Gdt_Code': '0309129418-002', 'Ho_Address': '456, Bình Dương'}],
]


def _setup(tmp_path, state=None, records=None, config=None):
    setup_test_brand(tmp_path, records or _GOOD_RECORDS, state=state, config=config)


class TestGreenfieldBacktest:
    def _report(self, tmp_path):
        return tmp_path / 'test-brand' / 'output' / 'test-brand_backtest_report.md'

    def test_writes_report_when_no_backtest_config(self, tmp_path):
        _setup(tmp_path)
        run_backtest('test-brand', brands_dir=tmp_path)
        assert self._report(tmp_path).exists()

    def test_report_contains_all_five_invariant_rows(self, tmp_path):
        _setup(tmp_path)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        assert 'Convergence reached' in text
        assert 'Dedup integrity' in text
        assert 'Brand filter compliance' in text
        assert 'GDT branch coverage' in text
        assert 'Playbook completeness' in text

    def test_all_pass_for_clean_data(self, tmp_path):
        _setup(tmp_path)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        assert text.count('PASS') == 5
        assert 'FAIL' not in text

    def test_convergence_fail_when_not_converged(self, tmp_path):
        state = dict(_CONVERGED_STATE)
        state['convergence'] = {'converged': False, 'rule': 'still running'}
        _setup(tmp_path, state=state)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        lines = [l for l in text.splitlines() if 'Convergence reached' in l]
        assert any('FAIL' in l for l in lines)

    def test_dedup_fail_when_duplicate_ids_in_checkpoint(self, tmp_path):
        records = [
            ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
                   'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '123, TP. HCM'}],
            ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1 dup', 'Name_F': 'co op food 1 dup',
                   'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '123, TP. HCM'}],
        ]
        _setup(tmp_path, records=records)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        lines = [l for l in text.splitlines() if 'Dedup integrity' in l]
        assert any('FAIL' in l for l in lines)

    def test_brand_filter_fail_when_non_matching_record(self, tmp_path):
        records = [
            ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
                   'Enterprise_Gdt_Code': '0309129418-001', 'Ho_Address': '123, TP. HCM'}],
            ['2', {'Id': '2', 'Name': 'SOME OTHER BRAND', 'Name_F': 'some other brand',
                   'Enterprise_Gdt_Code': '0309129418-002', 'Ho_Address': '456, Bình Dương'}],
        ]
        _setup(tmp_path, records=records)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        lines = [l for l in text.splitlines() if 'Brand filter' in l]
        assert any('FAIL' in l for l in lines)

    def test_gdt_coverage_fail_when_no_branch_format_codes(self, tmp_path):
        records = [
            ['1', {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': 'co op food 1',
                   'Enterprise_Gdt_Code': '00001', 'Ho_Address': '123, TP. HCM'}],
        ]
        _setup(tmp_path, records=records)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        lines = [l for l in text.splitlines() if 'GDT branch coverage' in l]
        assert any('FAIL' in l for l in lines)

    def test_playbook_fail_when_strategy_missing_from_history(self, tmp_path):
        state = {
            'phase_history': [
                # Missing parent_mst
                {'strategy': 'brand_variants', 'params': {}, 'probes': 10, 'added': 5, 'total': 5},
                {'strategy': 'solr_escape',    'params': {}, 'probes': 5,  'added': 0, 'total': 5},
                {'strategy': 'solr_escape',    'params': {}, 'probes': 50, 'added': 0, 'total': 5},
            ],
            'convergence': {'converged': True, 'rule': '3 consecutive phases'},
        }
        _setup(tmp_path, state=state)
        run_backtest('test-brand', brands_dir=tmp_path)
        text = self._report(tmp_path).read_text()
        lines = [l for l in text.splitlines() if 'Playbook completeness' in l]
        assert any('FAIL' in l for l in lines)
