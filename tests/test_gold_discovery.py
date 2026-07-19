from dkkd.sectors.gold.discovery import gold_discovery
from dkkd.config import BrandConfig
from dkkd.records import SweepState

def _dummy_config() -> BrandConfig:
    return BrandConfig(
        slug='_gold_discovery',
        name='Gold Discovery',
        brand_regex='.*',
        spelling_variants=[],
        seed_parent_msts=[],
    )

def test_gold_discovery_returns_probes():
    config = _dummy_config()
    state = SweepState(store_map={}, phase_history=[])
    probes = gold_discovery(config, state, {})
    assert len(probes) > 0

def test_gold_discovery_probe_count():
    config = _dummy_config()
    state = SweepState(store_map={}, phase_history=[])
    probes = gold_discovery(config, state, {})
    # Since we added spelling variants, the count is higher than 536.
    # It is exactly 1397 probes due to deduplication when accented == plain.
    assert len(probes) == 1397

def test_gold_discovery_no_duplicate_probes():
    config = _dummy_config()
    state = SweepState(store_map={}, phase_history=[])
    probes = gold_discovery(config, state, {})
    fields = [p.search_field for p in probes]
    assert len(fields) == len(set(fields))

def test_gold_discovery_bare_keywords_present():
    config = _dummy_config()
    state = SweepState(store_map={}, phase_history=[])
    probes = gold_discovery(config, state, {})
    fields = {p.search_field for p in probes}
    assert 'VÀNG' in fields
    assert 'VANG' in fields
    assert 'KIM HOÀN' in fields
