"""Integration test: gold discovery pipeline with FakeTransport.

Verifies end-to-end: gold_discovery probes → engine sweep → cluster → filter → config stubs.
"""
import json
import tempfile
from pathlib import Path

import yaml

from dkkd.config import BrandConfig
from dkkd.sectors.gold.orchestrator import cluster_by_parent_mst, filter_known_chains, write_config_stubs
from dkkd.engine import DkkdEngine
from dkkd.records import SweepState
from dkkd.sectors.gold.discovery import gold_discovery
from tests.conftest import FakeTransport


def _build_fake_db() -> dict[str, list[dict]]:
    db = {}
    for i in range(1, 6):
        for keyword in ['VÀNG', 'VANG', 'KIM HOÀN', 'VÀNG HÀ NỘI', 'VÀNG ĐÀ NẴNG']:
            if keyword not in db:
                db[keyword] = []
            db[keyword].append({
                'Id': f'A{i}',
                'Name': f'VÀNG KIM THÀNH CHI NHÁNH {i}',
                'Enterprise_Gdt_Code': f'1111111111-{i:03d}',
                'Name_F': '',
            })

    for i in range(1, 4):
        for keyword in ['DOJI', 'VÀNG', 'VÀNG HỒ CHÍ MINH']:
            if keyword not in db:
                db[keyword] = []
            db[keyword].append({
                'Id': f'B{i}',
                'Name': f'DOJI CHI NHÁNH {i}',
                'Enterprise_Gdt_Code': f'2222222222-{i:03d}',
                'Name_F': '',
            })

    db.setdefault('VÀNG', []).append({
        'Id': 'C1',
        'Name': 'TIỆM VÀNG THANH TÙNG',
        'Enterprise_Gdt_Code': '3333333333',
        'Name_F': '',
    })

    return db

def test_full_discovery_pipeline():
    transport = FakeTransport(_build_fake_db())
    config = BrandConfig(
        slug='_gold_discovery',
        name='Gold Discovery',
        brand_regex='.',
        spelling_variants=[],
        seed_parent_msts=[],
    )

    state = SweepState(store_map={}, phase_history=[])
    probes = gold_discovery(config, state, {})
    assert len(probes) > 0

    engine = DkkdEngine(config, transport, throttle=False)
    engine.sweep(probes, 'gold_discovery')

    records = list(engine.store_map.values())
    assert len(records) > 0

    clusters = cluster_by_parent_mst(records)
    assert '1111111111' in clusters
    assert len(clusters['1111111111']) == 5

    known_msts = {'2222222222'}
    candidates = filter_known_chains(clusters, known_msts, threshold=3)
    assert '1111111111' in candidates
    assert '2222222222' not in candidates
    assert '3333333333' not in candidates

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        written = write_config_stubs(candidates, tmp_path)
        assert len(written) >= 1

        content = written[0].read_text(encoding='utf-8')
        yaml_lines = [line for line in content.split('\n') if not line.startswith('#')]
        stub = yaml.safe_load('\n'.join(yaml_lines))
        assert stub['seed_parent_msts'] == ['1111111111']
        assert len(stub['spelling_variants']) >= 1
