"""Tests for dkkd.utils — fold_ascii and parse_gdt."""
import pytest
from dkkd.utils import fold_ascii, parse_gdt


# ── Task 1: fold_ascii ──────────────────────────────────────────────

class TestFoldAscii:
    def test_d_with_stroke(self):
        assert fold_ascii('Đặng') == 'dang'

    def test_circumflex_o(self):
        assert fold_ascii('Trường') == 'truong'

    def test_d_stroke_lowercase(self):
        assert fold_ascii('đường') == 'duong'

    def test_ascii_passthrough(self):
        assert fold_ascii('CO.OP FOOD') == 'co.op food'

    def test_nguyen(self):
        assert fold_ascii('Nguyễn') == 'nguyen'


# ── Task 2: parse_gdt ───────────────────────────────────────────────

class TestParseGdt:
    def test_counter_format(self):
        assert parse_gdt('00036') == {'format': 'counter', 'seq': 36}

    def test_branch_format(self):
        assert parse_gdt('0309129418-005') == {
            'format': 'branch',
            'parent_mst': '0309129418',
            'branch_seq': 5,
        }

    def test_none_input(self):
        assert parse_gdt(None) == {'format': 'empty'}

    def test_empty_string(self):
        assert parse_gdt('') == {'format': 'empty'}

    def test_other_format(self):
        assert parse_gdt('XYZ123') == {'format': 'other', 'raw': 'XYZ123'}
