"""Brand-slug → filesystem path resolution."""
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for p in (start, *start.parents):
        if (p / ".git").exists():
            return p
    return start


PACKAGE_ROOT = Path(__file__).resolve().parent.parent   # repo root
REPO_ROOT = _find_repo_root(PACKAGE_ROOT)                 # repo root

DEFAULT_BRANDS_DIR = PACKAGE_ROOT / 'brands'

def brand_dir(slug: str, brands_dir: Path | None = None) -> Path:
    base = brands_dir or DEFAULT_BRANDS_DIR
    # Try direct base / slug first (fast path & backwards compatibility)
    direct = base / slug
    if (direct / 'config.yaml').exists():
        return direct
    # Recursive search for a folder containing config.yaml that matches the slug
    if base.exists():
        for p in base.rglob('config.yaml'):
            if p.parent.name == slug:
                return p.parent
    return direct

def config_yaml(slug: str, brands_dir: Path | None = None) -> Path:
    return brand_dir(slug, brands_dir) / 'config.yaml'

def discovered_json(slug: str, brands_dir: Path | None = None) -> Path:
    return brand_dir(slug, brands_dir) / 'discovered.json'

def checkpoint_json(slug: str, brands_dir: Path | None = None) -> Path:
    return brand_dir(slug, brands_dir) / 'checkpoint.json'

def state_json(slug: str, brands_dir: Path | None = None) -> Path:
    return brand_dir(slug, brands_dir) / 'state.json'

def output_dir(slug: str, brands_dir: Path | None = None) -> Path:
    return brand_dir(slug, brands_dir) / 'output'
