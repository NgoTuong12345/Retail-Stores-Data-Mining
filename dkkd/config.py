"""Brand configuration: two-layer merge of config.yaml + discovered.json."""
from dataclasses import dataclass, field
import json
import re
from pathlib import Path
import yaml

from dkkd.paths import brand_dir, config_yaml, discovered_json

_LIST_FIELDS = ('spelling_variants', 'seed_parent_msts', 'discovered_msts',
                'sibling_brands', 'corporate_names')

# Default corporate keywords used when no classification.corporate_keywords is set.
# These identify warehouses, HQs, logistics, online ops, etc.
DEFAULT_CORPORATE_KEYWORDS = [
    'KHO',
    'VĂN PHÒNG',
    'VP',
    'VPĐD',
    'VP ĐẠI DIỆN',
    'VĂN PHÒNG ĐẠI DIỆN',
    'TRUNG TÂM PHÂN PHỐI',
    'LOGISTICS',
    'TRẠM TRUNG CHUYỂN',
    'BẢO HÀNH',
    'TRUNG TÂM ĐIỀU HÀNH',
    'HỘI SỞ',
    'ONLINE',
    'TRỰC TUYẾN',
    'HẬU CẦN',
    'TỔNG KHO',
    'KHO TỔNG',
    'KHO LẠNH',
    'KHO TRUNG TÂM',
    'VẬN TẢI',
    'VẬN CHUYỂN',
    'GIAO NHẬN',
    'CHĂM SÓC KHÁCH HÀNG',
    'CUSTOMER SERVICE',
]


@dataclass
class BrandConfig:
    slug: str
    name: str
    brand_regex: str
    spelling_variants: list[str] = field(default_factory=list)
    seed_parent_msts: list[str] = field(default_factory=list)
    discovered_msts: list[str] = field(default_factory=list)
    sibling_brands: list[str] = field(default_factory=list)
    corporate_names: list[str] = field(default_factory=list)
    store_type_rules: list[tuple[str, str]] = field(default_factory=list)
    default_store_type: str = ''
    classification: dict = field(default_factory=dict)
    backtest: dict = field(default_factory=dict)

    @property
    def compiled_regex(self) -> re.Pattern:
        return re.compile(self.brand_regex, re.IGNORECASE)

    @property
    def all_parent_msts(self) -> list[str]:
        """Union of seed + discovered MSTs, order-preserving dedup."""
        return _dedup_list(self.seed_parent_msts + self.discovered_msts)


def _dedup_list(items: list) -> list:
    """Order-preserving deduplication."""
    return list(dict.fromkeys(items))


def _merge_lists(base: list, overlay: list) -> list:
    """Union two lists, order-preserving, deduped."""
    return _dedup_list(base + overlay)


def load(slug: str, brands_dir: Path | None = None) -> BrandConfig:
    """Load a BrandConfig by merging config.yaml (authoritative) + discovered.json (additive)."""
    cfg_path = config_yaml(slug, brands_dir)
    disc_path = discovered_json(slug, brands_dir)

    with open(cfg_path, 'r', encoding='utf-8') as f:
        seed = yaml.safe_load(f) or {}

    disc = {}
    if disc_path.exists():
        with open(disc_path, 'r', encoding='utf-8') as f:
            disc = json.load(f) or {}

    # Merge: scalars → seed wins; lists → union
    merged = {}
    all_keys = set(list(seed.keys()) + list(disc.keys()))
    for key in all_keys:
        s_val = seed.get(key)
        d_val = disc.get(key)
        if key in _LIST_FIELDS:
            merged[key] = _merge_lists(s_val or [], d_val or [])
        elif s_val is not None:
            merged[key] = s_val  # seed wins on scalar conflict
        else:
            merged[key] = d_val

    # Handle store_type_rules specially (list of [regex, label] pairs)
    str_rules = merged.pop('store_type_rules', []) or []
    store_type_rules = [(r[0], r[1]) for r in str_rules] if str_rules else []

    return BrandConfig(
        slug=merged.get('slug', slug),
        name=merged.get('name', ''),
        brand_regex=merged.get('brand_regex', ''),
        spelling_variants=merged.get('spelling_variants', []),
        seed_parent_msts=merged.get('seed_parent_msts', []),
        discovered_msts=merged.get('discovered_msts', []),
        sibling_brands=merged.get('sibling_brands', []),
        corporate_names=merged.get('corporate_names', []),
        store_type_rules=store_type_rules,
        default_store_type=merged.get('default_store_type', ''),
        classification=merged.get('classification', {}),
        backtest=merged.get('backtest', {}),
    )


def enrich(slug: str, key: str, values: list, brands_dir: Path | None = None) -> None:
    """Append values to discovered.json only. config.yaml is never touched."""
    disc_path = discovered_json(slug, brands_dir)
    disc = {}
    if disc_path.exists():
        with open(disc_path, 'r', encoding='utf-8') as f:
            disc = json.load(f) or {}

    existing = disc.get(key, [])
    disc[key] = _dedup_list(existing + list(values))

    disc_path.parent.mkdir(parents=True, exist_ok=True)
    with open(disc_path, 'w', encoding='utf-8') as f:
        json.dump(disc, f, ensure_ascii=False, indent=2)
