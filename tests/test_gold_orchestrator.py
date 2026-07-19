from dkkd.sectors.gold.orchestrator import cluster_by_parent_mst, filter_known_chains, generate_config_stub

def test_cluster_by_parent_mst_groups_branches():
    records = [
        {'Id': '1', 'Name': 'VÀNG ABC HÀ NỘI', 'Enterprise_Gdt_Code': '0123456789-001'},
        {'Id': '2', 'Name': 'VÀNG ABC ĐÀ NẴNG', 'Enterprise_Gdt_Code': '0123456789-002'},
        {'Id': '3', 'Name': 'VÀNG ABC HCM', 'Enterprise_Gdt_Code': '0123456789-003'},
        {'Id': '4', 'Name': 'VÀNG XYZ HẢI PHÒNG', 'Enterprise_Gdt_Code': '9876543210-001'},
    ]
    clusters = cluster_by_parent_mst(records)
    assert '0123456789' in clusters
    assert len(clusters['0123456789']) == 3
    assert '9876543210' in clusters
    assert len(clusters['9876543210']) == 1

def test_cluster_by_parent_mst_includes_parent_only():
    records = [
        {'Id': '1', 'Name': 'CÔNG TY VÀNG ABC', 'Enterprise_Gdt_Code': '0123456789'},
        {'Id': '2', 'Name': 'VÀNG ABC CN1', 'Enterprise_Gdt_Code': '0123456789-001'},
    ]
    clusters = cluster_by_parent_mst(records)
    assert '0123456789' in clusters
    assert len(clusters['0123456789']) == 2

def test_filter_known_chains():
    clusters = {
        '0123456789': [{'Id': '1'}, {'Id': '2'}, {'Id': '3'}],
        '9999999999': [{'Id': '4'}, {'Id': '5'}, {'Id': '6'}],
    }
    known_msts = {'9999999999'}
    candidates = filter_known_chains(clusters, known_msts, threshold=3)
    assert '0123456789' in candidates
    assert '9999999999' not in candidates

def test_filter_known_chains_threshold():
    clusters = {
        '0123456789': [{'Id': '1'}, {'Id': '2'}, {'Id': '3'}],
        '1111111111': [{'Id': '4'}, {'Id': '5'}],
    }
    candidates = filter_known_chains(clusters, set(), threshold=3)
    assert '0123456789' in candidates
    assert '1111111111' not in candidates

def test_generate_config_stub():
    records = [
        {'Id': '1', 'Name': 'CỬA HÀNG VÀNG ABC HÀ NỘI', 'Enterprise_Gdt_Code': '0123456789-001'},
        {'Id': '2', 'Name': 'VÀNG ABC ĐÀ NẴNG', 'Enterprise_Gdt_Code': '0123456789-002'},
        {'Id': '3', 'Name': 'VÀNG ABC HCM', 'Enterprise_Gdt_Code': '0123456789-003'},
    ]
    stub = generate_config_stub('0123456789', records)
    assert stub['slug'].startswith('discovered-')
    assert '0123456789' in stub['seed_parent_msts']
    assert len(stub['_discovery_metadata']['sample_names']) <= 5
