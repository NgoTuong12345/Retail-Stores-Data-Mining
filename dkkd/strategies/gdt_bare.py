"""Bare GDT counter strategy: probes bare 5-digit counter sequences directly.

Bypasses spelling variant prefixes to capture locations that overflow Solr's
search window when queried with the brand name.
"""
from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('gdt_bare')
def gdt_bare(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Probe bare 5-digit GDT counter sequences directly."""
    if 'cap' in params:
        cap = int(params['cap'])
    else:
        cap = state.max_counter_seq if state.max_counter_seq > 50 else 50

    return [Probe(search_field=f'{i:05d}') for i in range(1, cap + 1)]
