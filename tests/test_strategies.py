"""Tests for all strategy functions (Tasks 7-11)."""
import pytest
from dkkd.config import BrandConfig
from dkkd.records import SweepState
from dkkd.strategies import REGISTRY, get, list_names
from dkkd.strategies.base import Probe


def _coop_config():
    return BrandConfig(
        slug='coop-food', name='Co.op Food',
        brand_regex=r'CO[\.\\\,\-]?\s*OP\s*FOOD|COOPFOOD',
        spelling_variants=['CO.OP FOOD', 'COOPFOOD', 'co.op food'],
        seed_parent_msts=['0309129418'],
    )


def _state(store=None, history=None):
    return SweepState(store_map=store or {}, phase_history=history or [])


def _state_with_records():
    store = {
        '1': {'Id': '1', 'Name': 'CO.OP FOOD 1', 'Enterprise_Gdt_Code': '00036'},
        '2': {'Id': '2', 'Name': 'CO.OP FOOD 2', 'Enterprise_Gdt_Code': '0309129418-005'},
        '3': {'Id': '3', 'Name': 'CO.OP FOOD NGUYEN', 'Enterprise_Gdt_Code': '0305767459-003'},
    }
    return SweepState(store_map=store)


# --- Task 7: brand_variants ---
class TestBrandVariants:
    def test_includes_known_variants(self):
        probes = get('brand_variants')(_coop_config(), _state(), {})
        fields = [p.search_field for p in probes]
        assert '+CO.OP +FOOD' in fields
        assert '+COOPFOOD' in fields

    def test_generates_separator_permutations(self):
        probes = get('brand_variants')(_coop_config(), _state(), {})
        fields_upper = [p.search_field.upper() for p in probes]
        # Should include CO.OPFOOD (the proven breakthrough)
        assert '+CO.OPFOOD' in fields_upper

    def test_deterministic_order(self):
        r1 = get('brand_variants')(_coop_config(), _state(), {})
        r2 = get('brand_variants')(_coop_config(), _state(), {})
        assert [p.search_field for p in r1] == [p.search_field for p in r2]

    def test_probes_are_probe_type(self):
        probes = get('brand_variants')(_coop_config(), _state(), {})
        for p in probes:
            assert isinstance(p, Probe)
            assert p.extra is None


# --- Task 8: solr_escape ---
class TestSolrEscape:
    def test_scout_emits_1_to_50(self):
        probes = get('solr_escape')(_coop_config(), _state(), {'phase': 'scout'})
        fields = [p.search_field for p in probes]
        assert fields[0] == '+CO.OP +FOOD +1'
        assert fields[1] == '+CO.OP +FOOD +00001'
        # 3 spelling variants * 50 * 2 = 300
        assert len(fields) == 300

    def test_full_computes_cap_from_state(self):
        store = {
            **{str(i): {'Id': str(i), 'Enterprise_Gdt_Code': f'{i:05d}'}
               for i in range(1, 612)},
            **{f'b{i}': {'Id': f'b{i}', 'Enterprise_Gdt_Code': f'0309129418-{i:03d}'}
               for i in range(1, 189)},
        }
        state = SweepState(store_map=store)
        probes = get('solr_escape')(_coop_config(), state, {'phase': 'full'})
        # cap = ceil(max(611, 188) * 1.2) = 734. 3 variants * 734 * 2 = 4404
        assert len(probes) >= 4400

    def test_default_is_scout(self):
        probes = get('solr_escape')(_coop_config(), _state(), {})
        assert len(probes) == 300


# --- Task 9: parent_mst ---
class TestParentMst:
    def test_unions_seed_and_discovered(self):
        config = _coop_config()
        state = _state_with_records()  # discovered_msts = {'0309129418', '0305767459'}
        probes = get('parent_mst')(config, state, {})
        fields = [p.search_field for p in probes]
        assert '0309129418' in fields
        assert '0305767459' in fields

    def test_emits_branch_probes(self):
        config = _coop_config()
        state = _state_with_records()
        probes = get('parent_mst')(config, state, {})
        fields = [p.search_field for p in probes]
        assert '+0309129418 +001' in fields
        assert '+0305767459 +001' in fields


