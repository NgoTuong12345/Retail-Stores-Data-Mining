"""Per-brand regression regression table for known filter incidents.

Each entry documents a real contamination/miss incident and the fix that
resolved it. Add a new brand's regression as a row in BRANDS below — never
as a new file. If a brand's config is later removed, its case is skipped
rather than failing the suite.
"""
import pytest

from dkkd import config as cfg
from dkkd.ingest import Ingester
from dkkd.paths import config_yaml
from tests.conftest import make_row

BRANDS = {
    'bach-hoa-xanh': {
        'config_asserts': {
            'name': 'Bách Hóa Xanh',
            'seed_parent_msts_contains': '0310471746',
        },
        'regex_positives': [
            'CỬA HÀNG BÁCH HÓA XANH SỐ 385',
            'ĐỊA ĐIỂM KINH DOANH KHO BÁCH HÓA XANH',
            'BHX SỐ 12',
        ],
        'regex_negatives': [
            'Thế Giới Điện Tử',
        ],
    },
    'winmart': {
        'regex_positives': [
            'WinMart', 'WIN MART', 'Winmart+', 'WINMART', 'winmart',
            'Win Mart Store 1', 'WINMART Chi Nhanh',
        ],
        'regex_negatives': [
            'Winner Mart', 'Win Win', 'WINNING', 'Windex',
            'CO.OP FOOD', 'Bach Hoa Xanh',
        ],
    },
    'bao-tin-minh-chau': {
        # Root cause (2026-06-30): brand_regex contained the bare generic tokens
        # 'BẢO TÍN' / 'BAO TIN' / 'BTMC', matching any company whose name contains
        # the common Vietnamese words "Bảo Tín" (trust/guarantee) — tea, fashion,
        # finance, building-materials, etc. 195/224 (87%) of records were false
        # positives. Fix: require the distinctive "MINH CHÂU" token (mirrors
        # phu-quy's conjunctive gold-anchor pattern).
        'ingest_real': [
            'CÔNG TY TNHH VÀNG BẠC ĐÁ QUÝ BẢO TÍN MINH CHÂU',
            'ĐỊA ĐIỂM KINH DOANH SỐ 06 - CÔNG TY CỔ PHẦN VÀNG BẠC ĐÁ QUÝ BẢO TÍN MINH CHÂU',
            'CHI NHÁNH BẢO TÍN MINH CHÂU TẠI THÀNH PHỐ HỒ CHÍ MINH',
        ],
        'ingest_false_positives': [
            'CÔNG TY TNHH TRÀ BẢO TÍN',
            'CỬA HÀNG THỜI TRANG BẢO TÍN CƠ SỞ 2',
            'CÔNG TY TNHH ĐẦU TƯ TÀI CHÍNH BẢO TÍN',
            'CÔNG TY TNHH VLXD BẢO TÍN',
            'CÔNG TY CỔ PHẦN Y TẾ BẢO TÍN',
            'TRUNG TÂM LUYỆN THI - DẠY KÈM BẢO TÍN HÀ TU',
            'DOANH NGHIỆP TƯ NHÂN BẢO TÍN 3',
            'CÔNG TY TNHH MỘT THÀNH VIÊN BTMC',
        ],
    },
    'sjc': {
        # The bare 'VÀNG BẠC ĐÁ QUÝ SÀI GÒN' alternative matched other "Sài Gòn
        # …gold" firms (Sài Gòn Minh Châu, Kim Lộc Phát, Kim Hảo, Ngân Hà). Every
        # genuine SJC store carries the 'SJC' token, so the filter requires it.
        'ingest_real': [
            'CÔNG TY TNHH MỘT THÀNH VIÊN VÀNG BẠC ĐÁ QUÝ SÀI GÒN - SJC',
            'CỬA HÀNG NỮ TRANG SJC 19',
            'CÔNG TY CỔ PHẦN VÀNG BẠC ĐÁ QUÝ SJC PHÚ THỌ',
        ],
        'ingest_false_positives': [
            'CÔNG TY TNHH KINH DOANH VÀNG BẠC ĐÁ QUÝ SÀI GÒN MINH CHÂU',
            'DOANH NGHIỆP TƯ NHÂN KINH DOANH VÀNG BẠC ĐÁ QUÝ SÀI GÒN KIM LỘC PHÁT',
            'CHI NHÁNH CÔNG TY TNHH KINH DOANH VÀNG BẠC ĐÁ QUÝ SÀI GÒN KIM HẢO',
            'CỬA HÀNG TRANG SỨC CÔNG TY TNHH MỘT THÀNH VIÊN VÀNG BẠC ĐÁ QUÝ NGÂN HÀ',
        ],
    },
}


@pytest.fixture(params=sorted(BRANDS), ids=sorted(BRANDS))
def brand_case(request):
    slug = request.param
    if not config_yaml(slug).exists():
        pytest.skip(f'brand config removed: {slug}')
    return slug, BRANDS[slug]


def test_config_asserts(brand_case):
    slug, case = brand_case
    asserts = case.get('config_asserts')
    if not asserts:
        pytest.skip(f'{slug}: no config_asserts')
    brand_config = cfg.load(slug)
    assert brand_config.slug == slug
    if 'name' in asserts:
        assert brand_config.name == asserts['name']
    if 'seed_parent_msts_contains' in asserts:
        assert asserts['seed_parent_msts_contains'] in brand_config.seed_parent_msts


def test_regex_positives(brand_case):
    slug, case = brand_case
    positives = case.get('regex_positives')
    if not positives:
        pytest.skip(f'{slug}: no regex_positives')
    regex = cfg.load(slug).compiled_regex
    for text in positives:
        assert regex.search(text), f'{slug}: {text!r} should match but did not'


def test_regex_negatives(brand_case):
    slug, case = brand_case
    negatives = case.get('regex_negatives')
    if not negatives:
        pytest.skip(f'{slug}: no regex_negatives')
    regex = cfg.load(slug).compiled_regex
    for text in negatives:
        assert not regex.search(text), f'{slug}: {text!r} should NOT match but did'


def test_ingest_real_accepted(brand_case):
    slug, case = brand_case
    real = case.get('ingest_real')
    if not real:
        pytest.skip(f'{slug}: no ingest_real')
    brand_config = cfg.load(slug)
    for i, name in enumerate(real):
        ing = Ingester(brand_config)
        assert ing.ingest([make_row(str(i), name)]) == 1, f'{slug}: should accept: {name}'


def test_ingest_false_positives_rejected(brand_case):
    slug, case = brand_case
    false_positives = case.get('ingest_false_positives')
    if not false_positives:
        pytest.skip(f'{slug}: no ingest_false_positives')
    brand_config = cfg.load(slug)
    for i, name in enumerate(false_positives):
        ing = Ingester(brand_config)
        assert ing.ingest([make_row(str(i), name)]) == 0, f'{slug}: should REJECT: {name}'
