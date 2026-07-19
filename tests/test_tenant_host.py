# tests/test_tenant_host.py
"""Tests for host-outlet label parsing and grouping key."""
import re

from dkkd.config import BrandConfig
from dkkd.tenant import parse_host, _host_key, tag_roles

_REGEX = re.compile(r'CO[\.\\\,\-]?\s*OP\s*XTRA|COOPXTRA', re.IGNORECASE)


class TestParseHost:
    def test_extracts_mall_name_from_address(self):
        rec = {'Ho_Address': 'Vị trí M-12, Tầng hầm CO.OP XTRA Sư Vạn Hạnh - Số 11 Sư Vạn Hạnh, Quận 10'}
        assert 'Sư Vạn Hạnh' in parse_host(rec, _REGEX)

    def test_stops_at_comma(self):
        rec = {'Ho_Address': 'Tầng hầm CO.OPXTRA SƯ VẠN HẠNH, Số 11 Sư Vạn Hạnh'}
        assert parse_host(rec, _REGEX) == 'CO.OPXTRA SƯ VẠN HẠNH'

    def test_falls_back_to_name_when_address_has_no_token(self):
        rec = {'Ho_Address': '101 Tôn Dật Tiên, Quận 7',
               'Name': 'SPICY BOX CO.OPXTRA VẠN HẠNH - ĐỊA ĐIỂM KINH DOANH CÔNG TY X'}
        assert 'VẠN HẠNH' in parse_host(rec, _REGEX)

    def test_no_token_returns_empty(self):
        rec = {'Ho_Address': 'Co.op Mart Vũng Tàu', 'Name': 'CHI NHÁNH ĐẠI THẾ GIỚI'}
        assert parse_host(rec, _REGEX) == ''


class TestHostKey:
    def test_folds_diacritics_and_spacing_so_variants_merge(self):
        # 'CO.OPXTRA SƯ VẠN HẠNH' and 'CO.OP XTRA Sư Vạn Hạnh' are one outlet
        assert _host_key('CO.OPXTRA SƯ VẠN HẠNH') == _host_key('CO.OP XTRA Sư Vạn Hạnh')

    def test_different_outlets_have_different_keys(self):
        assert _host_key('Co.opXtra Sư Vạn Hạnh') != _host_key('Co.opXtra Crescent Mall')

    def test_blank_label_is_empty_key(self):
        assert _host_key('') == ''


def test_tag_roles_fills_host_for_tenant_only():
    stores = [
        {'Id': 't', 'Enterprise_Gdt_Code': '00017', 'Enterprise_Code': '0022758357',
         'Name': 'GIAN HÀNG FRICO – CO.OP XTRA - CÔNG TY TNHH COOKMIX',
         'Ho_Address': 'Tầng hầm CO.OP XTRA Sư Vạn Hạnh, Số 11'},
        {'Id': 'o', 'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '0014819878',
         'Name': 'THỦ ĐỨC CO-OP XTRA', 'Ho_Address': 'Số 934 Quốc lộ 1A'},
    ]
    cfg = BrandConfig(slug='coop-extra', name='Coop-Extra',
                      brand_regex=r'CO[\.\\\,\-]?\s*OP\s*XTRA|COOPXTRA',
                      seed_parent_msts=['0301175691'],
                      classification={'tenant_separation': {'enabled': True}})
    tag_roles(stores, cfg)
    assert 'Sư Vạn Hạnh' in stores[0]['host_store']
    assert stores[1]['host_store'] == ''
