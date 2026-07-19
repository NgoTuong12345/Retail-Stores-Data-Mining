"""Tests for the creative loop extension (run_loop --creative)."""
import pytest

from dkkd.config import BrandConfig
from dkkd.engine import DkkdEngine
from dkkd.loop import _provinces_from_records, CREATIVE_PLAYBOOK, run_creative_loop, run_loop
from dkkd.records import SweepState
from tests.conftest import FakeTransport


CREATIVE_NAMES = [name for name, _ in CREATIVE_PLAYBOOK]
CREATIVE_UNIQUE_TO_CREATIVE_LOOP = set(CREATIVE_NAMES) - {'solr_escape'}


def _coop_config():
    return BrandConfig(
        slug='coop-food', name='Co.op Food',
        brand_regex=r'CO[\.\\\,\-]?\s*OP\s*FOOD|COOPFOOD',
        spelling_variants=['CO.OP FOOD'],
        seed_parent_msts=['0309129418'],
    )


def _write_config(brands_dir):
    """Write a minimal coop-food config.yaml."""
    bd = brands_dir / 'coop-food'
    bd.mkdir(parents=True, exist_ok=True)
    (bd / 'config.yaml').write_text(
        "slug: coop-food\n"
        "name: Co.op Food\n"
        "brand_regex: 'CO[\\.\\\\,\\-]?\\s*OP\\s*FOOD|COOPFOOD'\n"
        "spelling_variants:\n"
        "  - 'CO.OP FOOD'\n"
        "seed_parent_msts:\n"
        "  - '0309129418'\n",
        encoding='utf-8',
    )


class TestProvincesFromRecords:
    def test_returns_last_comma_token_from_address(self):
        state = SweepState(store_map={
            '1': {'Ho_Address': '123 Nguyen Trai, Quan 1, TP. HCM'},
        }, phase_history=[])
        assert _provinces_from_records(state) == ['TP. HCM']

    def test_deduplicates_same_province(self):
        state = SweepState(store_map={
            '1': {'Ho_Address': '123 A, TP. HCM'},
            '2': {'Ho_Address': '456 B, TP. HCM'},
        }, phase_history=[])
        assert _provinces_from_records(state) == ['TP. HCM']

    def test_handles_missing_ho_address_key(self):
        state = SweepState(store_map={'1': {}}, phase_history=[])
        assert _provinces_from_records(state) == []

    def test_handles_none_ho_address(self):
        state = SweepState(store_map={'1': {'Ho_Address': None}}, phase_history=[])
        assert _provinces_from_records(state) == []

    def test_handles_empty_ho_address(self):
        state = SweepState(store_map={'1': {'Ho_Address': ''}}, phase_history=[])
        assert _provinces_from_records(state) == []

    def test_returns_sorted_list(self):
        state = SweepState(store_map={
            '1': {'Ho_Address': '123, Hà Nội'},
            '2': {'Ho_Address': '456, Bình Dương'},
            '3': {'Ho_Address': '789, An Giang'},
        }, phase_history=[])
        assert _provinces_from_records(state) == ['An Giang', 'Bình Dương', 'Hà Nội']

    def test_empty_store_map_returns_empty_list(self):
        state = SweepState(store_map={}, phase_history=[])
        assert _provinces_from_records(state) == []


