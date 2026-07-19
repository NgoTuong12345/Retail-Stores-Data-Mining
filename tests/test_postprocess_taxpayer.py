import pytest
from unittest.mock import patch
from dkkd.postprocess import run_pipeline
from dkkd.config import BrandConfig

@patch('dkkd.postprocess.load_config')
@patch('dkkd.postprocess._load_stores')
@patch('dkkd.postprocess.load_status_cache')
def test_postprocess_falls_back_to_gdt_cache(mock_cache, mock_load, mock_cfg, tmp_path):
    mock_cfg.return_value = BrandConfig(
        slug='gs25', name='GS25', brand_regex='GS25',
        classification={}, seed_parent_msts=['0314658576']
    )
    mock_load.return_value = [
        {'Id': '1', 'Enterprise_Gdt_Code': '0314658576', 'Name': 'GS25 Store'}
    ]
    mock_cache.return_value = {
        '0314658576': {'status': 'NNT tạm nghỉ kinh doanh'}
    }
    
    (tmp_path / 'gs25').mkdir(parents=True, exist_ok=True)
    summary = run_pipeline('gs25', brands_dir=tmp_path, skip_date_calibration=True)
    assert summary is not None
    # Verify the status was set from the GDT cache fallback
    assert mock_load.return_value[0]['Status'] == 'NNT tạm nghỉ kinh doanh'
