"""TDD tests for dkkd.closure_signals — write failing first, then implement."""
from dkkd.closure_signals import (
    label_from_status,
    parent_dissolution_map,
    build_address_clusters,
    mark_superseded,
    build_closure_signal_map,
)


# --- label_from_status ---

def test_label_from_status_ceased_phrase_is_closed():
    assert label_from_status('Chấm dứt hoạt động') == 'Closed'


def test_label_from_status_active_phrase_is_operating():
    assert label_from_status('Đang hoạt động') == 'Operating'


def test_label_from_status_empty_is_operating():
    assert label_from_status('') == 'Operating'
    assert label_from_status(None) == 'Operating'


# --- parent_dissolution_map ---

def test_parent_dissolution_map_flags_mst_with_own_ceased_status():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'Chấm dứt hoạt động'},
        {'Id': '2', 'Enterprise_Gdt_Code': '2222222222-001', 'Enterprise_Code': '',
         'Status': 'NNT đang hoạt động'},
    ]
    dissolved = parent_dissolution_map(records)
    assert dissolved == {'1111111111': True}


def test_parent_dissolution_map_empty_when_no_ceased_status():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'NNT đang hoạt động'},
    ]
    assert parent_dissolution_map(records) == {}


def test_parent_dissolution_map_excludes_seed_parent_msts():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'Chấm dứt hoạt động'},
    ]
    dissolved = parent_dissolution_map(records, seed_parent_msts={'1111111111'})
    assert dissolved == {}


# --- build_address_clusters ---

def test_build_address_clusters_groups_same_mst_same_address():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '2', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '3', 'Enterprise_Gdt_Code': '1111111111-003', 'Enterprise_Code': '',
         'Ho_Address': '456 Le Loi, Phuong 2, Quan 3, TP.HCM'},
    ]
    clusters = build_address_clusters(records)
    assert len(clusters) == 1
    cluster_ids = {r['Id'] for r in list(clusters.values())[0]}
    assert cluster_ids == {'1', '2'}


def test_build_address_clusters_excludes_singletons():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    assert build_address_clusters(records) == {}


def test_build_address_clusters_does_not_merge_across_different_mst():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '2', 'Enterprise_Gdt_Code': '2222222222-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    assert build_address_clusters(records) == {}


# --- mark_superseded ---

def test_mark_superseded_older_id_points_to_newest():
    records = [
        {'Id': '100', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '200', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    assert mark_superseded(records) == {100: 200}


def test_mark_superseded_three_way_cluster_all_point_to_newest():
    records = [
        {'Id': '50', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '100', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '200', 'Enterprise_Gdt_Code': '1111111111-003', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    assert mark_superseded(records) == {50: 200, 100: 200}


def test_mark_superseded_no_clusters_is_empty():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    assert mark_superseded(records) == {}


# --- build_closure_signal_map ---

def test_build_closure_signal_map_parent_dissolved_signal():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'Chấm dứt hoạt động', 'Ho_Address': 'A'},
        {'Id': '2', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Status': None, 'Ho_Address': 'B'},
    ]
    signals = build_closure_signal_map(records)
    assert signals[1] == {'signal': 'parent_dissolved'}
    assert signals[2] == {'signal': 'parent_dissolved'}


def test_build_closure_signal_map_superseded_signal():
    records = [
        {'Id': '100', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': None, 'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '200', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Status': None, 'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    signals = build_closure_signal_map(records)
    assert signals[100] == {'signal': 'superseded', 'newer_id': 200}
    assert 200 not in signals


def test_build_closure_signal_map_dissolution_outranks_supersession():
    records = [
        {'Id': '100', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'Chấm dứt hoạt động',
         'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
        {'Id': '200', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Status': None, 'Ho_Address': '123 Nguyen Trai, Phuong 1, Quan 1, TP.HCM'},
    ]
    signals = build_closure_signal_map(records)
    assert signals[100] == {'signal': 'parent_dissolved'}
    assert signals[200] == {'signal': 'parent_dissolved'}


def test_build_closure_signal_map_external_dissolved_msts():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '3333333333-001', 'Enterprise_Code': '',
         'Status': None, 'Ho_Address': 'A'},
    ]
    signals = build_closure_signal_map(records, external_dissolved_msts={'3333333333'})
    assert signals[1] == {'signal': 'parent_dissolved'}


def test_build_closure_signal_map_no_signal_when_clean():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'NNT đang hoạt động', 'Ho_Address': 'A'},
    ]
    assert build_closure_signal_map(records) == {}


def test_build_closure_signal_map_excludes_seed_parent_msts():
    records = [
        {'Id': '1', 'Enterprise_Gdt_Code': '1111111111-001', 'Enterprise_Code': '',
         'Status': 'Chấm dứt hoạt động', 'Ho_Address': 'A'},
        {'Id': '2', 'Enterprise_Gdt_Code': '1111111111-002', 'Enterprise_Code': '',
         'Status': None, 'Ho_Address': 'B'},
    ]
    signals = build_closure_signal_map(records, seed_parent_msts={'1111111111'})
    assert 1 not in signals
    assert 2 not in signals
