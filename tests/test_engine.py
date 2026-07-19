"""Tests for DkkdEngine (Task 13), checkpoint (Task 14), and state_report (Task 15)."""
import json
import pytest
from pathlib import Path

from dkkd.config import BrandConfig
from dkkd.engine import DkkdEngine
from dkkd.records import SweepState
from dkkd.strategies.base import Probe
from dkkd import state_report
from tests.conftest import FakeTransport


def _coop_config():
    return BrandConfig(
        slug='coop-food', name='Co.op Food',
        brand_regex=r'CO[\.\\\,\-]?\s*OP\s*FOOD|COOPFOOD',
        spelling_variants=['CO.OP FOOD', 'COOPFOOD'],
        seed_parent_msts=['0309129418'],
    )


def _make_transport(responses=None):
    return FakeTransport(responses or {})


# --- Task 13: DkkdEngine.sweep ---
class TestEngineSweep:
    def test_sweep_ingests_matching_rows(self, tmp_path):
        transport = _make_transport({
            'CO.OP FOOD': [
                {'Id': '1', 'Name': 'CO.OP FOOD Store 1', 'Name_F': ''},
                {'Id': '2', 'Name': 'CO.OP FOOD Store 2', 'Name_F': ''},
            ],
        })
        engine = DkkdEngine(_coop_config(), transport, brands_dir=tmp_path, throttle=False)
        probes = [Probe(search_field='CO.OP FOOD')]
        added = engine.sweep(probes, 'test')
        assert added == 2
        assert len(engine.store_map) == 2

    def test_sweep_deduplicates(self, tmp_path):
        transport = _make_transport({
            'q1': [{'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': ''}],
            'q2': [{'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': ''}],  # same Id
        })
        engine = DkkdEngine(_coop_config(), transport, brands_dir=tmp_path, throttle=False)
        probes = [Probe(search_field='q1'), Probe(search_field='q2')]
        added = engine.sweep(probes, 'test')
        assert added == 1

    def test_sweep_empty_response_triggers_refresh(self, tmp_path):
        # 20 consecutive empty responses should trigger refresh_token
        transport = _make_transport({})  # all queries return empty
        engine = DkkdEngine(_coop_config(), transport, brands_dir=tmp_path, throttle=False)
        probes = [Probe(search_field=f'q{i}') for i in range(25)]
        engine.sweep(probes, 'test')
        # After 20 empties, refresh_token called; queries 21-25 continue
        assert transport.refresh_count >= 1

    def test_sweep_with_extra(self, tmp_path):
        transport = _make_transport({
            'CO.OP FOOD': [{'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': ''}],
        })
        engine = DkkdEngine(_coop_config(), transport, brands_dir=tmp_path, throttle=False)
        probes = [Probe(search_field='CO.OP FOOD', extra={'sortField': 'Id'})]
        engine.sweep(probes, 'test')
        assert transport.calls[0] == ('CO.OP FOOD', {'sortField': 'Id'})


# --- Task 14: Checkpoint round-trip ---
class TestCheckpoint:
    def test_save_load_roundtrip(self, tmp_path):
        config = _coop_config()
        transport = _make_transport({
            'q': [
                {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Name_F': ''},
                {'Id': '2', 'Name': 'CO.OP FOOD 2', 'Name_F': ''},
            ],
        })
        engine = DkkdEngine(config, transport, brands_dir=tmp_path, throttle=False)
        engine.sweep([Probe(search_field='q')], 'test')
        assert len(engine.store_map) == 2

        # Save
        engine.save_checkpoint()
        cp_path = tmp_path / 'coop-food' / 'checkpoint.json'
        assert cp_path.exists()

        # Verify format: [[id, record], ...]
        with open(cp_path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert all(isinstance(pair, list) and len(pair) == 2 for pair in data)

        # Load into fresh engine
        engine2 = DkkdEngine(config, _make_transport(), brands_dir=tmp_path, throttle=False)
        loaded = engine2.load_checkpoint()
        assert loaded == 2
        assert set(engine2.store_map.keys()) == set(engine.store_map.keys())

    def test_load_missing_checkpoint(self, tmp_path):
        engine = DkkdEngine(_coop_config(), _make_transport(), brands_dir=tmp_path, throttle=False)
        loaded = engine.load_checkpoint()
        assert loaded == 0


# --- Task 15: state_report.build ---
class TestStateReport:
    def test_report_structure(self):
        config = _coop_config()
        state = SweepState(
            store_map={
                '1': {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Enterprise_Gdt_Code': '00036'},
            },
            phase_history=[
                {'strategy': 'brand_variants', 'added': 1},
            ],
        )
        report = state_report.build(config, state)

        assert report['total_records'] == 1
        assert 'phase_history' in report
        assert 'discovered' in report
        assert 'derived' in report
        assert 'convergence' in report
        assert 'hints' in report

    def test_untried_strategies(self):
        config = _coop_config()
        state = SweepState(
            store_map={},
            phase_history=[
                {'strategy': 'brand_variants', 'added': 0},
                {'strategy': 'solr_escape', 'added': 0},
            ],
        )
        report = state_report.build(config, state)
        untried = report['hints']['untried_strategies']
        assert 'brand_variants' not in untried
        assert 'solr_escape' not in untried
        assert 'parent_mst' in untried
        assert 'token_mining' in untried

    def test_convergence_reflected(self):
        config = _coop_config()
        state = SweepState(
            store_map={},
            phase_history=[
                {'strategy': 'a', 'added': 0},
                {'strategy': 'b', 'added': 0},
                {'strategy': 'c', 'added': 0},
            ],
        )
        report = state_report.build(config, state)
        assert report['convergence']['converged'] is True

    def test_write_creates_file(self, tmp_path):
        config = _coop_config()
        state = SweepState(store_map={}, phase_history=[])
        path = state_report.write(config, state, brands_dir=tmp_path)
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert 'total_records' in data
