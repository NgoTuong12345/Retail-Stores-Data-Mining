# tests/test_tenant_tagging.py
"""Tests for the deterministic 3-way tenant role classifier.

Fixtures are REAL coop-extra rows (see brands/F&B/hyper_supermarket/coop-extra),
trimmed to the fields the rule reads.
"""
from dkkd.config import BrandConfig
from dkkd.tenant import base_mst, tag_roles

_COOPXTRA_REGEX = r'CO[\.\\\,\-]?\s*OP\s*XTRA|COOPXTRA'


def _config(enabled=True):
    return BrandConfig(
        slug='coop-extra', name='Coop-Extra',
        brand_regex=_COOPXTRA_REGEX,
        seed_parent_msts=['0301175691'],
        classification={'tenant_separation': {'enabled': enabled}},
    )


_OWN = {
    'Id': '3412393', 'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '0014819878',
    'Name': 'THỦ ĐỨC CO-OP XTRA',
    'Ho_Address': 'Số 934, Quốc lộ 1A, Phường Linh Xuân, Thành phố Hồ Chí Minh, Việt Nam',
}
_TENANT_FRICO = {
    'Id': '7214637', 'Enterprise_Gdt_Code': '00017', 'Enterprise_Code': '0022758357',
    'Name': 'GIAN HÀNG FRICO – CO.OP XTRA - CÔNG TY TNHH COOKMIX',
    'Ho_Address': 'Vị trí M-12, Tầng hầm CO.OP XTRA Sư Vạn Hạnh - Số 11 Sư Vạn Hạnh, Phường 12, Quận 10, TP.HCM',
}
_TENANT_CRESCENT = {
    'Id': '9366340', 'Enterprise_Gdt_Code': '0309453012-035', 'Enterprise_Code': '0028374240',
    'Name': 'CHI NHÁNH TẠI CO.OP XTRA CRESCENT MALL - CÔNG TY TNHH THƯƠNG MẠI XUẤT NHẬP KHẨU ĐẠI THẾ GIỚI',
    'Ho_Address': 'Tầng B1, Trung tâm mua sắm Crescent Mall, số 101 Tôn Dật Tiên, Quận 7, TP.HCM',
}
_UNRELATED = {
    'Id': '227839', 'Enterprise_Gdt_Code': '0309453012-002', 'Enterprise_Code': '0002514524',
    'Name': 'CHI NHÁNH CÔNG TY TNHH MỘT THÀNH VIÊN THƯƠNG MẠI XUẤT NHẬP KHẨU ĐẠI THẾ GIỚI',
    'Ho_Address': 'L1-05, lầu 1, Co.op Mart Vũng tàu, Số 36 Nguyễn Thái Học, Vũng Tàu',
}


