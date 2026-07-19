import json
import tempfile
from pathlib import Path

from dkkd.sectors.gold.report import aggregate_chain_data, write_summary_csv, write_by_chain_csv

GOLD_SLUGS = ['pnj', 'doji', 'sjc']

def _setup_fake_brands(tmp: Path):
    for slug in GOLD_SLUGS:
        d = tmp / slug
        d.mkdir()
        (d / 'config.yaml').write_text(
            f'slug: {slug}\nname: {slug.upper()}\nbrand_regex: "{slug.upper()}"\n'
            f'spelling_variants: ["{slug.upper()}"]\nseed_parent_msts: []\n'
            f'default_store_type: "{slug.upper()} Store"\n',
            encoding='utf-8',
        )
        records = [
            [f'{slug}-{i}', {'Id': f'{slug}-{i}', 'Name': f'{slug.upper()} Store {i}',
                             'Enterprise_Gdt_Code': f'0123456789-{i:03d}'}]
            for i in range(1, 4)
        ]
        (d / 'checkpoint.json').write_text(json.dumps(records), encoding='utf-8')

def test_aggregate_chain_data():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _setup_fake_brands(tmp_path)
        data = aggregate_chain_data(GOLD_SLUGS, tmp_path)
        assert len(data) == 9
        assert all('_chain_slug' in r for r in data)

def test_write_summary_csv():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _setup_fake_brands(tmp_path)
        data = aggregate_chain_data(GOLD_SLUGS, tmp_path)
        out = tmp_path / 'summary.csv'
        write_summary_csv(data, out)
        assert out.exists()
        lines = out.read_text(encoding='utf-8-sig').strip().split('\n')
        assert len(lines) == 10

def test_write_by_chain_csv():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _setup_fake_brands(tmp_path)
        data = aggregate_chain_data(GOLD_SLUGS, tmp_path)
        out = tmp_path / 'by_chain.csv'
        write_by_chain_csv(data, GOLD_SLUGS, out)
        assert out.exists()
        lines = out.read_text(encoding='utf-8-sig').strip().split('\n')
        assert len(lines) == 4
