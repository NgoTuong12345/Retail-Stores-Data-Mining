import pytest
from dkkd.data.provinces import PROVINCES, get_province_amplifiers, get_accent_variants

def test_provinces_count():
    assert len(PROVINCES) == 63

def test_province_has_accented_and_plain():
    ha_noi = [p for p in PROVINCES if p.slug == 'ha-noi']
    assert len(ha_noi) == 1
    assert ha_noi[0].accented == 'HÀ NỘI'
    assert ha_noi[0].plain == 'HA NOI'

def test_get_province_amplifiers_top5():
    top5 = get_province_amplifiers(tier='top5')
    slugs = {p.slug for p in top5}
    assert slugs == {'ha-noi', 'ho-chi-minh', 'da-nang', 'hai-phong', 'can-tho'}

def test_get_province_amplifiers_rest():
    rest = get_province_amplifiers(tier='rest')
    assert len(rest) == 58

def test_slugs_unique():
    slugs = [p.slug for p in PROVINCES]
    assert len(slugs) == len(set(slugs))

def test_get_province_amplifiers_invalid_tier():
    with pytest.raises(ValueError, match="Invalid tier: 'invalid'"):
        # type: ignore (testing runtime validation of string input)
        get_province_amplifiers(tier='invalid')

def test_get_accent_variants_thanh_hoa():
    variants = get_accent_variants("THANH HÓA")
    assert variants == ["THANH HOÁ", "THANH HÓA"]

def test_every_province_has_a_region():
    assert all(p.region for p in PROVINCES)

def test_region_spot_checks():
    by_slug = {p.slug: p.region for p in PROVINCES}
    assert by_slug['ha-noi'] == 'Đồng Bằng Sông Hồng'
    assert by_slug['ho-chi-minh'] == 'Đông Nam Bộ'
    assert by_slug['thanh-hoa'] == 'Bắc Trung Bộ'
    assert by_slug['can-tho'] == 'ĐBSCL'

def test_region_by_accented_matches_provinces():
    from dkkd.data.provinces import REGION_BY_ACCENTED
    assert REGION_BY_ACCENTED['HỒ CHÍ MINH'] == 'Đông Nam Bộ'
    assert len(REGION_BY_ACCENTED) == len(PROVINCES)

def test_every_province_has_a_region_post_reform():
    assert all(p.region_post_reform for p in PROVINCES)

def test_region_post_reform_by_accented_matches_provinces():
    from dkkd.data.provinces import REGION_POST_REFORM_BY_ACCENTED
    assert REGION_POST_REFORM_BY_ACCENTED['HỒ CHÍ MINH'] == 'Đông Nam Bộ'
    assert len(REGION_POST_REFORM_BY_ACCENTED) == len(PROVINCES)

def test_region_and_region_post_reform_differ_only_for_known_8_provinces():
    # These 8 old provinces merged (July 2025) into a province in a different
    # traditional region — everywhere else the two columns must agree.
    expected_diff_slugs = {
        'hoa-binh', 'bac-giang', 'vinh-phuc', 'binh-dinh',
        'phu-yen', 'binh-thuan', 'kon-tum', 'long-an',
    }
    diff_slugs = {p.slug for p in PROVINCES if p.region != p.region_post_reform}
    assert diff_slugs == expected_diff_slugs

def test_hoa_binh_region_traditional_vs_post_reform():
    hoa_binh = next(p for p in PROVINCES if p.slug == 'hoa-binh')
    assert hoa_binh.region == 'Tây Bắc Bộ'
    assert hoa_binh.region_post_reform == 'Đông Bắc Bộ'
