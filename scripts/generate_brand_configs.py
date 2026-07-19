"""Generate DKKD brand configs for brands in vn_retail_system.json.

Usage:
    python scripts/generate_brand_configs.py [--dry-run] [--sectors cosmetic,fitness,pharma] [--store-types drug_stores,...]

Reads vn_retail_system.json, filters to selected sectors/store types, and writes
brands/<sector>/<store_type>/<slug>/config.yaml for each brand that doesn't already exist.
"""
import json
import re
import unicodedata
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRANDS_DIR = PROJECT_ROOT / "brands"
JSON_SOURCE = PROJECT_ROOT / "vn_retail_system.json"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _strip_diacritics(text: str) -> str:
    """Remove Vietnamese diacritics, producing ASCII-folded form.

    Handles the đ/Đ → d/D rule before NFD decomposition (per project rules).
    Uses NFC normalization only — never NFKC or NFKD.
    """
    text = text.replace('đ', 'd').replace('Đ', 'D')
    # NFD to decompose, then strip combining marks, then NFC to recompose
    nfd = unicodedata.normalize('NFD', text)
    stripped = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return unicodedata.normalize('NFC', stripped)


def slugify(name: str) -> str:
    """Convert a brand name to a URL-safe slug.

    Rules:
      - Lowercase
      - đ/Đ → d/D, then strip all diacritics
      - Replace non-alphanumeric chars with hyphens
      - Collapse consecutive hyphens
      - Strip leading/trailing hyphens
    """
    s = _strip_diacritics(name.lower())
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def build_brand_regex(name: str) -> str:
    """Build a regex that matches the brand name in both diacriticked and ASCII forms.

    Returns a pipe-separated pattern: 'ORIGINAL_ESCAPED|ASCII_ESCAPED'.
    If the ASCII-folded form equals the original (no diacritics), returns just one.
    """
    escaped = re.escape(name)
    ascii_form = _strip_diacritics(name)
    ascii_escaped = re.escape(ascii_form)

    parts = [escaped]
    if ascii_escaped != escaped:
        parts.append(ascii_escaped)

    return '|'.join(parts)


def build_spelling_variants(name: str) -> list[str]:
    """Generate spelling variants: original, UPPER, lower, ASCII-folded versions.

    Returns a deduplicated list preserving insertion order.
    """
    ascii_name = _strip_diacritics(name)
    candidates = [
        name,
        name.upper(),
        name.lower(),
        ascii_name,
        ascii_name.upper(),
        ascii_name.lower(),
    ]
    # Deduplicate preserving order
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ---------------------------------------------------------------------------
# Config writer
# ---------------------------------------------------------------------------

def should_skip_brand(slug: str, brands_dir: Path) -> bool:
    """Return True if brands/<slug>/config.yaml already exists recursively."""
    # Check direct first
    if (brands_dir / slug / "config.yaml").exists():
        return True
    # Recursive check
    if brands_dir.exists():
        for p in brands_dir.rglob('config.yaml'):
            if p.parent.name == slug:
                return True
    return False


