from dkkd.reconcile import clean_address, extract_tower_code

def test_clean_address():
    addr = "Tầng trệt, Căn hộ S5.01, Nguyễn Xiển, Phường Long Thạnh Mỹ, Quận Thủ Đức, TP. Hồ Chí Minh"
    cleaned = clean_address(addr)
    # accents removed, stop words removed, synonyms mapped
    assert "floor1" in cleaned
    assert "s5 01" in cleaned or "s5.01" in cleaned or "s501" in cleaned
    assert "nguyen xien" in cleaned
    assert "phuong" not in cleaned
    assert "quan" not in cleaned

def test_extract_tower_code():
    assert extract_tower_code("S2.03 Vinhomes Grand Park") == "s2.03"
    assert extract_tower_code("Tòa Landmark 1") == "landmark1"
    assert extract_tower_code("Flora Mizuki Block MP2") == "mp2"


# --- Tax Code Matching Tests ---

import json
import pandas as pd
from pathlib import Path


def _make_checkpoint(records):
    """Helper: write a list of DKKD records as a checkpoint.json."""
    return [[i, r] for i, r in enumerate(records)]


def _test_matching_logic(crawled_rows, dkkd_records):
    """Test the core matching logic extracted from run_reconciliation."""
    from dkkd.reconcile import clean_address, extract_tower_code

    dkkd_list = []
    for r in dkkd_records:
        addr = r.get('Ho_Address', '')
        gdt = str(r.get('Enterprise_Gdt_Code') or '')
        dkkd_list.append({
            'record': r,
            'clean_addr': clean_address(addr),
            'tower': extract_tower_code(addr),
            'gdt': gdt,
            'enterprise_code': str(r.get('Enterprise_Code') or ''),
        })
    
    # Build indices (same as reconcile.py)
    gdt_code_index = {}
    gdt_counter_index = {}
    enterprise_code_index = {}
    for item in dkkd_list:
        gdt = item['gdt']
        ecode = item['enterprise_code']
        if gdt:
            gdt_code_index[gdt] = item
            if len(gdt) == 5 and gdt.isdigit():
                gdt_counter_index[gdt] = item
        if ecode:
            enterprise_code_index[ecode] = item
    
    return gdt_code_index, gdt_counter_index, enterprise_code_index


def test_format_b_branch_match():
    """Format B: hyphenated branch code like 0313330856-045 matches directly."""
    dkkd = [{'Id': '100', 'Enterprise_Code': '0313330856', 
             'Enterprise_Gdt_Code': '0313330856-045', 'Ho_Address': '37 Bùi Viện'}]
    gdt_idx, _, _ = _test_matching_logic([], dkkd)
    assert '0313330856-045' in gdt_idx
    assert gdt_idx['0313330856-045']['record']['Id'] == '100'


def test_format_a_counter_match():
    """Format A: 5-digit counter like 00202 is indexed for suffix matching."""
    dkkd = [{'Id': '200', 'Enterprise_Code': '0309129418',
             'Enterprise_Gdt_Code': '00202', 'Ho_Address': '100 Lý Tự Trọng'}]
    _, counter_idx, _ = _test_matching_logic([], dkkd)
    assert '00202' in counter_idx
    assert counter_idx['00202']['record']['Id'] == '200'


def test_parent_mst_fallback():
    """10-digit parent MST is indexed for parent fallback matching."""
    dkkd = [{'Id': '300', 'Enterprise_Code': '0313330856',
             'Enterprise_Gdt_Code': '', 'Ho_Address': '123 Nguyễn Huệ'}]
    _, _, ecode_idx = _test_matching_logic([], dkkd)
    assert '0313330856' in ecode_idx
    assert ecode_idx['0313330856']['record']['Id'] == '300'


def test_branch_records_not_excluded():
    """Regression: branch records (with hyphen in GDT code) must NOT be filtered out."""
    dkkd = [
        {'Id': '1', 'Enterprise_Code': '0313330856',
         'Enterprise_Gdt_Code': '0313330856-001', 'Ho_Address': 'addr1'},
        {'Id': '2', 'Enterprise_Code': '0313330856',
         'Enterprise_Gdt_Code': '0313330856-002', 'Ho_Address': 'addr2'},
        {'Id': '3', 'Enterprise_Code': '0313330856',
         'Enterprise_Gdt_Code': '00073', 'Ho_Address': 'addr3'},
    ]
    gdt_idx, counter_idx, _ = _test_matching_logic([], dkkd)
    # Branch records must be present
    assert '0313330856-001' in gdt_idx
    assert '0313330856-002' in gdt_idx
    # Counter record must also be present
    assert '00073' in counter_idx


