"""Corporate entity sweep: search for parent company names to capture
warehouses, HQs, logistics centers, online operations, and other non-store
entities that are registered under the corporate name rather than the brand name.

Uses config.corporate_names if specified, otherwise auto-generates search terms
from known parent MSTs and the brand name.
"""
from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('corporate_sweep')
def corporate_sweep(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Sweep for corporate entities (warehouses, HQs, logistics, online ops).

    Generates probes from:
    1. config.corporate_names (explicit parent company name search terms)
    2. Bare parent MST queries (seed + discovered)
    3. Brand name + corporate keywords (e.g. "KHO WINMART", "VĂN PHÒNG WINMART")
    """
    probes: list[Probe] = []
    seen: set[str] = set()

    def _add(query: str) -> None:
        q = query.strip()
        if q and q not in seen:
            seen.add(q)
            probes.append(Probe(search_field=q))

    # 1. Explicit corporate names from config
    for name in config.corporate_names:
        _add(name)

    # 2. Bare parent MST queries — surface the parent entity registration itself
    all_msts = (set(config.seed_parent_msts)
                | set(config.discovered_msts)
                | state.discovered_msts)
    for mst in sorted(all_msts):
        _add(mst)

    # 3. Brand name + corporate keywords
    #    e.g. "KHO WINMART", "VĂN PHÒNG An Khang"
    corporate_keywords = [
        'KHO',
        'VĂN PHÒNG',
        'TRUNG TÂM PHÂN PHỐI',
        'LOGISTICS',
        'ONLINE',
    ]
    # Use short brand variants to combine with keywords
    short_variants = []
    for v in config.spelling_variants[:4]:  # limit to avoid explosion
        # Use variants that are short enough to be useful (< 30 chars)
        if len(v) < 30:
            short_variants.append(v)

    for kw in corporate_keywords:
        for variant in short_variants:
            _add(f'{kw} {variant}')
            _add(f'{variant} {kw}')

    return probes
