"""Tests for dkkd.records — Task 6: SweepState derived counters."""
import pytest
from dkkd.records import SweepState

FIXTURE_STORE = {
    '1': {'Id': '1', 'Name': 'Store 1', 'Enterprise_Gdt_Code': '00036'},
    '2': {'Id': '2', 'Name': 'Store 2', 'Enterprise_Gdt_Code': '00142'},
    '3': {'Id': '3', 'Name': 'Store 3', 'Enterprise_Gdt_Code': '0309129418-005'},
    '4': {'Id': '4', 'Name': 'Store 4', 'Enterprise_Gdt_Code': '0309129418-012'},
    '5': {'Id': '5', 'Name': 'Store 5', 'Enterprise_Gdt_Code': '0305767459-003'},
    '6': {'Id': '6', 'Name': 'Store 6', 'Enterprise_Gdt_Code': 'XYZ123'},
    '7': {'Id': '7', 'Name': 'Store 7', 'Enterprise_Gdt_Code': None},
    '8': {'Id': '8', 'Name': 'Store 8', 'Enterprise_Gdt_Code': ''},
    '9': {'Id': '9', 'Name': 'Store 9', 'Enterprise_Gdt_Code': '00001'},
    '10': {'Id': '10', 'Name': 'Store 10'},  # missing key entirely
}

class TestSweepState:
    def test_total_records(self):
        state = SweepState(store_map=FIXTURE_STORE)
        assert state.total_records == 10

    def test_discovered_msts(self):
        state = SweepState(store_map=FIXTURE_STORE)
        assert state.discovered_msts == {'0309129418', '0305767459'}

    def test_max_counter_seq(self):
        state = SweepState(store_map=FIXTURE_STORE)
        assert state.max_counter_seq == 142

    def test_max_branch_seq(self):
        state = SweepState(store_map=FIXTURE_STORE)
        assert state.max_branch_seq == 12

    def test_empty_store(self):
        state = SweepState(store_map={})
        assert state.total_records == 0
        assert state.discovered_msts == set()
        assert state.max_counter_seq == 0
        assert state.max_branch_seq == 0
