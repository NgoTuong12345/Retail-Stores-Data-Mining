"""Tests for the masothue.com URL-sweep operating-status strategy.

Covers:
- _name_to_slug: offline slug construction from DKKD Name / Name_F
- sweep_masothue_urls: Format B filtering + construct-and-verify loop
- fetch_masothue_statuses: Tình trạng / Ngày hoạt động extraction (active,
  ceased, and de-listed branches)
"""
from unittest.mock import MagicMock, patch

from dkkd.enrich_masothue import (
    _name_to_slug,
    sweep_masothue_urls,
    fetch_masothue_statuses,
)


# --- Real masothue.com HTML fragments (status cell only) ------------------
# Active branch: link text is plain
_HTML_ACTIVE = (
    "<tr><td><i class='fa fa-info'></i> Tình trạng</td>"
    "<td id='tax-status-html'><a "
    "href='/tra-cuu-ma-so-thue-theo-trang-thai-cong-ty/nnt-dang-hoat-dong-19' "
    "title='tra cứu mã số thuế công ty Đang hoạt động'>Đang hoạt động</a></td></tr>"
    "<tr><td>Ngày hoạt động</td><td><span itemprop='foundingDate'>2010-12-06</span></td></tr>"
)
# Ceased branch: link text wrapped in <span> (text-only capture would miss it)
_HTML_CEASED = (
    "<tr><td><i class='fa fa-info'></i> Tình trạng</td>"
    "<td id='tax-status-html'><a "
    "href='/tra-cuu-ma-so-thue-theo-trang-thai-cong-ty/nnt-ngung-hoat-dong-23' "
    "title='tra cứu mã số thuế công ty Ngừng hoạt động và đã hoàn thành thủ tục "
    "chấm dứt hiệu lực MST'><span class='badge'>Ngừng hoạt động và đã hoàn thành "
    "thủ tục chấm dứt hiệu lực MST</span></a></td></tr>"
    "<tr><td>Ngày hoạt động</td><td><span itemprop='foundingDate'>2010-12-23</span></td></tr>"
)
_HTML_OOPS = "<html><body>Dữ liệu bạn cần tìm không tồn tại :(</body></html>"


class TestNameToSlug:
    def test_folds_vietnamese_diacritics(self):
        slug = _name_to_slug('CỬA HÀNG SỐ 16 - CÔNG TY TNHH VÒNG TRÒN ĐỎ')
        assert slug == 'cua-hang-so-16-cong-ty-tnhh-vong-tron-do'

    def test_folds_d_stroke(self):
        # đ/Đ have no NFD decomposition — must map explicitly to d/D
        assert _name_to_slug('ĐỎ ĐEN') == 'do-den'

    def test_collapses_punctuation_runs(self):
        assert _name_to_slug('CHI NHÁNH  --  HÀ NỘI') == 'chi-nhanh-ha-noi'

    def test_empty_name(self):
        assert _name_to_slug('') == ''
        assert _name_to_slug(None) == ''


class TestSweepMasothueUrls:
    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_only_format_b_resolved(self, mock_get):
        resp = MagicMock(status_code=200, text=_HTML_ACTIVE)
        mock_get.return_value = resp

        stores = [
            {'Enterprise_Gdt_Code': '0306182043-001', 'Name': 'CỬA HÀNG SỐ 16'},
            {'Enterprise_Gdt_Code': '00036', 'Name': 'ĐỊA ĐIỂM A'},      # Format A — skip
            {'Enterprise_Gdt_Code': '', 'Name': 'NO CODE'},               # empty — skip
        ]
        url_map = sweep_masothue_urls(stores, delay=0)

        assert list(url_map.keys()) == ['0306182043-001']
        assert url_map['0306182043-001'] == '/0306182043-001-cua-hang-so-16'

    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_delisted_branch_not_added(self, mock_get):
        # 404 / Oops page → URL not retained
        mock_get.return_value = MagicMock(status_code=200, text=_HTML_OOPS)
        stores = [{'Enterprise_Gdt_Code': '0306182043-099', 'Name': 'CỬA HÀNG CŨ'}]
        url_map = sweep_masothue_urls(stores, delay=0)
        assert url_map == {}

    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_prefers_name_f_over_name(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text=_HTML_ACTIVE)
        stores = [{
            'Enterprise_Gdt_Code': '0306182043-001',
            'Name_F': 'CUA HANG SO 16',
            'Name': 'IGNORED UNICODE',
        }]
        url_map = sweep_masothue_urls(stores, delay=0)
        assert url_map['0306182043-001'] == '/0306182043-001-cua-hang-so-16'

    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_format_a_enterprise_code_resolved(self, mock_get):
        # Format A: 5-digit GDT but a 10-digit Enterprise_Code that does NOT
        # start with '00' — must still be attempted via the Enterprise_Code.
        mock_get.return_value = MagicMock(status_code=200, text=_HTML_ACTIVE)
        stores = [{
            'Enterprise_Gdt_Code': '00274',
            'Enterprise_Code': '0312056897',
            'Name': 'CỬA HÀNG SỐ 233',
        }]
        url_map = sweep_masothue_urls(stores, delay=0)
        assert url_map['0312056897'] == '/0312056897-cua-hang-so-233'

    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_seed_parent_mst_not_queried(self, mock_get):
        # A bare 10-digit Enterprise_Code equal to a seed parent MST must be
        # skipped — we never query the parent company as if it were a store.
        mock_get.return_value = MagicMock(status_code=200, text=_HTML_ACTIVE)
        stores = [{
            'Enterprise_Gdt_Code': '0306182043',
            'Enterprise_Code': '0306182043',
            'Name': 'CÔNG TY TNHH VÒNG TRÒN ĐỎ',
        }]
        url_map = sweep_masothue_urls(stores, delay=0, seed_parent_msts={'0306182043'})
        assert url_map == {}


class TestFetchMasothueStatuses:
    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_active_branch(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text=_HTML_ACTIVE)
        res = fetch_masothue_statuses({'0306182043-001': '/0306182043-001-x'}, delay=0)
        s = res['0306182043-001']
        assert s['tinh_trang'] == 'Đang hoạt động'
        assert s['is_active']
        assert not s['not_found']
        assert s['ngay_hd'] == '2010-12-06'

    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_ceased_branch_status_in_span(self, mock_get):
        # The status text lives inside a <span> — title-attr capture must still
        # return the clean status, not fall through to a later <a> (rep name).
        mock_get.return_value = MagicMock(status_code=200, text=_HTML_CEASED)
        res = fetch_masothue_statuses({'0306182043-003': '/0306182043-003-x'}, delay=0)
        s = res['0306182043-003']
        assert s['tinh_trang'] == 'Ngừng hoạt động và đã hoàn thành thủ tục chấm dứt hiệu lực MST'
        assert not s['is_active']

    @patch('dkkd.enrich_masothue.time.sleep', lambda *_: None)
    @patch('dkkd.enrich_masothue.requests.get')
    def test_delisted_branch_flagged_not_found(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404, text=_HTML_OOPS)
        res = fetch_masothue_statuses({'0306182043-099': '/0306182043-099-x'}, delay=0)
        s = res['0306182043-099']
        assert s['not_found']
        assert not s['is_active']
