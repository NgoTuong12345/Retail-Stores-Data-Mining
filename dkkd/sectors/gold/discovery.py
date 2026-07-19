"""Gold discovery strategy: keyword × province matrix sweep.

Generates probes by combining gold-related keywords with Vietnamese province names
to rotate the DKKD Solr 10-row window and discover gold/jewelry chains.
"""
from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState
from dkkd.sectors.gold.keywords import get_keywords
from dkkd.data.provinces import get_province_amplifiers

@strategy('gold_discovery')
def gold_discovery(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Generate keyword × province probes for gold chain discovery."""
    seen: set[str] = set()
    probes: list[Probe] = []

    all_keywords = get_keywords('all')           # 15
    high_signal = get_keywords('high_signal')    # 11
    top5 = get_province_amplifiers('top5')       # 5
    rest = get_province_amplifiers('rest')       # 58

    def _add(search_field: str) -> None:
        key = search_field.upper()
        if key not in seen:
            seen.add(key)
            probes.append(Probe(search_field=search_field))

    # Tier 1: Bare keywords (no province)
    for kw in all_keywords:
        _add(kw)

    # Tier 2: Top-5 cities × all keywords
    for prov in top5:
        for kw in all_keywords:
            _add(f'{kw} {prov.accented}')
            _add(f'{kw} {prov.plain}')

    # Tier 3: Remaining 58 provinces × high-signal keywords only
    for prov in rest:
        for kw in high_signal:
            _add(f'{kw} {prov.accented}')
            _add(f'{kw} {prov.plain}')

    return probes