class TestBaseMst:
    def test_format_b_returns_head(self):
        assert base_mst({'Enterprise_Gdt_Code': '0309453012-002'}) == '0309453012'

    def test_bare_ten_digit_gdt_returns_itself(self):
        assert base_mst({'Enterprise_Gdt_Code': '0100796508'}) == '0100796508'

    def test_format_a_five_digit_falls_back_to_enterprise_code(self):
        assert base_mst({'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '0014819878'}) == '0014819878'

    def test_no_code_returns_empty(self):
        assert base_mst({'Enterprise_Gdt_Code': '', 'Enterprise_Code': ''}) == ''


class TestTagRoles:
    def _roles(self, records, enabled=True):
        stores = [dict(r) for r in records]
        tag_roles(stores, _config(enabled))
        return {s['Id']: s['store_role'] for s in stores}

    def test_own_store_by_clean_brand_name(self):
        assert self._roles([_OWN])['3412393'] == 'own_store'

    def test_tenant_by_gian_hang_marker(self):
        assert self._roles([_TENANT_FRICO])['7214637'] == 'in_brand_tenant'

    def test_tenant_inside_brand_even_with_other_parent_mst(self):
        # Đại Thế Giới branch, but physically inside Co.opXtra Crescent Mall
        assert self._roles([_TENANT_CRESCENT])['9366340'] == 'in_brand_tenant'

    def test_unrelated_when_brand_token_absent(self):
        # Đại Thế Giới branch inside Co.op MART (a different mall) — token nowhere
        assert self._roles([_UNRELATED])['227839'] == 'unrelated'

    def test_own_store_by_parent_mst(self):
        rec = {'Id': 'x', 'Enterprise_Gdt_Code': '0301175691-050',
               'Name': 'CHI NHÁNH CÔNG TY ... CO.OPXTRA', 'Ho_Address': ''}
        assert self._roles([rec])['x'] == 'own_store'

    def test_disabled_tags_everything_own_store(self):
        roles = self._roles([_TENANT_FRICO, _UNRELATED], enabled=False)
        assert set(roles.values()) == {'own_store'}

    def test_host_store_key_always_present(self):
        stores = [dict(_TENANT_FRICO)]
        tag_roles(stores, _config())
        assert 'host_store' in stores[0]

    def test_discovered_mst_is_not_treated_as_own_store(self):
        # Regression: coop-extra's discovered.json has discovered_msts=['0309453012'],
        # which is Đại Thế Giới's MST (a productive Solr search seed the sweep
        # found), NOT Saigon Co.op's own entity. Only seed_parent_msts may grant
        # own_store via MST match — discovered_msts must not.
        cfg = BrandConfig(
            slug='coop-extra', name='Coop-Extra', brand_regex=_COOPXTRA_REGEX,
            seed_parent_msts=['0301175691'], discovered_msts=['0309453012'],
            classification={'tenant_separation': {'enabled': True}},
        )
        stores = [dict(_UNRELATED)]  # base_mst == '0309453012'
        tag_roles(stores, cfg)
        assert stores[0]['store_role'] == 'unrelated'

    def test_own_store_name_pattern_catches_format_a_business_locations(self):
        # Real AEON case: MaxValu stores are registered as AEON Việt Nam's own
        # Format-A business locations ('CÔNG TY TNHH AEON VIỆT NAM – ĐỊA ĐIỂM
        # KINH DOANH MAXVALU ...'), each with a unique Enterprise_Code (Format A
        # 5-digit GDT codes encode no shared parent MST — see base_mst). Neither
        # the MST check nor the bare-name check (blocked by the 'CÔNG TY'
        # third-party marker) can catch these; only an explicit official-entity
        # name pattern can.
        cfg = BrandConfig(
            slug='aeon-supermarket', name='AEON (Supermarket)',
            brand_regex=r'AEON|CITIMART|MAX\s*VALU',
            seed_parent_msts=['0311241512'],
            classification={
                'tenant_separation': {
                    'enabled': True,
                    'own_store_name_patterns': [r'^CÔNG TY TNHH AEON VIỆT NAM'],
                },
            },
        )
        rec = {
            'Id': '8176960', 'Enterprise_Gdt_Code': '00008', 'Enterprise_Code': '0024921646',
            'Name': 'CÔNG TY TNHH AEON VIỆT NAM – ĐỊA ĐIỂM KINH DOANH MAXVALU VĂN TÂN',
            'Ho_Address': 'Văn Tân, Hà Nội',
        }
        stores = [rec]
        tag_roles(stores, cfg)
        assert stores[0]['store_role'] == 'own_store'

    def test_own_store_name_pattern_does_not_leak_to_unrelated_companies(self):
        # A genuinely different company operating inside an AEON mall must NOT
        # be swept into own_store just because the brand regex sits nearby.
        cfg = BrandConfig(
            slug='aeon-supermarket', name='AEON (Supermarket)',
            brand_regex=r'AEON|CITIMART|MAX\s*VALU',
            seed_parent_msts=['0311241512'],
            classification={
                'tenant_separation': {
                    'enabled': True,
                    'own_store_name_patterns': [r'^CÔNG TY TNHH AEON VIỆT NAM'],
                },
            },
        )
        rec = {
            'Id': '1', 'Enterprise_Gdt_Code': '0302286281-001', 'Enterprise_Code': '',
            'Name': 'CHI NHÁNH CÔNG TY CỔ PHẦN THƯƠNG MẠI NGUYỄN KIM - TRUNG TÂM MUA SẮM NGUYỄN KIM AEON TÂN PHÚ',
            'Ho_Address': 'AEON Tân Phú',
        }
        stores = [rec]
        tag_roles(stores, cfg)
        assert stores[0]['store_role'] == 'in_brand_tenant'

    def test_own_store_name_pattern_without_anchor_matches_anywhere_in_name(self):
        # Real AEON case: Citimart's original operator (Đông Hưng) puts the
        # legal entity name at the END of some registrations, not the start
        # ('GIAN HÀNG CITIMART MỸ ĐÌNH - CHI NHÁNH CÔNG TY TNHH THƯƠNG MẠI
        # DỊCH VỤ ĐÔNG HƯNG'). A pattern with no '^' anchor must still match.
        cfg = BrandConfig(
            slug='aeon-supermarket', name='AEON (Supermarket)',
            brand_regex=r'AEON|CITIMART|MAX\s*VALU',
            classification={
                'tenant_separation': {
                    'enabled': True,
                    'own_store_name_patterns': [r'CÔNG TY TNHH THƯƠNG MẠI DỊCH VỤ ĐÔNG HƯNG'],
                },
            },
        )
        rec = {
            'Id': '583612', 'Enterprise_Gdt_Code': '', 'Enterprise_Code': '0006246141',
            'Name': 'GIAN HÀNG CITIMART MỸ ĐÌNH - CHI NHÁNH CÔNG TY TNHH THƯƠNG MẠI DỊCH VỤ ĐÔNG HƯNG',
            'Ho_Address': 'Mỹ Đình, Hà Nội',
        }
        stores = [rec]
        tag_roles(stores, cfg)
        assert stores[0]['store_role'] == 'own_store'
