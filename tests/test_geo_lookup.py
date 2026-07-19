import pytest
import re
from dkkd.data.geo_lookup import get_geo_lookup, normalize_geo_name


def test_normalize_geo_name():
    assert normalize_geo_name("Thành phố Hà Nội") == "ha noi"
    assert normalize_geo_name("Quận Cầu Giấy") == "cau giay"
    assert normalize_geo_name("Phường Phúc Xá") == "phuc xa"
    assert normalize_geo_name("Xã Phong Phú") == "phong phu"
    assert normalize_geo_name("Thị trấn Chợ Lách") == "cho lach"
    assert normalize_geo_name("tp.hcm") == "tp.hcm"
    assert normalize_geo_name("Bến Tre") == "ben tre"
    assert normalize_geo_name("") == ""
    assert normalize_geo_name(None) == ""


def test_geo_lookup_singleton():
    l1 = get_geo_lookup()
    l2 = get_geo_lookup()
    assert l1 is l2


def test_id_to_name_resolution():
    lookup = get_geo_lookup()
    # City
    assert lookup.get_city_name(81) == "Thành phố Hà Nội"
    assert lookup.get_city_name("122") == "Thành phố Hồ Chí Minh"
    assert lookup.get_city_name(9999) is None

    # District
    assert lookup.get_district_name(1037) == "Quận Cầu Giấy"
    assert lookup.get_district_name(794) == "Quận 1"
    assert lookup.get_district_name(9999) is None

    # Ward
    assert lookup.get_ward_name(12087) == "Phường Quan Hoa"
    assert lookup.get_ward_name(20276) == "Phường Bến Nghé"
    assert lookup.get_ward_name(99999) is None


def test_name_to_id_resolution():
    lookup = get_geo_lookup()
    assert lookup.find_city_id("Hà Nội") == "81"
    assert lookup.find_city_id("Hồ Chí Minh") == "122"
    assert lookup.find_city_id("Nonexistent City") is None

    # District lookup
    assert "1037" in lookup.find_district_ids("Cầu Giấy")
    assert "794" in lookup.find_district_ids("Quận 1")
    # Chau Thanh exists in multiple provinces
    chau_thanh_dids = lookup.find_district_ids("Châu Thành")
    assert len(chau_thanh_dids) > 1
    # Resolved with city_id filter
    chau_thanh_la_dids = lookup.find_district_ids("Châu Thành", city_id=131) # Long An
    assert len(chau_thanh_la_dids) == 1


def test_regex_generation():
    lookup = get_geo_lookup()
    hcm_regex = lookup.generate_regex("Thành phố Hồ Chí Minh", "city")
    assert bool(re.search(hcm_regex, "TP.HCM", re.IGNORECASE))
    assert bool(re.search(hcm_regex, "tp hcm", re.IGNORECASE))
    assert bool(re.search(hcm_regex, "Hồ Chí Minh", re.IGNORECASE))
    assert bool(re.search(hcm_regex, "Sài Gòn", re.IGNORECASE))
    assert not bool(re.search(hcm_regex, "Bình Dương", re.IGNORECASE))

    cau_giay_regex = lookup.generate_regex("Quận Cầu Giấy", "district")
    assert bool(re.search(cau_giay_regex, "Cầu Giấy", re.IGNORECASE))
    assert bool(re.search(cau_giay_regex, "Q. Cầu Giấy", re.IGNORECASE))
    assert bool(re.search(cau_giay_regex, "Quận Cầu Giấy", re.IGNORECASE))
    assert not bool(re.search(cau_giay_regex, "Hoàn Kiếm", re.IGNORECASE))


def test_address_resolution():
    lookup = get_geo_lookup()
    
    # Standard complete address
    cid, did, wid = lookup.resolve_address_ids(
        "100 Cầu Giấy, Phường Quan Hoa, Quận Cầu Giấy, Thành phố Hà Nội"
    )
    assert cid == "81"
    assert did == "1037"
    assert wid == "12087"

    # Minimal address with abbreviations
    cid, did, wid = lookup.resolve_address_ids(
        "Số 5 Nguyễn Huệ, P. Bến Nghé, Q1, TPHCM"
    )
    assert cid == "122"
    assert did == "794"
    assert wid == "20276"

    # Address missing city name (inferred from unique district)
    cid, did, wid = lookup.resolve_address_ids(
        "Xã Phong Phú, Huyện Bình Chánh"
    )
    assert cid == "122"
    assert did == "815"
    assert wid == "20567"


def test_get_region():
    lookup = get_geo_lookup()
    assert lookup.get_region(81) == "Đồng Bằng Sông Hồng"     # Hà Nội
    assert lookup.get_region("122") == "Đông Nam Bộ"          # Hồ Chí Minh
    assert lookup.get_region("138") == "ĐBSCL"                # Cần Thơ
    # Post-2025-reform renamed City_Ids fold into their original province's region
    assert lookup.get_region("144") == "Bắc Trung Bộ"         # Thành phố Huế
    assert lookup.get_region("145") == "Đông Nam Bộ"          # Thành phố Đồng Nai
    assert lookup.get_region(9999) is None


def test_get_region_covers_every_known_city_id():
    lookup = get_geo_lookup()
    assert all(lookup.get_region(cid) for cid in lookup.cities)


def test_get_region_post_reform():
    lookup = get_geo_lookup()
    # Hòa Bình (city_id 105): traditional Tây Bắc Bộ, but merged into Phú Thọ
    # (July 2025 reform), whose own region is Đông Bắc Bộ.
    assert lookup.get_region(105) == "Tây Bắc Bộ"
    assert lookup.get_region_post_reform(105) == "Đông Bắc Bộ"
    # Provinces with no 2025 merger-partner region change agree on both.
    assert lookup.get_region_post_reform("122") == "Đông Nam Bộ"          # Hồ Chí Minh
    assert lookup.get_region_post_reform(9999) is None


def test_get_region_post_reform_covers_every_known_city_id():
    lookup = get_geo_lookup()
    assert all(lookup.get_region_post_reform(cid) for cid in lookup.cities)
