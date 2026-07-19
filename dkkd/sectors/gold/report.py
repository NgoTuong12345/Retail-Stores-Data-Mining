"""Consolidated gold sector report generator.

Aggregates data from all gold chain brand checkpoints into:
  - gold_sector_summary.csv — one row per store across all chains
  - gold_sector_by_chain.csv — chain-level summary
"""
import csv
import json
from collections import Counter
from pathlib import Path

from dkkd.paths import DEFAULT_BRANDS_DIR, checkpoint_json

# Known gold chain slugs (updated as new chains are added)
GOLD_CHAIN_SLUGS = [
    'pnj', 'doji', 'sjc', 'bao-tin-minh-chau', 'phu-quy',
    'mi-hong', 'cao-fine-jewellery', 'precita', 'jemmia',
]


def aggregate_chain_data(
    slugs: list[str] | None = None,
    brands_dir: Path | None = None,
) -> list[dict]:
    """Load and merge checkpoint data from all gold chains.

    Each record is augmented with '_chain_slug' and '_chain_name' fields.
    """
    slugs = slugs or GOLD_CHAIN_SLUGS
    brands_dir = brands_dir or DEFAULT_BRANDS_DIR
    all_records: list[dict] = []

    for slug in slugs:
        cp_path = checkpoint_json(slug, brands_dir)
        if not cp_path.exists():
            continue

        with open(cp_path, 'r', encoding='utf-8') as f:
            pairs = json.load(f)

        for item in pairs:
            record = item[1] if isinstance(item, list) else item
            if record.get('Core_Operating_Store') == 'No':
                continue
            record['_chain_slug'] = slug
            record['_chain_name'] = slug.replace('-', ' ').title()
            all_records.append(record)

    return all_records


def write_summary_csv(records: list[dict], output_path: Path) -> None:
    """Write one-row-per-store summary CSV."""
    if not records:
        output_path.write_text('', encoding='utf-8-sig')
        return

    # Determine fieldnames: _chain fields first, then original fields
    chain_fields = ['_chain_slug', '_chain_name']
    original_fields = [k for k in records[0].keys() if k not in chain_fields]
    fieldnames = chain_fields + original_fields

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)


def write_by_chain_csv(
    records: list[dict],
    slugs: list[str],
    output_path: Path,
) -> None:
    """Write chain-level summary CSV."""
    chain_counts: Counter = Counter()
    for r in records:
        chain_counts[r.get('_chain_slug', 'unknown')] += 1

    fieldnames = ['chain_slug', 'chain_name', 'total_stores']
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for slug in slugs:
            writer.writerow({
                'chain_slug': slug,
                'chain_name': slug.replace('-', ' ').title(),
                'total_stores': chain_counts.get(slug, 0),
            })


def generate_gold_report(
    brands_dir: Path | None = None,
    fmt: str = 'csv',
) -> list[Path]:
    """Generate consolidated gold sector reports. Returns list of output file paths."""
    brands_dir = brands_dir or DEFAULT_BRANDS_DIR
    output = brands_dir.parent / 'output'
    output.mkdir(parents=True, exist_ok=True)

    # Discover all gold chains (known + discovered)
    slugs = list(GOLD_CHAIN_SLUGS)
    discovered_dir = brands_dir / '_discovered'
    if discovered_dir.exists():
        for f in discovered_dir.iterdir():
            if f.suffix == '.yaml':
                slug = f.stem
                if slug not in slugs:
                    slugs.append(slug)

    records = aggregate_chain_data(slugs, brands_dir)
    paths = []

    if fmt == 'csv':
        summary_path = output / 'gold_sector_summary.csv'
        write_summary_csv(records, summary_path)
        paths.append(summary_path)

        by_chain_path = output / 'gold_sector_by_chain.csv'
        write_by_chain_csv(records, slugs, by_chain_path)
        paths.append(by_chain_path)
    elif fmt == 'json':
        json_path = output / 'gold_sector_summary.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        paths.append(json_path)

    return paths