class TestCreativePlaybookParams:
    def _state(self, store_map=None):
        return SweepState(store_map=store_map or {}, phase_history=[])

    def _param_fn(self, strategy_name):
        return next(fn for name, fn in CREATIVE_PLAYBOOK if name == strategy_name)

    def test_creative_playbook_order(self):
        assert CREATIVE_NAMES == [
            'corporate_sweep', 'compound', 'gdt_bare',
            'token_mining', 'hierarchy_walk', 'solr_escape',
        ]

    def test_token_mining_params_are_empty(self):
        assert self._param_fn('token_mining')(self._state()) == {}

    def test_compound_amplifiers_populated_from_record_addresses(self):
        state = self._state(store_map={
            '1': {'Ho_Address': '123 Abc, TP. HCM'},
            '2': {'Ho_Address': '456 Def, Bình Dương'},
        })
        params = self._param_fn('compound')(state)
        assert 'amplifiers' in params
        assert 'TP. HCM' in params['amplifiers']
        assert 'Bình Dương' in params['amplifiers']

    def test_gdt_bare_cap_scales_with_max_counter_seq(self):
        state = self._state(store_map={
            '1': {'Enterprise_Gdt_Code': '00080'},
        })
        assert self._param_fn('gdt_bare')(state) == {'cap': 160}

    def test_gdt_bare_cap_floor_enforced_at_100(self):
        state = self._state()
        assert self._param_fn('gdt_bare')(state) == {'cap': 100}


class TestRunCreativeLoop:
    def test_all_creative_strategies_run_in_order(self, tmp_path):
        config = _coop_config()
        engine = DkkdEngine(config, FakeTransport({}), brands_dir=tmp_path, throttle=False)
        state = SweepState(store_map={}, phase_history=[])

        result = run_creative_loop(state, config, engine, 'coop-food', tmp_path)

        assert [p['strategy'] for p in result.phase_history] == CREATIVE_NAMES

    def test_each_phase_has_required_fields(self, tmp_path):
        config = _coop_config()
        engine = DkkdEngine(config, FakeTransport({}), brands_dir=tmp_path, throttle=False)
        state = SweepState(store_map={}, phase_history=[])

        result = run_creative_loop(state, config, engine, 'coop-food', tmp_path)

        for phase in result.phase_history:
            assert {'strategy', 'params', 'probes', 'added', 'total'} <= phase.keys()

    def test_convergence_only_after_all_creative_phases_run(self, tmp_path):
        config = _coop_config()
        engine = DkkdEngine(config, FakeTransport({}), brands_dir=tmp_path, throttle=False)
        # Two trailing zeros already in history — one more in creative shouldn't stop early
        phase_history = [
            {'strategy': 'brand_variants', 'params': {}, 'probes': 10, 'added': 5, 'total': 5},
            {'strategy': 'solr_escape', 'params': {}, 'probes': 5, 'added': 0, 'total': 5},
            {'strategy': 'solr_escape', 'params': {}, 'probes': 50, 'added': 0, 'total': 5},
        ]
        state = SweepState(store_map={}, phase_history=phase_history)

        result = run_creative_loop(state, config, engine, 'coop-food', tmp_path)

        creative = result.phase_history[-len(CREATIVE_PLAYBOOK):]
        # All creative strategies must run at least once before convergence can stop the loop
        assert len(creative) == len(CREATIVE_PLAYBOOK)
        assert [p['strategy'] for p in creative] == CREATIVE_NAMES


class TestRunLoopCreativeFlag:
    def test_creative_false_does_not_run_creative_strategies(self, tmp_path):
        _write_config(tmp_path)
        state = run_loop('coop-food', transport=FakeTransport({}),
                         brands_dir=tmp_path, throttle=False, creative=False)
        assert not {p['strategy'] for p in state.phase_history} & CREATIVE_UNIQUE_TO_CREATIVE_LOOP

    def test_creative_true_appends_creative_strategies_after_playbook(self, tmp_path):
        _write_config(tmp_path)
        state = run_loop('coop-food', transport=FakeTransport({}),
                         brands_dir=tmp_path, throttle=False, creative=True)
        assert {p['strategy'] for p in state.phase_history} & CREATIVE_UNIQUE_TO_CREATIVE_LOOP

    def test_default_kwarg_behaves_like_creative_false(self, tmp_path):
        _write_config(tmp_path)
        state = run_loop('coop-food', transport=FakeTransport({}),
                         brands_dir=tmp_path, throttle=False)
        assert not {p['strategy'] for p in state.phase_history} & CREATIVE_UNIQUE_TO_CREATIVE_LOOP
