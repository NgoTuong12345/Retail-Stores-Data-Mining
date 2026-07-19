"""TDD tests for dkkd.license_trends — pure MST distribution + growth curve."""
from dkkd.license_trends import group_by_mst, mst_distribution, mst_growth_curve


def _rec(id_, gdt=None, code=None, year=None):
    r = {'Id': id_}
    if gdt is not None:
        r['Enterprise_Gdt_Code'] = gdt
    if code is not None:
        r['Enterprise_Code'] = code
    if year is not None:
        r['Establishment_Year'] = year
    return r


# --- group_by_mst ---

def test_group_by_mst_groups_format_b_branches_under_parent():
    records = [
        _rec('1', gdt='1111111111-001'),
        _rec('2', gdt='1111111111-002'),
        _rec('3', gdt='2222222222-001'),
    ]
    groups = group_by_mst(records)
    assert set(groups.keys()) == {'1111111111', '2222222222'}
    assert len(groups['1111111111']) == 2
    assert len(groups['2222222222']) == 1


def test_group_by_mst_drops_unresolvable_records():
    records = [_rec('1', gdt='00036'), _rec('2', code='123')]
    groups = group_by_mst(records)
    assert groups == {}


def test_group_by_mst_falls_back_to_enterprise_code_for_format_a():
    records = [_rec('1', gdt='00036', code='3333333333')]
    groups = group_by_mst(records)
    assert set(groups.keys()) == {'3333333333'}


# --- mst_distribution ---

def test_mst_distribution_counts_single_vs_multi():
    records = [
        _rec('1', gdt='1111111111-001'),
        _rec('2', gdt='1111111111-002'),
        _rec('3', gdt='2222222222-001'),
    ]
    result = mst_distribution(records)
    assert result['single_store_msts'] == 1
    assert result['multi_store_msts'] == 1
    assert result['total_msts'] == 2
    assert result['total_stores'] == 3


def test_mst_distribution_top_msts_sorted_descending_and_capped():
    records = [
        _rec('1', gdt='1111111111-001'), _rec('2', gdt='1111111111-002'),
        _rec('3', gdt='1111111111-003'),
        _rec('4', gdt='2222222222-001'), _rec('5', gdt='2222222222-002'),
        _rec('6', gdt='3333333333-001'),
    ]
    result = mst_distribution(records, top_n=2)
    assert result['top_msts'] == [('1111111111', 3), ('2222222222', 2)]


def test_mst_distribution_ties_broken_by_mst_ascending():
    records = [_rec('1', gdt='2222222222-001'), _rec('2', gdt='1111111111-001')]
    result = mst_distribution(records, top_n=2)
    assert result['top_msts'] == [('1111111111', 1), ('2222222222', 1)]


def test_mst_distribution_empty_input_is_all_zero():
    result = mst_distribution([])
    assert result == {
        'single_store_msts': 0, 'multi_store_msts': 0,
        'total_msts': 0, 'total_stores': 0, 'top_msts': [],
    }


# --- mst_growth_curve ---

def test_mst_growth_curve_counts_per_year():
    records = [
        _rec('1', gdt='1111111111-001', year=2018),
        _rec('2', gdt='1111111111-002', year=2018),
        _rec('3', gdt='1111111111-003', year=2020),
    ]
    curve = mst_growth_curve(records, '1111111111')
    assert curve == {2018: 2, 2020: 1}


def test_mst_growth_curve_excludes_records_with_no_establishment_year():
    records = [
        _rec('1', gdt='1111111111-001', year=2018),
        _rec('2', gdt='1111111111-002'),
    ]
    curve = mst_growth_curve(records, '1111111111')
    assert curve == {2018: 1}


def test_mst_growth_curve_unknown_mst_returns_empty():
    records = [_rec('1', gdt='1111111111-001', year=2018)]
    assert mst_growth_curve(records, '9999999999') == {}
