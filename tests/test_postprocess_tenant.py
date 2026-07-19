# tests/test_postprocess_tenant.py
"""Integration: tenant tagging + host_effectiveness rollup through run_pipeline.

Mirrors tests/test_postprocess_3state.py's mock setup.
"""
import csv
from unittest.mock import patch

from dkkd.postprocess import run_pipeline
from dkkd.config import BrandConfig


def _config():
    return BrandConfig(
        slug='coop-extra', name='Coop-Extra',
        brand_regex=r'CO[\.\\\,\-]?\s*OP\s*XTRA|COOPXTRA',
        seed_parent_msts=['0301175691'],
        classification={'tenant_separation': {'enabled': True}, 'corporate_keywords': []},
    )


@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_pipeline_tags_roles_and_writes_rollup(mock_pins, mock_cache, mock_load, mock_cfg, tmp_path):
    mock_cfg.return_value = _config()
    mock_load.return_value = [
        {'Id': '3412393', 'Enterprise_Gdt_Code': '00003', 'Enterprise_Code': '0014819878',
         'Name': 'THỦ ĐỨC CO-OP XTRA', 'Name_F': 'THU DUC CO-OP XTRA',
         'Ho_Address': 'Số 934 Quốc lộ 1A, Phường Linh Xuân, TP.HCM'},
        {'Id': '7214637', 'Enterprise_Gdt_Code': '00017', 'Enterprise_Code': '0022758357',
         'Name': 'GIAN HÀNG FRICO – CO.OP XTRA - CÔNG TY TNHH COOKMIX', 'Name_F': '',
         'Ho_Address': 'Tầng hầm CO.OP XTRA Sư Vạn Hạnh, Số 11 Sư Vạn Hạnh, Quận 10'},
        {'Id': '227839', 'Enterprise_Gdt_Code': '0309453012-002', 'Enterprise_Code': '0002514524',
         'Name': 'CHI NHÁNH CÔNG TY TNHH ĐẠI THẾ GIỚI', 'Name_F': '',
         'Ho_Address': 'L1-05, Co.op Mart Vũng tàu, Vũng Tàu'},
    ]
    mock_cache.return_value = {'0301175691': {'status': 'NNT đang hoạt động'}}
    mock_pins.return_value = {}

    out_dir = tmp_path / 'coop-extra' / 'output'
    out_dir.mkdir(parents=True)

    run_pipeline('coop-extra', brands_dir=tmp_path, skip_date_calibration=True)

    stores = mock_load.return_value
    roles = {s['Id']: s['store_role'] for s in stores}
    assert roles == {'3412393': 'own_store', '7214637': 'in_brand_tenant', '227839': 'unrelated'}

    he_path = out_dir / 'coop-extra_host_effectiveness.csv'
    assert he_path.exists(), 'host_effectiveness.csv must be written for opt-in brand'
    with open(he_path, encoding='utf-8-sig') as f:
        he_rows = list(csv.DictReader(f))
    assert len(he_rows) == 1
    assert 'Sư Vạn Hạnh' in he_rows[0]['host_store']
    assert he_rows[0]['tenant_count'] == '1'

    schema_path = out_dir / 'coop-extra_standard_schema.csv'
    with open(schema_path, encoding='utf-8-sig') as f:
        assert 'store_role' in csv.DictReader(f).fieldnames


@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
@patch('dkkd.postprocess.load_locator_pins')
def test_pipeline_skips_rollup_when_disabled(mock_pins, mock_cache, mock_load, mock_cfg, tmp_path):
    cfg = _config()
    cfg.classification['tenant_separation']['enabled'] = False
    mock_cfg.return_value = cfg
    mock_load.return_value = [
        {'Id': '1', 'Enterprise_Gdt_Code': '0301175691-001', 'Enterprise_Code': '',
         'Name': 'CO.OPXTRA X', 'Name_F': '', 'Ho_Address': 'Q1'},
    ]
    mock_cache.return_value = {'0301175691': {'status': 'NNT đang hoạt động'}}
    mock_pins.return_value = {}
    out_dir = tmp_path / 'coop-extra' / 'output'
    out_dir.mkdir(parents=True)

    run_pipeline('coop-extra', brands_dir=tmp_path, skip_date_calibration=True)

    assert not (out_dir / 'coop-extra_host_effectiveness.csv').exists()
    assert mock_load.return_value[0]['store_role'] == 'own_store'