def test_null_gdt_code_safe():
    """Records with None/null Enterprise_Gdt_Code must not crash."""
    dkkd = [{'Id': '400', 'Enterprise_Code': '0301234567',
             'Enterprise_Gdt_Code': None, 'Ho_Address': 'somewhere'}]
    gdt_idx, counter_idx, ecode_idx = _test_matching_logic([], dkkd)
    # Should not crash, and parent MST should still be indexed
    assert '0301234567' in ecode_idx


def test_reconciliation_finds_nested_brand_checkpoint(tmp_path):
    """Regression: a brand living under a nested category directory (e.g.
    brands/ICT/ict_stores/<slug>, like fpt-shop) must be found. The old
    checkpoint resolution only guessed brands/F&B/convenience_stores/<slug>
    and brands/<slug> relative to the CWD, missing this shape entirely."""
    from dkkd.reconcile import run_reconciliation

    brands_root = tmp_path / 'brands'
    brand_dir = brands_root / 'ICT' / 'ict_stores' / 'nested-brand'
    brand_dir.mkdir(parents=True)
    (brand_dir / 'config.yaml').write_text('slug: nested-brand\n', encoding='utf-8')

    dkkd_records = [{
        'Id': '1', 'Enterprise_Code': '0301234567',
        'Enterprise_Gdt_Code': '00001',
        'Ho_Address': '37 Bùi Viện, Phường 1, Quận 1, TP. Hồ Chí Minh',
        'Name': 'Test Store 1',
    }]
    with open(brand_dir / 'checkpoint.json', 'w', encoding='utf-8') as f:
        json.dump(_make_checkpoint(dkkd_records), f)

    crawled_path = tmp_path / 'crawled.csv'
    pd.DataFrame([{
        'store_code': 's1', 'store_name': 'Store 1',
        'new_address': '37 Bui Vien, P1, Q1, TPHCM',
        'old_address': '37 Bùi Viện, Phường 1, Quận 1, TP. Hồ Chí Minh',
    }]).to_csv(crawled_path, index=False)

    out_dir = tmp_path / 'out'
    run_reconciliation('nested-brand', crawled_path, out_dir, brands_dir=brands_root)

    mapping = pd.read_csv(out_dir / 'nested-brand_store_mapping.csv')
    assert mapping.iloc[0]['dkkd_id'] == 1
    assert mapping.iloc[0]['match_type'] == 'Unique'


def test_extract_house_numbers_range():
    from dkkd.reconcile import extract_house_numbers
    assert extract_house_numbers("416-418 Nguyễn Văn Nghi") == {"416", "418"}


def test_extract_house_numbers_single():
    from dkkd.reconcile import extract_house_numbers
    assert extract_house_numbers("37 Bùi Viện") == {"37"}


def test_extract_house_numbers_none():
    from dkkd.reconcile import extract_house_numbers
    assert extract_house_numbers("Chung cư Landmark 1") == set()


def test_house_number_range_matches_query_number_end_to_end(tmp_path):
    """Regression: DKKD range '416-418' must match a locator query for '418'
    (a single point inside the range) — this was a silent miss before the fix,
    measured live against a real FPT Shop locator crawl (87.1% recall)."""
    from dkkd.reconcile import run_reconciliation

    brands_root = tmp_path / 'brands'
    brand_dir = brands_root / 'range-brand'
    brand_dir.mkdir(parents=True)
    (brand_dir / 'config.yaml').write_text('slug: range-brand\n', encoding='utf-8')

    dkkd_records = [{
        'Id': '1', 'Enterprise_Code': '0301234567',
        'Enterprise_Gdt_Code': '00001',
        'Ho_Address': '416-418 Nguyễn Văn Nghi, Phường 7, Quận Gò Vấp, TP. Hồ Chí Minh',
        'Name': 'Test Store 1',
    }]
    with open(brand_dir / 'checkpoint.json', 'w', encoding='utf-8') as f:
        json.dump(_make_checkpoint(dkkd_records), f)

    crawled_path = tmp_path / 'crawled.csv'
    pd.DataFrame([{
        'store_code': 's1', 'store_name': 'Store 1',
        'new_address': '418 Nguyen Van Nghi, P7, Go Vap, TPHCM',
        'old_address': '418 Nguyễn Văn Nghi, Phường 7, Quận Gò Vấp, TP. Hồ Chí Minh',
    }]).to_csv(crawled_path, index=False)

    out_dir = tmp_path / 'out'
    run_reconciliation('range-brand', crawled_path, out_dir, brands_dir=brands_root)

    mapping = pd.read_csv(out_dir / 'range-brand_store_mapping.csv')
    assert mapping.iloc[0]['dkkd_id'] == 1