def write_brand_config(
    brand_entry: dict,
    sector: str,
    store_type: str,
    brands_dir: Path,
) -> dict:
    """Write a brand config.yaml for one brand.

    Args:
        brand_entry: dict with keys 'brand_name', 'parent_company', 'country_of_origin'
        sector: the sector string (e.g. 'cosmetic')
        store_type: the store_type string from the JSON (e.g. 'cosmetic_stores')
        brands_dir: path to the brands/ directory

    Returns:
        dict with 'slug', 'brand_name', 'sector', 'store_type', 'status' ('created' or 'skipped')
    """
    name = brand_entry["brand_name"]
    slug = slugify(name)

    result = {
        "slug": slug,
        "brand_name": name,
        "sector": sector,
        "store_type": store_type,
    }

    if should_skip_brand(slug, brands_dir):
        result["status"] = "skipped"
        result["reason"] = "config.yaml already exists"
        return result

    config = {
        "slug": slug,
        "name": name,
        "brand_regex": build_brand_regex(name),
        "spelling_variants": build_spelling_variants(name),
        "seed_parent_msts": [],
        "default_store_type": name,
    }

    # Write config.yaml
    brand_path = brands_dir / sector / store_type / slug
    brand_path.mkdir(parents=True, exist_ok=True)
    config_path = brand_path / "config.yaml"

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(f"# {name} — auto-generated from vn_retail_system.json ({sector} / {store_type})\n")
        yaml.dump(
            config,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    result["status"] = "created"
    return result


# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------

def load_brands(
    json_path: Path,
    sector_filter: list[str] | None = None,
    store_type_filter: list[str] | None = None,
) -> list[tuple[dict, str, str]]:
    """Load brands from vn_retail_system.json.

    Returns list of (brand_entry, sector, store_type) tuples.
    If sector_filter or store_type_filter is provided, only include those.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    brands = []
    for sector_data in data["sectors"]:
        sector = sector_data["sector"]
        if sector_filter and sector not in sector_filter:
            continue
        for st in sector_data["store_types"]:
            store_type = st["store_type"]
            if store_type_filter and store_type not in store_type_filter:
                continue
            for brand in st["brands"]:
                brands.append((brand, sector, store_type))

    return brands


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate DKKD brand configs from vn_retail_system.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without writing files",
    )
    parser.add_argument(
        "--sectors",
        type=str,
        default=None,
        help="Comma-separated list of sectors to include (default: all)",
    )
    parser.add_argument(
        "--store-types",
        type=str,
        default=None,
        help="Comma-separated list of store types to include (default: all)",
    )
    parser.add_argument(
        "--brands-dir",
        type=str,
        default=str(BRANDS_DIR),
        help=f"Path to brands directory (default: {BRANDS_DIR})",
    )
    parser.add_argument(
        "--json-source",
        type=str,
        default=str(JSON_SOURCE),
        help=f"Path to vn_retail_system.json (default: {JSON_SOURCE})",
    )
    args = parser.parse_args()

    json_path = Path(args.json_source)
    brands_dir = Path(args.brands_dir)
    sector_filter = args.sectors.split(',') if args.sectors else None
    store_type_filter = args.store_types.split(',') if args.store_types else None

    # Load brands
    all_brands = load_brands(json_path, sector_filter, store_type_filter)
    print(f"Found {len(all_brands)} brands to process")

    results = []
    created_count = 0
    skipped_count = 0

    for brand_entry, sector, store_type in all_brands:
        if args.dry_run:
            slug = slugify(brand_entry["brand_name"])
            skip = should_skip_brand(slug, brands_dir)
            status = "would_skip" if skip else "would_create"
            result = {
                "slug": slug,
                "brand_name": brand_entry["brand_name"],
                "sector": sector,
                "store_type": store_type,
                "status": status,
            }
        else:
            result = write_brand_config(brand_entry, sector, store_type, brands_dir)

        results.append(result)
        if "create" in result["status"]:
            created_count += 1
        else:
            skipped_count += 1

        # Print one-line status
        marker = "+" if "create" in result["status"] else ">"
        print(f"  {marker} {result['slug']:40s} [{sector:12s} / {store_type:20s}] {result['status']}")

    # Summary
    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Summary:")
    print(f"  Total:   {len(results)}")
    print(f"  Created: {created_count}")
    print(f"  Skipped: {skipped_count}")

    # Write manifest
    if not args.dry_run:
        manifest_dir = json_path.parent / "output"
        manifest_dir.mkdir(exist_ok=True)
        manifest_path = manifest_dir / "brand_manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    "source": str(json_path),
                    "total_brands": len(results),
                    "created": created_count,
                    "skipped": skipped_count,
                    "brands": results,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"\nManifest written to: {manifest_path}")


if __name__ == "__main__":
    main()
