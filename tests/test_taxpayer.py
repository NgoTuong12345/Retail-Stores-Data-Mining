import json
import tempfile
import pathlib
from unittest.mock import MagicMock, patch
from dkkd.taxpayer import TaxpayerClient, load_status_cache, save_status_cache


def _write(tmp_path, entries):
    out = tmp_path / 'output'
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'masothue_store_statuses.json', 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False)
    return out


@patch('dkkd.taxpayer.output_dir')
def test_active_and_terminated_mapped(mock_out):
    with tempfile.TemporaryDirectory() as d:
        out = _write(pathlib.Path(d), {
            '0306182043-001': {'is_active': True, 'tinh_trang': 'Đang hoạt động', 'not_found': False},
            '0306182043-099': {'is_active': False, 'tinh_trang': 'Không tồn tại', 'not_found': True},
        })
        mock_out.return_value = out
        cache = load_status_cache('any')
        assert cache['0306182043-001']['status'] == 'NNT đang hoạt động'
        assert cache['0306182043-099']['status'] == 'Không tồn tại'


@patch('dkkd.taxpayer.output_dir')
def test_resolved_but_no_status_field_skipped(mock_out):
    # Format A địa điểm: page resolves but the status field is ad-gated →
    # empty tinh_trang, not terminated. Must NOT be mapped to ceased.
    with tempfile.TemporaryDirectory() as d:
        out = _write(pathlib.Path(d), {
            '0019190749': {'is_active': False, 'tinh_trang': '', 'not_found': False},
        })
        mock_out.return_value = out
        cache = load_status_cache('any')
        assert '0019190749' not in cache


@patch('requests.Session.get')
def test_query_taxpayer_status_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "mst": "0314658576", "tenNnt": "CONG TY GS25", "trangThai": "1", "trangThaiMoTa": "Đang hoạt động", "coQuanThue": "Cuc Thue HCMC"
    }
    mock_get.return_value = mock_resp

    client = TaxpayerClient()
    res = client.query_taxpayer_status("0314658576", ckey="captcha_key", cvalue="captcha_val")
    assert res is not None
    assert res['mst'] == "0314658576"
    assert res['status'] == "NNT đang hoạt động"
    assert res['name'] == "CONG TY GS25"