# --- Task 10: token_mining, compound ---
class TestTokenMining:
    def test_emits_rare_tokens(self):
        probes = get('token_mining')(_coop_config(), _state_with_records(), {})
        assert len(probes) > 0

    def test_empty_store_no_probes(self):
        probes = get('token_mining')(_coop_config(), _state(), {})
        assert len(probes) == 0


class TestCompound:
    def test_compound_with_amplifiers(self):
        probes = get('compound')(_coop_config(), _state(), {'amplifiers': ['Nguyen', 'Tran']})
        fields = [p.search_field for p in probes]
        assert '+CO.OP +FOOD +Nguyen' in fields
        # 'co.op food' and 'CO.OP FOOD' collide when uppercased → 2 unique variants × 2 amps = 4
        assert len(fields) == 4

    def test_compound_deduplicates(self):
        probes = get('compound')(_coop_config(), _state(),
                                 {'amplifiers': ['Nguyen', 'nguyen']})
        # 'CO.OP FOOD Nguyen' / 'CO.OP FOOD nguyen' same upper key,
        # plus 'co.op food' collides with 'CO.OP FOOD' → 2 unique combos
        assert len(probes) == 2


class TestGdtBare:
    def test_default_cap_from_state(self):
        state = SweepState(store_map={'1': {'Id': '1', 'Enterprise_Gdt_Code': '00036'}})
        probes = get('gdt_bare')(_coop_config(), state, {})
        fields = [p.search_field for p in probes]
        assert fields[0] == '00001'
        assert fields[-1] == '00050'  # default min cap is 50
        assert len(fields) == 50

    def test_custom_cap(self):
        probes = get('gdt_bare')(_coop_config(), _state(), {'cap': 10})
        fields = [p.search_field for p in probes]
        assert fields[0] == '00001'
        assert fields[-1] == '00010'
        assert len(fields) == 10


class TestRaw:
    def test_splits_semicolons(self):
        probes = get('raw')(_coop_config(), _state(), {'probes': 'KW1;KW2;KW3'})
        fields = [p.search_field for p in probes]
        assert fields == ['KW1', 'KW2', 'KW3']

    def test_strips_whitespace(self):
        probes = get('raw')(_coop_config(), _state(), {'probes': ' KW1 ; KW2 '})
        fields = [p.search_field for p in probes]
        assert fields == ['KW1', 'KW2']

    def test_empty_probes_param(self):
        probes = get('raw')(_coop_config(), _state(), {'probes': ''})
        assert probes == []

    def test_missing_probes_param(self):
        probes = get('raw')(_coop_config(), _state(), {})
        assert probes == []

    def test_probes_have_no_extra(self):
        probes = get('raw')(_coop_config(), _state(), {'probes': 'HELLO'})
        assert probes[0].extra is None

    def test_single_probe(self):
        probes = get('raw')(_coop_config(), _state(), {'probes': 'CO.OP FOOD QUẬN TÂN BÌNH'})
        assert len(probes) == 1
        assert probes[0].search_field == 'CO.OP FOOD QUẬN TÂN BÌNH'


# --- Task 11: Registry ---
class TestRegistry:
    def test_all_strategies_registered(self):
        expected = {'brand_variants', 'solr_escape', 'parent_mst',
                    'token_mining', 'compound', 'gdt_bare',
                    'gold_discovery', 'raw', 'hierarchy_walk',
                    'corporate_sweep'}
        assert expected == set(REGISTRY.keys())

    def test_get_resolves(self):
        fn = get('brand_variants')
        assert callable(fn)

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get('nonexistent_strategy')

    def test_list_names_complete(self):
        names = list_names()
        assert 'raw' in names
        assert len(names) == 10
