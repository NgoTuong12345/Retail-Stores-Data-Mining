"""Brand variant strategy: permute separators/case to discover spelling variants.

The CO.OPFOOD breakthrough (30 extra stores) came from a no-space separator
variant that the legacy scraper didn't originally try. This strategy
systematically generates all separator × case permutations.
"""
from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('brand_variants')
def brand_variants(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Permute separators/case from the canonical name to discover spelling variants."""
    # Start with known variants from config
    variants: list[str] = list(config.spelling_variants)

    # Decompose the canonical name into tokens
    # e.g. 'Co.op Food' → ['Co', 'op', 'Food']
    parts = config.name.replace('.', ' ').replace('-', ' ').replace(',', ' ').split()

    seps = ['.', '-', ' ', ',', '']
    case_fns = [str.upper, str.lower, str.title, lambda s: s]

    # Full-join permutations: sep × case
    for sep in seps:
        joined = sep.join(parts)
        for case_fn in case_fns:
            v = case_fn(joined)
            if v not in variants:
                variants.append(v)

    # Partial-join variants: first two tokens joined with sep, last token concatenated
    # This generates CO.OPFOOD, CO-OPFOOD, COOPFOOD, etc.
    if len(parts) >= 3:
        for sep in seps:
            v = sep.join(parts[:2]) + parts[2]
            for case_fn in [str.upper, str.lower, str.title]:
                cv = case_fn(v)
                if cv not in variants:
                    variants.append(cv)

    required_variants = []
    for v in variants:
        req = " ".join(f"+{t}" for t in v.split() if t)
        if req:
            required_variants.append(req)

    return [Probe(search_field=v) for v in required_variants]
