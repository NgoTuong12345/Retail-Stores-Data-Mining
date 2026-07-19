"""Discovery orchestrator: run gold_discovery sweep, cluster, filter, generate config stubs.

This module is NOT a strategy — it orchestrates the full discovery workflow:
1. Run gold_discovery strategy probes through the engine
2. Cluster raw results by parent MST
3. Filter out known chains and below-threshold clusters
4. Generate config.yaml stubs for candidate chains
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

from dkkd.utils import parse_gdt


def cluster_by_parent_mst(records: list[dict]) -> dict[str, list[dict]]:
    """Group records by parent MST extracted from Enterprise_Gdt_Code.

    Handles both branch-format ('MST-NNN') and bare parent ('MST') codes.
    Records with counter-format (5-digit) or empty codes are skipped.
    """
    clusters: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        gdt = r.get('Enterprise_Gdt_Code') or ''
        parsed = parse_gdt(gdt)
        if parsed['format'] == 'branch':
            clusters[parsed['parent_mst']].append(r)
        elif parsed['format'] == 'other' and re.match(r'^\d{10}$', gdt):
            # Bare 10-digit MST = parent entity registration
            clusters[gdt].append(r)
    return dict(clusters)


def filter_known_chains(
    clusters: dict[str, list[dict]],
    known_msts: set[str],
    threshold: int = 3,
) -> dict[str, list[dict]]:
    """Filter clusters: remove known chains, apply branch count threshold.

    Args:
        clusters: MST → list of records
        known_msts: set of parent MSTs belonging to already-configured brands
        threshold: minimum branch count to qualify as a chain candidate

    Returns:
        Filtered dict of candidate chains.
    """
    candidates = {}
    for mst, records in clusters.items():
        if mst in known_msts:
            continue
        if len(records) >= threshold:
            candidates[mst] = records
    return candidates


def _extract_brand_name(records: list[dict]) -> str:
    """Extract the most common multi-word token from Name fields as candidate brand name.

    Heuristic: split each Name into bigrams, find the most frequent bigram
    that isn't a generic word (CÔNG TY, CHI NHÁNH, CỬA HÀNG, etc.).
    Falls back to the first 3 words of the most common Name.
    """
    generic = {
        'CÔNG TY', 'CHI NHÁNH', 'CỬA HÀNG', 'TNHH', 'MTV', 'CỔ PHẦN',
        'DOANH NGHIỆP', 'TƯ NHÂN', 'HỘ KINH', 'KINH DOANH',
        'VÀNG BẠC', 'ĐÁ QUÝ', 'TRANG SỨC', 'KIM HOÀN',
    }
    from collections import Counter
    bigram_counts: Counter = Counter()
    for r in records:
        name = (r.get('Name') or '').upper().strip()
        words = name.split()
        for i in range(len(words) - 1):
            bg = f'{words[i]} {words[i + 1]}'
            if bg not in generic:
                bigram_counts[bg] += 1

    if bigram_counts:
        best_bigram = bigram_counts.most_common(1)[0][0]
        return best_bigram

    # Fallback: first 3 words of most common Name
    name_counts: Counter = Counter()
    for r in records:
        name_counts[(r.get('Name') or '').upper().strip()] += 1
    if name_counts:
        most_common_name = name_counts.most_common(1)[0][0]
        return ' '.join(most_common_name.split()[:3])

    return 'UNKNOWN'


def generate_config_stub(mst: str, records: list[dict]) -> dict:
    """Generate a config.yaml-compatible dict for a discovered chain candidate.

    Returns a dict with config fields plus '_discovery_metadata' for review.
    """
    brand_name = _extract_brand_name(records)
    slug = 'discovered-' + re.sub(r'[^a-z0-9]+', '-', brand_name.lower()).strip('-')

    sample_names = [r.get('Name', '') for r in records[:5]]

    return {
        'slug': slug,
        'name': brand_name.title(),
        'brand_regex': re.escape(brand_name),
        'spelling_variants': [brand_name],
        'seed_parent_msts': [mst],
        'default_store_type': brand_name.title(),
        '_discovery_metadata': {
            'parent_mst': mst,
            'branch_count': len(records),
            'sample_names': sample_names,
        },
    }


def write_config_stubs(
    candidates: dict[str, list[dict]],
    output_dir: Path,
) -> list[Path]:
    """Write config.yaml stubs for each candidate chain. Returns list of written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for mst, records in candidates.items():
        stub = generate_config_stub(mst, records)
        meta = stub.pop('_discovery_metadata')

        # Write YAML with metadata as comments
        slug = stub['slug']
        out_path = output_dir / f'{slug}.yaml'

        lines = [
            f'# AUTO-DISCOVERED — review before running',
            f'# Parent MST: {meta["parent_mst"]}',
            f'# Branch count: {meta["branch_count"]}',
            f'# Sample names:',
        ]
        for sn in meta['sample_names']:
            lines.append(f'#   - {sn}')
        lines.append('')

        yaml_content = yaml.dump(stub, allow_unicode=True, default_flow_style=False, sort_keys=False)
        content = '\n'.join(lines) + yaml_content

        out_path.write_text(content, encoding='utf-8')
        written.append(out_path)

    return written


