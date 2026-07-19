"""Token mining strategy: find rare tokens in collected records for novel probes."""
from collections import Counter

from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('token_mining')
def token_mining(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Mine rare tokens from collected records to find new stores.

    Splits all Name tokens by frequency, emits low-frequency ones
    combined with brand variants as compound probes.
    """
    token_freq: Counter[str] = Counter()
    for r in state.store_map.values():
        name = r.get('Name') or ''
        for token in name.split():
            token_freq[token.upper()] += 1

    # Rarest first
    sorted_tokens = sorted(token_freq.items(), key=lambda x: x[1])
    max_freq = params.get('max_freq', 3)
    rare_tokens = [tok for tok, freq in sorted_tokens if freq <= max_freq]

    # Combine with top brand variants
    variants = config.spelling_variants[:3] if config.spelling_variants else [config.name]
    probes: list[Probe] = []
    for variant in variants:
        # Prefix every word in variant with "+" to make them required terms in Solr
        required_variant = " ".join(f"+{t}" for t in variant.split() if t)
        for token in rare_tokens:
            probes.append(Probe(search_field=f'{required_variant} +{token}'))

    return probes
