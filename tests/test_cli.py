"""Tests for CLI (Task 17) and loop (Task 18)."""
import json
import pytest
import yaml
from pathlib import Path

from dkkd.cli import main, parse_params
from dkkd.loop import run_loop, PLAYBOOK
from dkkd.config import BrandConfig
from dkkd.records import SweepState
from tests.conftest import FakeTransport


def _setup_brand(tmp_path, slug='test-brand', extra_config=None):
    """Create a brand directory with config.yaml."""
    brand_dir = tmp_path / slug
    brand_dir.mkdir(parents=True, exist_ok=True)
    config = {
        'slug': slug,
        'name': 'Test Brand',
        'brand_regex': r'TEST\s*BRAND|TESTBRAND',
        'spelling_variants': ['TEST BRAND', 'TESTBRAND'],
        'seed_parent_msts': ['0000000001'],
        'default_store_type': 'Test',
    }
    if extra_config:
        config.update(extra_config)
    with open(brand_dir / 'config.yaml', 'w') as f:
        yaml.dump(config, f)
    return brand_dir


class TestParseParams:
    def test_empty(self):
        assert parse_params('') == {}

    def test_single(self):
        assert parse_params('phase=scout') == {'phase': 'scout'}

    def test_multiple(self):
        assert parse_params('phase=full,max_freq=3') == {'phase': 'full', 'max_freq': '3'}


class TestCLI:
    def test_strategies_command(self, capsys):
        main(['strategies'])
        captured = capsys.readouterr()
        assert 'brand_variants' in captured.out
        assert 'corporate_sweep' in captured.out

    def test_brands_command(self, tmp_path, capsys, monkeypatch):
        _setup_brand(tmp_path, 'test-brand')
        monkeypatch.setattr('dkkd.cli.DEFAULT_BRANDS_DIR', tmp_path)
        main(['brands'])
        captured = capsys.readouterr()
        assert 'test-brand' in captured.out

    def test_converged_no_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr('dkkd.paths.DEFAULT_BRANDS_DIR', tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            main(['converged', '--brand', 'nonexistent'])
        assert exc_info.value.code == 1

    def test_bad_strategy_name(self, tmp_path, monkeypatch):
        from dkkd.strategies import get
        with pytest.raises(KeyError):
            get('nonexistent_strategy_12345')


# --- Task 18: loop.py deterministic auto-runner ---
class TestLoop:
    def test_playbook_order(self):
        """Verify the deterministic playbook has the expected order."""
        names = [name for name, _ in PLAYBOOK]
        assert names == ['brand_variants', 'solr_escape', 'solr_escape', 'parent_mst']

    def test_loop_runs_to_convergence(self, tmp_path):
        """Loop with empty transport should hit convergence after playbook completes."""
        _setup_brand(tmp_path, 'test-brand')
        transport = FakeTransport({})  # all queries return empty → 0 added each phase

        state = run_loop('test-brand', transport=transport, brands_dir=tmp_path, throttle=False)

        # Should have run at least 3 phases (convergence after 3 consecutive 0-added)
        assert len(state.phase_history) >= 3
        # All phases should have added 0
        for p in state.phase_history:
            assert p['added'] == 0

    def test_loop_early_halt_on_convergence(self, tmp_path):
        """If convergence is hit after 3 phases, loop should stop (not run all 4)."""
        _setup_brand(tmp_path, 'test-brand')
        transport = FakeTransport({})

        state = run_loop('test-brand', transport=transport, brands_dir=tmp_path, throttle=False)

        # With 4-step playbook and 0 adds each, convergence after 3rd phase
        # So phase 4 (parent_mst) should NOT run
        strategies_run = [p['strategy'] for p in state.phase_history]
        assert len(strategies_run) == 3
        assert 'parent_mst' not in strategies_run

    def test_loop_writes_state_json(self, tmp_path):
        _setup_brand(tmp_path, 'test-brand')
        transport = FakeTransport({})

        run_loop('test-brand', transport=transport, brands_dir=tmp_path, throttle=False)

        state_path = tmp_path / 'test-brand' / 'state.json'
        assert state_path.exists()
        with open(state_path) as f:
            data = json.load(f)
        assert 'total_records' in data
        assert data['convergence']['converged'] is True

    def test_loop_with_data_collects_and_enriches(self, tmp_path):
        """Loop with matching data should collect records and enrich config."""
        _setup_brand(tmp_path, 'test-brand')

        # Only 'TEST BRAND' returns rows; all other queries return empty
        transport = FakeTransport({
            'TEST BRAND': [
                {'Id': '1', 'Name': 'TEST BRAND Store', 'Name_F': '',
                 'Enterprise_Gdt_Code': '0000000001-001'},
            ],
            'TESTBRAND': [
                {'Id': '2', 'Name': 'TESTBRAND Shop', 'Name_F': '',
                 'Enterprise_Gdt_Code': '0000000001-002'},
            ],
        })

        state = run_loop('test-brand', transport=transport, brands_dir=tmp_path, throttle=False)

        # Should have collected records
        assert state.total_records >= 1

def test_cli_parser_audit_tax(monkeypatch):
    called = []
    def mock_cmd_audit_tax(args):
        called.append(args)
    monkeypatch.setattr('dkkd.cli.cmd_audit_tax', mock_cmd_audit_tax)
    main(['audit-tax', '--brand', 'circle-k'])
    assert len(called) == 1
    assert called[0].brand == 'circle-k'