def test_reconciliation_report_shows_recall_and_below_target_warning(tmp_path):
    """Below-90% recall must be surfaced in the report: the recall figure and
    a warning that flags it as a known matcher-coverage gap, not a target to
    silently miss. 1 matched / 2 crawled = 50% recall here."""
    from dkkd.reconcile import run_reconciliation

    brands_root = tmp_path / 'brands'
    brand_dir = brands_root / 'ICT' / 'ict_stores' / 'low-recall-brand'
    brand_dir.mkdir(parents=True)
    (brand_dir / 'config.yaml').write_text('slug: low-recall-brand\n', encoding='utf-8')

    dkkd_records = [{
        'Id': '1', 'Enterprise_Code': '0301234567',
        'Enterprise_Gdt_Code': '00001',
        'Ho_Address': '37 Bùi Viện, Phường 1, Quận 1, TP. Hồ Chí Minh',
        'Name': 'Test Store 1',
    }]
    with open(brand_dir / 'checkpoint.json', 'w', encoding='utf-8') as f:
        json.dump(_make_checkpoint(dkkd_records), f)

    crawled_path = tmp_path / 'crawled.csv'
    pd.DataFrame([
        {
            'store_code': 's1', 'store_name': 'Store 1',
            'new_address': '37 Bui Vien, P1, Q1, TPHCM',
            'old_address': '37 Bùi Viện, Phường 1, Quận 1, TP. Hồ Chí Minh',
        },
        {
            'store_code': 's2', 'store_name': 'Store 2 (no match)',
            'new_address': '999 Hoang Sa, P Da Kao, Q1, TPHCM',
            'old_address': '999 Hoàng Sa, Phường Đa Kao, Quận 1, TP. Hồ Chí Minh',
        },
    ]).to_csv(crawled_path, index=False)

    out_dir = tmp_path / 'out'
    run_reconciliation('low-recall-brand', crawled_path, out_dir, brands_dir=brands_root)

    report = (out_dir / 'low-recall-brand_reconciliation_report.md').read_text(encoding='utf-8')
    assert '1/2' in report
    assert '50.0%' in report
    assert 'below the 90% design target' in report


def test_reconciliation_report_no_warning_when_recall_at_target(tmp_path):
    """Regression: the nested-brand scenario has 1/1 = 100% recall, so the
    below-target warning text must NOT appear in its report."""
    from dkkd.reconcile import run_reconciliation

    brands_root = tmp_path / 'brands'
    brand_dir = brands_root / 'ICT' / 'ict_stores' / 'nested-brand-2'
    brand_dir.mkdir(parents=True)
    (brand_dir / 'config.yaml').write_text('slug: nested-brand-2\n', encoding='utf-8')

    dkkd_records = [{
        'Id': '1', 'Enterprise_Code': '0301234567',
        'Enterprise_Gdt_Code': '00001',
        'Ho_Address': '37 Bùi Viện, Phường 1, Quận 1, TP. Hồ Chí Minh',
        'Name': 'Test Store 1',
    }]
    with open(brand_dir / 'checkpoint.json', 'w', encoding='utf-8') as f:
        json.dump(_make_checkpoint(dkkd_records), f)

    crawled_path = tmp_path / 'crawled.csv'
    pd.DataFrame([{
        'store_code': 's1', 'store_name': 'Store 1',
        'new_address': '37 Bui Vien, P1, Q1, TPHCM',
        'old_address': '37 Bùi Viện, Phường 1, Quận 1, TP. Hồ Chí Minh',
    }]).to_csv(crawled_path, index=False)

    out_dir = tmp_path / 'out'
    run_reconciliation('nested-brand-2', crawled_path, out_dir, brands_dir=brands_root)

    report = (out_dir / 'nested-brand-2_reconciliation_report.md').read_text(encoding='utf-8')
    assert '1/1' in report
    assert '100.0%' in report
    assert 'below the 90% design target' not in report

