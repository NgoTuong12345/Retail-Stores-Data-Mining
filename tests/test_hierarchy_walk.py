"""TDD tests for hierarchy_walk strategy.

Tests are written BEFORE implementation (Step 1 gate: all must fail on import).
Run with: pytest tests/test_hierarchy_walk.py -v
"""
import math
import re
from pathlib import Path

import pytest

from dkkd.config import BrandConfig, load as load_cfg
from dkkd.records import SweepState
from dkkd.strategies.base import Probe
from dkkd.strategies.hierarchy_walk import hierarchy_walk, _per_parent_max


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(seed_msts=None):
    """Minimal BrandConfig for unit tests."""
    return BrandConfig(
        slug='test', name='Test Brand',
        brand_regex=r'TEST',
        seed_parent_msts=seed_msts or [],
    )


def b_rec(mst: str, seq: int) -> dict:
    """Format B record: Enterprise_Gdt_Code = MST-NNN."""
    return {'Enterprise_Gdt_Code': f'{mst}-{seq:03d}', 'Id': f'{mst}-{seq}'}


def a_rec(counter: int) -> dict:
    """Format A record: Enterprise_Gdt_Code = 5-digit counter."""
    return {'Enterprise_Gdt_Code': f'{counter:05d}', 'Id': str(counter)}


def fields(probes: list[Probe]) -> list[str]:
    """Extract search_field strings from a probe list."""
    return [p.search_field for p in probes]


def all_brand_slugs() -> list[str]:
    """Discover all configured brand slugs by scanning brands/ for config.yaml files."""
    brands_dir = Path(__file__).resolve().parent.parent / 'brands'
    if not brands_dir.exists():
        return []
    return [p.parent.name for p in sorted(brands_dir.rglob('config.yaml'))]


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_no_format_b_in_state_uses_config_seeds():
    """Empty store_map → probes config seed_parent_msts only."""
    cfg = make_config(['1234567890'])
    state = SweepState(store_map={})
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)
    assert '1234567890' in f
    assert any(x.startswith('+1234567890 ') for x in f)


def test_per_parent_cap_above_global_max():
    """Core bug fix: per-parent cap, not global max.

    Old parent_mst: global max = 146, cap = ceil(146 * 1.2) = 176 → both parents capped at 176.
    hierarchy_walk: parent A cap = ceil(146 * 1.5) = 219; parent B cap = 200 (floor).
    """
    records = {
        '1': b_rec('1111111111', 146),   # parent A: max branch seq 146
        '2': b_rec('2222222222', 5),     # parent B: max branch seq 5
    }
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)

    a_branches = [x for x in f if x.startswith('+1111111111 ')]
    b_branches = [x for x in f if x.startswith('+2222222222 ')]

    expected_a_cap = int(math.ceil(146 * 1.5))   # 219
    assert len(a_branches) == expected_a_cap, (
        f"Parent A: expected {expected_a_cap} branches, got {len(a_branches)}"
    )
    assert len(b_branches) == 200, (
        f"Parent B: expected 200 (floor), got {len(b_branches)}"
    )


def test_discovers_msts_from_format_b_records():
    """Two distinct Format B parents → both appear in probe list."""
    records = {
        '1': b_rec('1111111111', 10),
        '2': b_rec('2222222222', 20),
    }
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)
    assert '1111111111' in f
    assert '2222222222' in f


def test_min_branch_cap_floor():
    """Single-branch parent must still get 200 probes (the floor)."""
    records = {'1': b_rec('9999999999', 1)}
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    branches = [x for x in fields(result) if x.startswith('+9999999999 ')]
    assert len(branches) == 200, f"Expected 200 (floor), got {len(branches)}"


def test_no_duplicate_probes():
    """Config MST that also appears in state Format B records must not duplicate."""
    records = {'1': b_rec('1234567890', 50)}
    cfg = make_config(['1234567890'])
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)
    assert f.count('1234567890') == 1, "Bare MST probe must appear exactly once"


def test_bare_mst_included():
    """Each parent MST must appear as a bare (non-suffixed) probe."""
    records = {'1': b_rec('5555555555', 10)}
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    assert '5555555555' in fields(result)


def test_format_a_records_not_extracted_as_msts():
    """Format A records (5-digit counter) must NOT be treated as parent MSTs."""
    records = {
        '1': a_rec(279),
        '2': a_rec(42),
    }
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)
    # No 10-digit MST-style probes should appear (config empty, no Format B records)
    mst_like = [x for x in f if re.match(r'^\d{10}$', x)]
    assert not mst_like, f"Format A records leaked as parent MSTs: {mst_like}"


def test_probe_ordering():
    """Probes must be deterministic: MSTs sorted lexicographically, then bare, then 001..cap."""
    records = {
        '1': b_rec('2000000000', 5),   # higher lex
        '2': b_rec('1000000000', 5),   # lower lex
    }
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)

    a_idx = f.index('1000000000')   # lower → should come first
    b_idx = f.index('2000000000')   # higher → should come second
    assert a_idx < b_idx, "MSTs must be sorted lexicographically"
    assert f[a_idx + 1] == '+1000000000 +001', "Bare MST must immediately precede branch-001"


def test_playbook_swap():
    """CREATIVE_PLAYBOOK must contain hierarchy_walk after the swap."""
    # Import loop after strategy is registered to avoid import-order issues
    import dkkd.loop  # noqa: F401
    from dkkd.loop import CREATIVE_PLAYBOOK
    strategy_names = [name for name, _ in CREATIVE_PLAYBOOK]
    assert 'hierarchy_walk' in strategy_names, (
        f"hierarchy_walk not found in CREATIVE_PLAYBOOK. Got: {strategy_names}"
    )


def test_custom_min_branch_cap_via_params():
    """min_branch_cap param overrides the 200 default."""
    records = {'1': b_rec('7777777777', 1)}
    cfg = make_config()
    state = SweepState(store_map=records)
    result = hierarchy_walk(cfg, state, {'min_branch_cap': 50})
    branches = [x for x in fields(result) if x.startswith('+7777777777 ')]
    # seq=1, cap = max(ceil(1*1.5), 50) = max(2, 50) = 50
    assert len(branches) == 50, f"Expected 50 (custom floor), got {len(branches)}"


# ---------------------------------------------------------------------------
# Parametrized cross-brand tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('brand_slug', all_brand_slugs())
def test_all_brands_config_seeds_probed(brand_slug):
    """For every configured brand, all seed_parent_msts appear in hierarchy_walk probes."""
    cfg = load_cfg(brand_slug)
    if not cfg.all_parent_msts:
        pytest.skip(f"{brand_slug}: no seed_parent_msts configured")
    state = SweepState(store_map={})
    result = hierarchy_walk(cfg, state, {})
    f = fields(result)
    for mst in cfg.all_parent_msts:
        assert mst in f, f"{brand_slug}: seed MST {mst!r} not in probe list"
