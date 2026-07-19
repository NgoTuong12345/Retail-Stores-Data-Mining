"""Strategy registry: @strategy decorator, get(), list_names()."""
from typing import Callable

REGISTRY: dict[str, Callable] = {}


def strategy(name: str):
    """Decorator to register a strategy function."""
    def decorator(fn):
        REGISTRY[name] = fn
        return fn
    return decorator


def get(name: str) -> Callable:
    """Get a registered strategy by name. Raises KeyError if unknown."""
    if name not in REGISTRY:
        raise KeyError(f"Unknown strategy: {name!r}. Available: {list(REGISTRY.keys())}")
    return REGISTRY[name]


def list_names() -> list[str]:
    """Return all registered strategy names."""
    return sorted(REGISTRY.keys())


# Import every strategy module once so its @strategy decorator registers it.
from dkkd.strategies import brand_variants  # noqa: E402,F401
from dkkd.strategies import compound  # noqa: E402,F401
from dkkd.strategies import corporate_sweep  # noqa: E402,F401
from dkkd.strategies import gdt_bare  # noqa: E402,F401
from dkkd.sectors.gold import discovery  # noqa: E402,F401
from dkkd.strategies import hierarchy_walk  # noqa: E402,F401
from dkkd.strategies import parent_mst  # noqa: E402,F401
from dkkd.strategies import raw  # noqa: E402,F401
from dkkd.strategies import solr_escape  # noqa: E402,F401
from dkkd.strategies import token_mining  # noqa: E402,F401
