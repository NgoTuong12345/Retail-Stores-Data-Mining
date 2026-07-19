"""TDD tests for closure_signals wiring into dkkd.operating_status — write failing first."""
from dkkd.config import BrandConfig
from dkkd.operating_status import resolve_operating_status
from tests.conftest import make_optin_config


# --- Rung 2 (NEW): parent-dissolution signal ---

def test_parent_dissolved_signal_closes_record():
    store = {
        'Id': '100', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00036', 'Enterprise_Code': '', 'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status(
        [store], config, locator_pins={}, gdt_cache={},
        closure_signals={100: {'signal': 'parent_dissolved'}},
    )
    assert store['Operating_Status'] == 'Closed'
    assert store['Operating_Evidence'] == 'structural:parent-dissolved'
    assert store['Core_Operating_Store'] == 'No'


def test_parent_dissolution_outranks_locator_pin():
    store = {
        'Id': '100', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00036', 'Enterprise_Code': '', 'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status(
        [store], config, locator_pins={100: 'Unique'}, gdt_cache={},
        closure_signals={100: {'signal': 'parent_dissolved'}},
    )
    assert store['Operating_Status'] == 'Closed'
    assert store['Operating_Evidence'] == 'structural:parent-dissolved'


# --- Rung 5 (NEW): address-supersession signal ---

def test_superseded_signal_closes_record_when_no_locator_pin():
    store = {
        'Id': '100', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00036', 'Enterprise_Code': '', 'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status(
        [store], config, locator_pins={}, gdt_cache={},
        closure_signals={100: {'signal': 'superseded', 'newer_id': 999}},
    )
    assert store['Operating_Status'] == 'Closed'
    assert store['Operating_Evidence'] == 'structural:superseded:999'
    assert store['Core_Operating_Store'] == 'No'


def test_locator_pin_outranks_superseded_signal():
    store = {
        'Id': '100', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '00036', 'Enterprise_Code': '', 'Status': None,
    }
    config = make_optin_config()
    resolve_operating_status(
        [store], config, locator_pins={100: 'Unique'}, gdt_cache={},
        closure_signals={100: {'signal': 'superseded', 'newer_id': 999}},
    )
    assert store['Operating_Status'] == 'Operating'
    assert store['Operating_Evidence'] == 'locator:Unique'


# --- Regression guard: closure_signals=None reproduces the pre-existing ladder ---

def test_no_closure_signals_is_backward_compatible():
    store = {
        'Id': '500', 'Store_Brand_Format': 'Test Brand',
        'Enterprise_Gdt_Code': '0100000001-001', 'Enterprise_Code': '',
        'Status': 'NNT đang hoạt động',
    }
    config = make_optin_config()  # seed_parent_msts = ['0306182043']
    resolve_operating_status(
        [store], config, locator_pins={},
        gdt_cache={'0100000001': {'status': 'NNT đang hoạt động'}},
    )  # closure_signals omitted entirely — must default to None
    assert store['Operating_Status'] == 'Operating'
    assert store['Operating_Evidence'] == 'gdt-own-mst'
    assert store['Core_Operating_Store'] == 'Yes'
