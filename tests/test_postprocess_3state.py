"""TDD tests for 3-state resolver wired into postprocess.run_pipeline.

Test 1: opt-in brand — Format-A record under active parent gets Unverified
  (Stage 2 suppression blocks parent-status inheritance; no locator pin)

Test 2: non-opt-in brand — no Unverified records, core counts match expected
"""
import pytest
from unittest.mock import patch, MagicMock
from dkkd.postprocess import run_pipeline
from dkkd.config import BrandConfig


# ── Shared fixtures ────────────────────────────────────────────────────────────

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


def _make_legacy_config():
    return BrandConfig(
        slug='test-legacy',
        name='Test Legacy',
        brand_regex='Test Legacy',
        classification={
            'corporate_keywords': [],
        },
        seed_parent_msts=[],
    )


# ── Test 1: opt-in brand — Format-A → Unverified (Stage 2 suppression) ────────

@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_optin_format_a_no_pin_is_unverified(
    mock_pins, mock_cache, mock_load, mock_cfg, tmp_path
):
    """Format-A record (00036) under active parent gets Unverified, not Operating.

    - opt_in=True suppresses parent-status inheritance in Stage 2 → Status=None
    - No locator pins → resolver places record at Rung 5 (Unverified)
    - Core_Operating_Store must be 'No'
    - _unverified.csv must be created in output dir
    """
    mock_cfg.return_value = _make_optin_config()
    # One Format-A record whose parent is active in gdt cache
    mock_load.return_value = [
        {
            'Id': '1001',
            'Enterprise_Gdt_Code': '00036',
            'Enterprise_Code': '',
            'Name': 'Test Brand Store 1',
            'Name_F': 'TEST BRAND STORE 1',
        }
    ]
    # Parent MST is active
    mock_cache.return_value = {
        '0306182043': {'status': 'NNT đang hoạt động'}
    }
    # No locator pins → file missing, function returns {}
    mock_pins.return_value = {}

    # Ensure output directory exists
    out_dir = tmp_path / 'test-brand' / 'output'
    out_dir.mkdir(parents=True)

    summary = run_pipeline(
        'test-brand',
        brands_dir=tmp_path,
        skip_date_calibration=True,
    )

    stores = mock_load.return_value
    assert stores[0]['Operating_Status'] == 'Unverified', (
        f"Expected Unverified, got {stores[0].get('Operating_Status')}"
    )
    assert stores[0]['Core_Operating_Store'] == 'No', (
        f"Expected No, got {stores[0].get('Core_Operating_Store')}"
    )

    # unverified.csv must exist (backtest.py reads this directly)
    unverified_path = out_dir / 'test-brand_unverified.csv'
    assert unverified_path.exists(), "Expected _unverified.csv to be created"

    # standard_schema.csv is the analyst-facing deliverable — replaces the
    # old core_operating/non_operating split CSVs
    schema_path = out_dir / 'test-brand_standard_schema.csv'
    assert schema_path.exists(), "Expected standard_schema.csv to be created"
    assert not (out_dir / 'test-brand_core_operating.csv').exists()
    assert not (out_dir / 'test-brand_non_operating.csv').exists()

    # summary must include the unverified key
    assert 'unverified' in summary
    assert summary['unverified'] == 1


# ── Test 2: non-opt-in brand — no Unverified records, core counts correct ──────

@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_legacy_brand_no_unverified(
    mock_pins, mock_cache, mock_load, mock_cfg, tmp_path
):
    """Non-opt-in brand produces zero Unverified records.

    - opt_in=False → resolver uses _resolve_legacy (reads Core_Operating_Store)
    - Core_Operating_Store counts must survive the pipeline unchanged
    - _unverified.csv is still written (empty file)
    """
    mock_cfg.return_value = _make_legacy_config()
    mock_load.return_value = [
        {
            'Id': '2001',
            'Enterprise_Gdt_Code': '0300000001-001',
            'Enterprise_Code': '',
            'Name': 'Test Legacy Active',
            'Name_F': 'TEST LEGACY ACTIVE',
        },
        {
            'Id': '2002',
            'Enterprise_Gdt_Code': '0300000002-001',
            'Enterprise_Code': '',
            'Name': 'Test Legacy Closed',
            'Name_F': 'TEST LEGACY CLOSED',
        },
    ]
    mock_cache.return_value = {
        '0300000001': {'status': 'NNT đang hoạt động'},
        '0300000002': {'status': 'Chấm dứt hoạt động'},
    }
    mock_pins.return_value = {}

    out_dir = tmp_path / 'test-legacy' / 'output'
    out_dir.mkdir(parents=True)

    summary = run_pipeline(
        'test-legacy',
        brands_dir=tmp_path,
        skip_date_calibration=True,
    )

    stores = mock_load.return_value
    # No record may be Unverified for a non-opt-in brand
    statuses = [s.get('Operating_Status') for s in stores]
    assert 'Unverified' not in statuses, (
        f"Non-opt-in brand must not produce Unverified; got {statuses}"
    )

    # Summary must include the three-state keys
    assert 'unverified' in summary
    assert summary['unverified'] == 0
