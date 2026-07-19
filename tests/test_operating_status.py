"""TDD tests for dkkd.operating_status — write failing first, then implement."""
import pytest
from dkkd.config import BrandConfig
from dkkd.operating_status import resolve_operating_status
from tests.conftest import make_optin_config


def make_legacy_config() -> BrandConfig:
    return BrandConfig(
        slug='coop-food',
        name='Co.op Food',
        brand_regex='CO.OP FOOD',
        classification={},
    )


# --- Test 1: Format-A under active parent, no locator pin → Unverified ---

def test_format_a_no_pin_unverified():
    store = {
        'Id': '100', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00036', 'Enterprise_Code': '',
        'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status([store], config, locator_pins={}, gdt_cache={})
    assert store['Operating_Status'] == 'Unverified'
    assert store['Operating_Evidence'] == 'licensed-unverified'
    assert store['Core_Operating_Store'] == 'No'


# --- Test 2: Locator-pinned (Unique) → Operating ---

def test_locator_pinned_unique_operating():
    store = {
        'Id': '200', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00100', 'Enterprise_Code': '',
        'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status([store], config, locator_pins={200: 'Unique'}, gdt_cache={})
    assert store['Operating_Status'] == 'Operating'
    assert store['Operating_Evidence'] == 'locator:Unique'
    assert store['Core_Operating_Store'] == 'Yes'


# --- Test 3: Locator-pinned (Shared_Co-located) → Operating ---

def test_locator_pinned_shared_colocated_operating():
    store = {
        'Id': '300', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00200', 'Enterprise_Code': '',
        'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status([store], config, locator_pins={300: 'Shared_Co-located'}, gdt_cache={})
    assert store['Operating_Status'] == 'Operating'
    assert store['Operating_Evidence'] == 'locator:Shared_Co-located'
    assert store['Core_Operating_Store'] == 'Yes'


# --- Test 4: Status='Chấm dứt hoạt động' outranks locator pin → Closed ---

def test_status_ceased_outranks_locator_pin():
    store = {
        'Id': '400', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00300', 'Enterprise_Code': '',
        'Status': 'Chấm dứt hoạt động',
    }
    config = make_optin_config()
    resolve_operating_status([store], config, locator_pins={400: 'Unique'}, gdt_cache={})
    assert store['Operating_Status'] == 'Closed'
    assert store['Operating_Evidence'] == 'status-ceased'
    assert store['Core_Operating_Store'] == 'No'


# --- Test 5: Own-MST active (not in seed_parent_msts) → Operating / gdt-own-mst ---

def test_own_mst_active_gdt_operating():
    store = {
        'Id': '500', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '0100000001-001',
        'Enterprise_Code': '', 'Status': 'NNT đang hoạt động',
    }
    config = make_optin_config()  # seed_parent_msts = ['0306182043']
    resolve_operating_status(
        [store], config,
        locator_pins={},
        gdt_cache={'0100000001': {'status': 'NNT đang hoạt động'}},
    )
    assert store['Operating_Status'] == 'Operating'
    assert store['Operating_Evidence'] == 'gdt-own-mst'
    assert store['Core_Operating_Store'] == 'Yes'


# --- Test 6: Corporate name → Closed / corporate ---

def test_corporate_name_closed():
    store = {
        'Id': '600', 'Store_Brand_Format': 'Test Brand (Corporate/Logistics)',
        'Enterprise_Gdt_Code': '00001', 'Enterprise_Code': '',
        'Status': 'NNT đang hoạt động',
    }
    config = make_optin_config()
    resolve_operating_status([store], config, locator_pins={600: 'Unique'}, gdt_cache={})
    assert store['Operating_Status'] == 'Closed'
    assert store['Operating_Evidence'] == 'corporate'
    assert store['Core_Operating_Store'] == 'No'


# --- Test 7: Reconciliation identity — Operating + Closed + Unverified == total ---

def test_reconciliation_identity():
    stores = [
        {'Id': '1', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00001', 'Enterprise_Code': '', 'Status': None},   # Unverified
        {'Id': '2', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00002', 'Enterprise_Code': '', 'Status': None},   # Operating (pinned)
        {'Id': '3', 'Store_Brand_Format': 'Test Brand (Corporate/Logistics)', 'Enterprise_Gdt_Code': '00000', 'Enterprise_Code': '', 'Status': 'NNT đang hoạt động'},  # Closed (corporate)
        {'Id': '4', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '', 'Status': 'Chấm dứt hoạt động'},  # Closed (status-ceased)
        {'Id': '5', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00004', 'Enterprise_Code': '', 'Status': None},   # Unverified
    ]
    config = make_optin_config()
    resolve_operating_status(stores, config, locator_pins={2: 'Unique'}, gdt_cache={})
    operating = sum(1 for s in stores if s['Operating_Status'] == 'Operating')
    closed = sum(1 for s in stores if s['Operating_Status'] == 'Closed')
    unverified = sum(1 for s in stores if s['Operating_Status'] == 'Unverified')
    assert operating + closed + unverified == len(stores)


# --- Test 8: Invariant — Core_Operating_Store=='Yes' iff Operating_Status=='Operating' ---

def test_core_operating_store_invariant():
    stores = [
        {'Id': '1', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00001', 'Enterprise_Code': '', 'Status': None},
        {'Id': '2', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00002', 'Enterprise_Code': '', 'Status': None},
        {'Id': '3', 'Store_Brand_Format': 'Test Brand (Corporate/Logistics)', 'Enterprise_Gdt_Code': '00000', 'Enterprise_Code': '', 'Status': 'NNT đang hoạt động'},
        {'Id': '4', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '', 'Status': 'Chấm dứt hoạt động'},
        {'Id': '5', 'Store_Brand_Format': 'Test Brand', 'Enterprise_Gdt_Code': '00004', 'Enterprise_Code': '', 'Status': None},
    ]
    config = make_optin_config()
    resolve_operating_status(stores, config, locator_pins={2: 'Unique'}, gdt_cache={})
    for s in stores:
        if s['Operating_Status'] == 'Operating':
            assert s['Core_Operating_Store'] == 'Yes', f"Id={s['Id']} Operating but Core=No"
        else:
            assert s['Core_Operating_Store'] == 'No', f"Id={s['Id']} {s['Operating_Status']} but Core=Yes"


# --- Test 9: Backward-compat — non-opt-in brand keeps exact counts, no Unverified ---

def test_legacy_brand_backward_compat():
    stores = [
        {'Id': '10', 'Store_Brand_Format': 'Co.op Food', 'Enterprise_Gdt_Code': '00001', 'Enterprise_Code': '', 'Status': 'NNT đang hoạt động', 'Core_Operating_Store': 'Yes'},
        {'Id': '11', 'Store_Brand_Format': 'Co.op Food', 'Enterprise_Gdt_Code': '00002', 'Enterprise_Code': '', 'Status': 'NNT đang hoạt động', 'Core_Operating_Store': 'Yes'},
        {'Id': '12', 'Store_Brand_Format': 'Co.op Food (Legacy/Closed)', 'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '', 'Status': 'Chấm dứt hoạt động', 'Core_Operating_Store': 'No'},
    ]
    config = make_legacy_config()
    resolve_operating_status(stores, config)  # no locator_pins, no gdt_cache
    # Core_Operating_Store must not change
    assert stores[0]['Core_Operating_Store'] == 'Yes'
    assert stores[1]['Core_Operating_Store'] == 'Yes'
    assert stores[2]['Core_Operating_Store'] == 'No'
    # New columns are set using legacy-classify
    assert stores[0]['Operating_Status'] == 'Operating'
    assert stores[0]['Operating_Evidence'] == 'legacy-classify'
    assert stores[2]['Operating_Status'] == 'Closed'
    assert stores[2]['Operating_Evidence'] == 'legacy-classify'
    # No Unverified records for non-opt-in brand
    assert all(s['Operating_Status'] != 'Unverified' for s in stores)