def run_discovery(
    transport=None,
    brands_dir: Path | None = None,
    threshold: int = 3,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Full discovery pipeline: sweep → cluster → filter → generate stubs.

    Args:
        transport: Injected transport (None → RequestsTransport)
        brands_dir: Override brands directory
        threshold: Min branches for chain candidate (default 3)
        output_dir: Where to write config stubs (default: brands/_discovered/)
        dry_run: If True, don't write files

    Returns:
        Summary dict with counts and candidate info.
    """
    from dkkd.config import BrandConfig, load
    from dkkd.engine import DkkdEngine
    from dkkd.paths import DEFAULT_BRANDS_DIR
    from dkkd.strategies import get as get_strategy

    brands_dir = brands_dir or DEFAULT_BRANDS_DIR
    output_dir = output_dir or (brands_dir / '_discovered')

    if transport is None:
        from dkkd.transport import RequestsTransport
        transport = RequestsTransport()

    # Create a permissive config for discovery (accept all results)
    discovery_config = BrandConfig(
        slug='_gold_discovery',
        name='Gold Discovery',
        brand_regex='.',  # Match everything
        spelling_variants=[],
        seed_parent_msts=[],
    )

    engine = DkkdEngine(discovery_config, transport, brands_dir=brands_dir)
    strategy_fn = get_strategy('gold_discovery')
    from dkkd.records import SweepState
    state = SweepState(store_map={}, phase_history=[])
    probes = strategy_fn(discovery_config, state, {})

    print(f'Running gold discovery: {len(probes)} probes...')
    engine.sweep(probes, 'gold_discovery')

    raw_records = list(engine.store_map.values())
    print(f'Collected {len(raw_records)} unique records')

    # Cluster by parent MST
    clusters = cluster_by_parent_mst(raw_records)
    print(f'Clustered into {len(clusters)} parent MSTs')

    # Collect known chain MSTs from existing brand configs
    known_msts: set[str] = set()
    if brands_dir.exists():
        for d in brands_dir.iterdir():
            if d.is_dir() and (d / 'config.yaml').exists() and d.name != '_discovered':
                try:
                    brand_cfg = load(d.name, brands_dir)
                    known_msts.update(brand_cfg.all_parent_msts)
                except Exception:
                    pass

    candidates = filter_known_chains(clusters, known_msts, threshold)
    print(f'{len(candidates)} candidate chains (>={threshold} branches) after filtering')

    written = []
    if not dry_run and candidates:
        written = write_config_stubs(candidates, output_dir)
        print(f'Config stubs written to {output_dir}/')

    return {
        'total_records': len(raw_records),
        'total_clusters': len(clusters),
        'known_msts_filtered': len(known_msts),
        'candidates': len(candidates),
        'candidate_details': {
            mst: {
                'branch_count': len(recs),
                'sample_name': (recs[0].get('Name') or '') if recs else '',
            }
            for mst, recs in candidates.items()
        },
        'stubs_written': [str(p) for p in written],
    }
