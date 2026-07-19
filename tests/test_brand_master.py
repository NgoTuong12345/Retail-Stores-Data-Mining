"""Tests for dkkd.brand_master — overlay × config assembly."""
import yaml
from pathlib import Path

from dkkd import brand_master


def _brands_tree(root: Path):
    d = root / 'F&B' / 'mini_supermarket' / 'winmart'
    d.mkdir(parents=True)
    (d / 'config.yaml').write_text(yaml.safe_dump({'slug': 'winmart', 'name': 'WinMart',
        'brand_regex': 'WinMart', 'seed_parent_msts': ['0104918404']}), encoding='utf-8')
    return root


def test_vn_folder_only_brand_gets_folder_crosswalk_classification(tmp_path):
    """A brand's classification is derived purely from its
    brands/<industry>/<subsector>/ folder slug."""
    brands = _brands_tree(tmp_path / 'brands')  # winmart, F&B/mini_supermarket
    master = tmp_path / 'brand_master.yaml'
    master.write_text(yaml.safe_dump([]), encoding='utf-8')  # no curated overlay entry
    rows = brand_master.assemble_master_rows(brands_dir=brands, master_path=master)
    r = next(x for x in rows if x['brand_slug'] == 'winmart')
    assert r['retail_format'] == 'Small Local Grocers'
    assert r['channel_type'] == 'Retail'


def test_assemble_resolves_curated_overlay_and_folds_search(tmp_path):
    brands = _brands_tree(tmp_path / 'brands')
    master = tmp_path / 'brand_master.yaml'
    master.write_text(yaml.safe_dump([{'slug': 'winmart',
        'country_origin': 'Vietnam', 'domestic_foreign': 'Domestic',
        'owner_msts': {'0104918404': 'WinCommerce JSC'}}]), encoding='utf-8')

    rows = brand_master.assemble_master_rows(brands_dir=brands, master_path=master)
    r = next(x for x in rows if x['brand_slug'] == 'winmart')
    assert r['record_source'] == 'dkkd_master'
    assert r['industry'] == 'F&B' and r['subsector'] == 'mini_supermarket'
    assert r['nbo_is_local'] is True          # derived from domestic_foreign == 'Domestic'
    assert 'winmart' in r['search_blob'].lower()
    assert 'wincommerce' in r['search_blob'].lower()


def test_nbo_is_local_none_without_curated_domestic_foreign(tmp_path):
    brands = _brands_tree(tmp_path / 'brands')
    master = tmp_path / 'brand_master.yaml'
    master.write_text(yaml.safe_dump([]), encoding='utf-8')   # no curated overlay entry
    rows = brand_master.assemble_master_rows(brands_dir=brands, master_path=master)
    r = next(x for x in rows if x['brand_slug'] == 'winmart')
    assert r['nbo_is_local'] is None


def test_assemble_curated_entities_from_owner_msts(tmp_path):
    master = tmp_path / 'brand_master.yaml'
    master.write_text(yaml.safe_dump([{'slug': 'winmart',
        'owner_msts': {'0104918404': 'WinCommerce JSC'}}]), encoding='utf-8')

    companies, bridge = brand_master.assemble_curated_entities(master_path=master)
    assert companies == [('0104918404', 'WinCommerce JSC')]
    assert bridge == [('winmart', '0104918404', 'owner_curated', None)]


def test_assemble_curated_entities_no_overlay_is_empty(tmp_path):
    companies, bridge = brand_master.assemble_curated_entities(master_path=tmp_path / 'missing.yaml')
    assert companies == [] and bridge == []


def test_assemble_curated_entities_rejects_unquoted_octal_mst(tmp_path):
    """An unquoted owner_msts key like 0301234567 (all digits 0-7) parses as
    a YAML 1.1 octal int, silently becoming a different number — must fail
    loud instead of building a company row under the wrong mst."""
    master = tmp_path / 'brand_master.yaml'
    master.write_text(
        "- slug: coop-food\n  owner_msts:\n    0301234567: Some Owner\n",  # unquoted
        encoding='utf-8',
    )
    try:
        brand_master.assemble_curated_entities(master_path=master)
        assert False, "expected ValueError"
    except ValueError as e:
        assert 'owner_msts' in str(e)


def test_real_overlay_is_consistent():
    """Guards brands/_master/brand_master.yaml against curation rot: every
    slug must exist under brands/, and slugs must be unique.
    """
    overlay = brand_master.load_overlay()
    raw = yaml.safe_load(brand_master.DEFAULT_MASTER_PATH.read_text(encoding='utf-8')) or []
    slugs = [r['slug'] for r in raw]
    assert len(slugs) == len(set(slugs)), "duplicate slugs in brand_master.yaml"
    for slug in overlay:
        matches = list(brand_master.DEFAULT_BRANDS_DIR.glob(f"*/*/{slug}/config.yaml"))
        assert matches, f"{slug} (in brand_master.yaml) has no brands/*/*/{slug}/config.yaml"
