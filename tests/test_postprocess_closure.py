"""TDD test proving postprocess.run_pipeline wires closure_signals end-to-end."""
from unittest.mock import patch
from dkkd.postprocess import run_pipeline
from dkkd.config import BrandConfig


def _make_optin_config():
    return BrandConfig(
        slug='test-brand',
        name='Test Brand',
        brand_regex='Test Brand',
        classification={
            'operating_status': {'enabled': True},
            'corporate_keywords': [],
        },
        seed_parent_msts=['0306182043'],
    )


def _make_optin_config_with_structural_signals():
    return BrandConfig(
        slug='test-brand',
        name='Test Brand',
        brand_regex='Test Brand',
        classification={
            'operating_status': {'enabled': True, 'structural_signals_enabled': True},
            'corporate_keywords': [],
        },
        seed_parent_msts=['0306182043'],
    )


@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_closure_signals_propagate_across_sibling_branches(
    mock_pins, mock_cache, mock_load, mock_cfg, tmp_path
):
    """Record 1002 has no status/locator evidence of its own, but shares a parent
    MST with 1001 (which has its own ceased GDT status) — structural propagation
    must close 1002 too, proving postprocess wires build_closure_signal_map()
    into resolve_operating_status() before the resolver runs. Uses a non-seed
    MST ('9999999999'), distinct from the brand's seed_parent_msts
    ('0306182043'), since seed parent MSTs are excluded from dissolution
    propagation (measured 47.6% precision on the shared-corporate-MST case)."""
    mock_cfg.return_value = _make_optin_config_with_structural_signals()
    mock_load.return_value = [
        {
            'Id': '1001', 'Enterprise_Gdt_Code': '9999999999-001', 'Enterprise_Code': '',
            'Name': 'Test Brand Store 1', 'Name_F': 'TEST BRAND STORE 1',
            'Ho_Address': '1 Main St, Q1, TP.HCM',
        },
        {
            'Id': '1002', 'Enterprise_Gdt_Code': '9999999999-002', 'Enterprise_Code': '',
            'Name': 'Test Brand Store 2', 'Name_F': 'TEST BRAND STORE 2',
            'Ho_Address': '2 Other St, Q1, TP.HCM',
        },
    ]
    # Only 1001's own branch code has a ceased status in the GDT cache — 1002 has none.
    mock_cache.return_value = {
        '9999999999-001': {'status': 'Chấm dứt hoạt động'},
    }
    mock_pins.return_value = {}

    out_dir = tmp_path / 'test-brand' / 'output'
    out_dir.mkdir(parents=True)

    run_pipeline('test-brand', brands_dir=tmp_path, skip_date_calibration=True)

    stores = mock_load.return_value
    by_id = {s['Id']: s for s in stores}
    assert by_id['1001']['Operating_Status'] == 'Closed'
    assert by_id['1002']['Operating_Status'] == 'Closed', (
        f"Expected sibling branch to inherit parent-dissolution signal, "
        f"got {by_id['1002'].get('Operating_Status')}"
    )
    assert by_id['1002']['Operating_Evidence'] == 'structural:parent-dissolved'
    assert by_id['1002']['Core_Operating_Store'] == 'No'


@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_structural_signals_disabled_by_default_does_not_flip_locator_confirmed_store(
    mock_pins, mock_cache, mock_load, mock_cfg, tmp_path
):
    """Regression guard: with structural_signals_enabled unset (default off), a
    locator-confirmed, own-status-active store must NOT be flipped to Closed by
    a sibling branch's own ceased status under the same shared parent MST.
    This is the false-positive the final whole-branch review found live on
    Circle K data (a branch closing wrongly propagated to locator-confirmed
    open stores sharing the corporate MST)."""
    mock_cfg.return_value = _make_optin_config()  # structural_signals_enabled unset/off
    mock_load.return_value = [
        {
            'Id': '1001', 'Enterprise_Gdt_Code': '0306182043-001', 'Enterprise_Code': '',
            'Name': 'Test Brand Store 1', 'Name_F': 'TEST BRAND STORE 1',
            'Ho_Address': '1 Main St, Q1, TP.HCM',
        },
        {
            'Id': '1002', 'Enterprise_Gdt_Code': '0306182043-002', 'Enterprise_Code': '',
            'Name': 'Test Brand Store 2', 'Name_F': 'TEST BRAND STORE 2',
            'Ho_Address': '2 Other St, Q1, TP.HCM',
        },
    ]
    # 1001's own branch code has ceased status; 1002's own branch code is active.
    mock_cache.return_value = {
        '0306182043-001': {'status': 'Chấm dứt hoạt động'},
        '0306182043-002': {'status': 'NNT đang hoạt động'},
    }
    # 1002 is confirmed open by the brand's own store locator.
    mock_pins.return_value = {1002: 'Unique'}

    out_dir = tmp_path / 'test-brand' / 'output'
    out_dir.mkdir(parents=True)

    run_pipeline('test-brand', brands_dir=tmp_path, skip_date_calibration=True)

    stores = mock_load.return_value
    by_id = {s['Id']: s for s in stores}
    assert by_id['1002']['Operating_Status'] == 'Operating', (
        f"Locator-confirmed active store must not be flipped by a sibling's "
        f"ceased status when structural_signals_enabled is off, "
        f"got {by_id['1002'].get('Operating_Status')}"
    )
    assert by_id['1002']['Operating_Evidence'] == 'locator:Unique'


@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_seed_parent_mst_excluded_even_with_structural_signals_enabled(
    mock_pins, mock_cache, mock_load, mock_cfg, tmp_path
):
    """Even with structural_signals_enabled=True, a sibling sharing the brand's
    own seed_parent_mst must NOT be closed by another sibling's ceased status —
    measured 47.6% precision (10/21) on real Circle K data for exactly this
    shared-corporate-MST pattern. Non-seed MSTs still propagate normally (see
    test_closure_signals_propagate_across_sibling_branches)."""
    mock_cfg.return_value = _make_optin_config_with_structural_signals()  # seed_parent_msts=['0306182043']
    mock_load.return_value = [
        {
            'Id': '1001', 'Enterprise_Gdt_Code': '0306182043-001', 'Enterprise_Code': '',
            'Name': 'Test Brand Store 1', 'Name_F': 'TEST BRAND STORE 1',
            'Ho_Address': '1 Main St, Q1, TP.HCM',
        },
        {
            'Id': '1002', 'Enterprise_Gdt_Code': '0306182043-002', 'Enterprise_Code': '',
            'Name': 'Test Brand Store 2', 'Name_F': 'TEST BRAND STORE 2',
            'Ho_Address': '2 Other St, Q1, TP.HCM',
        },
    ]
    mock_cache.return_value = {
        '0306182043-001': {'status': 'Chấm dứt hoạt động'},
    }
    mock_pins.return_value = {}  # no locator pin — isolates the seed-MST exclusion itself

    out_dir = tmp_path / 'test-brand' / 'output'
    out_dir.mkdir(parents=True)

    run_pipeline('test-brand', brands_dir=tmp_path, skip_date_calibration=True)

    stores = mock_load.return_value
    by_id = {s['Id']: s for s in stores}
    assert by_id['1002']['Operating_Status'] != 'Closed', (
        f"Sibling under the brand's own seed_parent_mst must not be closed by "
        f"another sibling's ceased status, got {by_id['1002'].get('Operating_Status')}"
    )
    assert by_id['1002']['Operating_Evidence'] != 'structural:parent-dissolved'
