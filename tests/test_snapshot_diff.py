"""TDD tests for dkkd.snapshot_diff — pure diff core, no I/O."""
from dkkd.snapshot_diff import _records_to_by_id, diff_snapshots


# --- _records_to_by_id ---

def test_records_to_by_id_keys_on_string_id():
    records = [{'Id': '100', 'Name': 'A'}, {'Id': '200', 'Name': 'B'}]
    by_id = _records_to_by_id(records)
    assert by_id == {'100': {'Id': '100', 'Name': 'A'}, '200': {'Id': '200', 'Name': 'B'}}


def test_records_to_by_id_coerces_int_id_to_string():
    records = [{'Id': 100, 'Name': 'A'}]
    assert _records_to_by_id(records) == {'100': {'Id': 100, 'Name': 'A'}}


# --- diff_snapshots: no-op ---

def test_diff_snapshots_identical_is_all_empty():
    older = {'1': {'Id': '1', 'Name': 'A', 'Ho_Address': 'Addr 1', 'Operating_Status': 'Operating'}}
    newer = {'1': {'Id': '1', 'Name': 'A', 'Ho_Address': 'Addr 1', 'Operating_Status': 'Operating'}}
    result = diff_snapshots(older, newer)
    assert result['new_ids'] == {'genuinely_new': [], 'newly_discovered': []}
    assert result['vanished_ids'] == []
    assert result['relocations'] == {}
    assert result['status_changes'] == {}
    assert result['renamed'] == {}


# --- new_ids split ---

def test_new_ids_genuinely_new_when_establishment_date_in_window():
    older = {}
    newer = {'1': {'Id': '1', 'Name': 'A', 'Establishment_Date': '2026-06-15'}}
    result = diff_snapshots(older, newer, older_date='2026-06-01', newer_date='2026-06-30')
    assert result['new_ids']['genuinely_new'] == ['1']
    assert result['new_ids']['newly_discovered'] == []


def test_new_ids_newly_discovered_when_establishment_date_predates_window():
    older = {}
    newer = {'1': {'Id': '1', 'Name': 'A', 'Establishment_Date': '2020-01-01'}}
    result = diff_snapshots(older, newer, older_date='2026-06-01', newer_date='2026-06-30')
    assert result['new_ids']['genuinely_new'] == []
    assert result['new_ids']['newly_discovered'] == ['1']


def test_new_ids_newly_discovered_when_no_dates_provided():
    older = {}
    newer = {'1': {'Id': '1', 'Name': 'A', 'Establishment_Date': '2026-06-15'}}
    result = diff_snapshots(older, newer)
    assert result['new_ids']['genuinely_new'] == []
    assert result['new_ids']['newly_discovered'] == ['1']


def test_new_ids_newly_discovered_when_establishment_date_missing():
    older = {}
    newer = {'1': {'Id': '1', 'Name': 'A'}}
    result = diff_snapshots(older, newer, older_date='2026-06-01', newer_date='2026-06-30')
    assert result['new_ids']['genuinely_new'] == []
    assert result['new_ids']['newly_discovered'] == ['1']


# --- vanished_ids ---

def test_vanished_ids_present_in_older_only():
    older = {'1': {'Id': '1', 'Name': 'A'}}
    newer = {}
    result = diff_snapshots(older, newer)
    assert result['vanished_ids'] == ['1']
    # Must never be conflated with a status label.
    assert 'Closed' not in str(result['vanished_ids'])


# --- relocations ---

def test_relocation_fires_on_real_address_change():
    older = {'1': {'Id': '1', 'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'}}
    newer = {'1': {'Id': '1', 'Ho_Address': '456 Le Loi, Phuong 2, Quan 3, TP.HCM'}}
    result = diff_snapshots(older, newer)
    assert result['relocations'] == {
        '1': {
            'old_address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM',
            'new_address': '456 Le Loi, Phuong 2, Quan 3, TP.HCM',
        }
    }


def test_relocation_does_not_fire_on_formatting_only_change():
    older = {'1': {'Id': '1', 'Ho_Address': '123 Duong Nguyen Trai, Phuong 1, Quan 1, TP.HCM'}}
    newer = {'1': {'Id': '1', 'Ho_Address': '123 NGUYEN TRAI, PHUONG 1, QUAN 1, TP.HCM'}}
    result = diff_snapshots(older, newer)
    assert result['relocations'] == {}


def test_relocation_does_not_fire_when_address_missing_on_either_side():
    older = {'1': {'Id': '1', 'Ho_Address': ''}}
    newer = {'1': {'Id': '1', 'Ho_Address': '456 Le Loi, Phuong 2, Quan 3, TP.HCM'}}
    result = diff_snapshots(older, newer)
    assert result['relocations'] == {}


# --- status_changes ---

def test_status_change_fires_with_bracket():
    older = {'1': {'Id': '1', 'Operating_Status': 'Operating'}}
    newer = {'1': {'Id': '1', 'Operating_Status': 'Closed'}}
    result = diff_snapshots(older, newer, older_date='2026-06-01', newer_date='2026-06-30')
    assert result['status_changes'] == {
        '1': {'old_status': 'Operating', 'new_status': 'Closed', 'bracket': ['2026-06-01', '2026-06-30']}
    }


def test_status_change_does_not_fire_when_status_missing_on_either_side():
    older = {'1': {'Id': '1', 'Operating_Status': ''}}
    newer = {'1': {'Id': '1', 'Operating_Status': 'Closed'}}
    result = diff_snapshots(older, newer)
    assert result['status_changes'] == {}


def test_status_change_does_not_fire_when_unchanged():
    older = {'1': {'Id': '1', 'Operating_Status': 'Operating'}}
    newer = {'1': {'Id': '1', 'Operating_Status': 'Operating'}}
    result = diff_snapshots(older, newer)
    assert result['status_changes'] == {}


# --- renamed ---

def test_renamed_fires_on_name_change_independent_of_address():
    older = {'1': {'Id': '1', 'Name': 'Old Name Co', 'Ho_Address': 'Same Address'}}
    newer = {'1': {'Id': '1', 'Name': 'New Name Co', 'Ho_Address': 'Same Address'}}
    result = diff_snapshots(older, newer)
    assert result['renamed'] == {'1': {'old_name': 'Old Name Co', 'new_name': 'New Name Co'}}
    assert result['relocations'] == {}


def test_renamed_and_relocation_can_co_fire_for_same_id():
    older = {'1': {'Id': '1', 'Name': 'Old Name Co', 'Ho_Address': '123 Nguyen Trai, Quan 1'}}
    newer = {'1': {'Id': '1', 'Name': 'New Name Co', 'Ho_Address': '456 Le Loi, Quan 3'}}
    result = diff_snapshots(older, newer)
    assert result['renamed'] == {'1': {'old_name': 'Old Name Co', 'new_name': 'New Name Co'}}
    assert result['relocations'] == {
        '1': {'old_address': '123 Nguyen Trai, Quan 1', 'new_address': '456 Le Loi, Quan 3'}
    }
