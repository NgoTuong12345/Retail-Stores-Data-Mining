"""Compound query strategy: brand variant + amplifier word."""
import re

from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('compound')
def compound(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Compound queries: brand variant + amplifier word, deduped."""
    amplifiers = params.get('amplifiers', [])
    if isinstance(amplifiers, str):
        # Support splitting by semicolon, comma, or whitespace
        amplifiers = [amp.strip() for amp in re.split(r'[;,\s]+', amplifiers) if amp.strip()]

    variants = config.spelling_variants[:3] if config.spelling_variants else [config.name]

    seen: set[str] = set()
    probes: list[Probe] = []
    for variant in variants:
        # Prefix every word in variant with "+" to make them required terms in Solr
        required_variant = " ".join(f"+{token}" for token in variant.split() if token)
        for amp in amplifiers:
            # Prefix every word in amplifier with "+" as well
            required_amp = " ".join(f"+{token}" for token in amp.split() if token)
            key = f'{required_variant} {required_amp}'.upper()
            if key not in seen:
                seen.add(key)
                probes.append(Probe(search_field=f'{required_variant} {required_amp}'))

    return probes
