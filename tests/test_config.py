"""Tests for dkkd.config — BrandConfig.load and enrich."""
import json
import pytest
import yaml
from dkkd.config import BrandConfig, load, enrich


def _write_config_yaml(brand_path, data):
    """Helper: write config.yaml into a brand directory."""
    brand_path.mkdir(parents=True, exist_ok=True)
    cfg_path = brand_path / 'config.yaml'
    with open(cfg_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True)
    return cfg_path


def _write_discovered_json(brand_path, data):
    """Helper: write discovered.json into a brand directory."""
    brand_path.mkdir(parents=True, exist_ok=True)
    disc_path = brand_path / 'discovered.json'
    with open(disc_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return disc_path


# ── Task 3: BrandConfig.load two-layer merge ────────────────────────

class TestBrandConfigLoad:
    def test_load_with_both_files_list_union_dedup(self, tmp_path):
        """Lists union (dedup, order-preserving), scalar conflict → config.yaml wins."""
        slug = 'testbrand'
        brand_path = tmp_path / slug

        seed = {
            'slug': slug,
            'name': 'Test Brand Seed',
            'brand_regex': r'test\s*brand',
            'spelling_variants': ['TestBrand', 'Test-Brand'],
            'seed_parent_msts': ['MST001', 'MST002'],
            'default_store_type': 'Cửa hàng',
        }
        disc = {
            'name': 'Test Brand Discovered',  # scalar conflict → seed wins
            'spelling_variants': ['Test-Brand', 'TestBrand V2'],  # overlap + new
            'discovered_msts': ['MST002', 'MST003'],  # overlap with seed_parent_msts is ok, different field
        }

        _write_config_yaml(brand_path, seed)
        _write_discovered_json(brand_path, disc)

        cfg = load(slug, brands_dir=tmp_path)

        # Scalar: seed wins
        assert cfg.name == 'Test Brand Seed'
        assert cfg.brand_regex == r'test\s*brand'
        assert cfg.default_store_type == 'Cửa hàng'

        # Lists: union, deduped, order-preserving
        assert cfg.spelling_variants == ['TestBrand', 'Test-Brand', 'TestBrand V2']

        # seed_parent_msts from seed only
        assert cfg.seed_parent_msts == ['MST001', 'MST002']

        # discovered_msts from disc only
        assert cfg.discovered_msts == ['MST002', 'MST003']

        # all_parent_msts is seed + discovered, deduped
        assert cfg.all_parent_msts == ['MST001', 'MST002', 'MST003']

    def test_load_missing_discovered_json(self, tmp_path):
        """Missing discovered.json → seed only, no error."""
        slug = 'seedonly'
        brand_path = tmp_path / slug

        seed = {
            'slug': slug,
            'name': 'Seed Only',
            'brand_regex': r'seed',
            'seed_parent_msts': ['MST100'],
        }
        _write_config_yaml(brand_path, seed)

        cfg = load(slug, brands_dir=tmp_path)
        assert cfg.name == 'Seed Only'
        assert cfg.seed_parent_msts == ['MST100']
        assert cfg.discovered_msts == []
        assert cfg.all_parent_msts == ['MST100']

    def test_load_returns_brandconfig_dataclass(self, tmp_path):
        """Load returns a BrandConfig dataclass with all fields."""
        slug = 'fullfields'
        brand_path = tmp_path / slug

        seed = {
            'slug': slug,
            'name': 'Full Fields',
            'brand_regex': r'full',
            'spelling_variants': ['Full'],
            'seed_parent_msts': ['MST200'],
            'sibling_brands': ['other-brand'],
            'store_type_rules': [['.*mart.*', 'Siêu thị'], ['.*express.*', 'Cửa hàng']],
            'default_store_type': 'Cửa hàng',
        }
        _write_config_yaml(brand_path, seed)

        cfg = load(slug, brands_dir=tmp_path)
        assert isinstance(cfg, BrandConfig)
        assert cfg.slug == slug
        assert cfg.name == 'Full Fields'
        assert cfg.brand_regex == r'full'
        assert cfg.spelling_variants == ['Full']
        assert cfg.seed_parent_msts == ['MST200']
        assert cfg.sibling_brands == ['other-brand']
        assert cfg.store_type_rules == [('.*mart.*', 'Siêu thị'), ('.*express.*', 'Cửa hàng')]
        assert cfg.default_store_type == 'Cửa hàng'
        # compiled_regex property
        assert cfg.compiled_regex.pattern == r'full'


# ── Task 4: enrich ──────────────────────────────────────────────────

class TestEnrich:
    def test_enrich_appends_to_discovered_json(self, tmp_path):
        """enrich appends values to discovered.json only."""
        slug = 'enrichtest'
        brand_path = tmp_path / slug

        seed = {'slug': slug, 'name': 'Enrich Test', 'brand_regex': r'enrich'}
        _write_config_yaml(brand_path, seed)

        enrich(slug, 'spelling_variants', ['NEW VARIANT'], brands_dir=tmp_path)

        disc_path = brand_path / 'discovered.json'
        assert disc_path.exists()
        with open(disc_path, 'r', encoding='utf-8') as f:
            disc = json.load(f)
        assert disc['spelling_variants'] == ['NEW VARIANT']

    def test_enrich_does_not_touch_config_yaml(self, tmp_path):
        """config.yaml must be byte-unchanged after enrich."""
        slug = 'enrichyaml'
        brand_path = tmp_path / slug

        seed = {'slug': slug, 'name': 'YAML Unchanged', 'brand_regex': r'yaml'}
        cfg_path = _write_config_yaml(brand_path, seed)
        original_bytes = cfg_path.read_bytes()

        enrich(slug, 'discovered_msts', ['MST999'], brands_dir=tmp_path)

        assert cfg_path.read_bytes() == original_bytes

    def test_enrich_no_duplicate(self, tmp_path):
        """Re-enrich with same value → no duplicate."""
        slug = 'nodup'
        brand_path = tmp_path / slug

        seed = {'slug': slug, 'name': 'No Dup', 'brand_regex': r'nodup'}
        _write_config_yaml(brand_path, seed)

        enrich(slug, 'spelling_variants', ['VAR1'], brands_dir=tmp_path)
        enrich(slug, 'spelling_variants', ['VAR1', 'VAR2'], brands_dir=tmp_path)

        disc_path = brand_path / 'discovered.json'
        with open(disc_path, 'r', encoding='utf-8') as f:
            disc = json.load(f)
        assert disc['spelling_variants'] == ['VAR1', 'VAR2']

    def test_load_after_enrich_picks_up_values(self, tmp_path):
        """Load after enrich picks up the new values."""
        slug = 'loadenrich'
        brand_path = tmp_path / slug

        seed = {
            'slug': slug,
            'name': 'Load Enrich',
            'brand_regex': r'loadenrich',
            'seed_parent_msts': ['MST001'],
        }
        _write_config_yaml(brand_path, seed)

        enrich(slug, 'discovered_msts', ['MST002'], brands_dir=tmp_path)

        cfg = load(slug, brands_dir=tmp_path)
        assert 'MST002' in cfg.discovered_msts
        assert cfg.all_parent_msts == ['MST001', 'MST002']
