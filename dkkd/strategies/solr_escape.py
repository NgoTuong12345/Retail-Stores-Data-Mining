"""Solr +N escape strategy: two-phase numeric probe.

Scout phase: +1..+50 (quick coverage check).
Full phase: +1..+cap where cap = max(max_counter_seq, max_branch_seq) × 1.2.
Queries both branch format (+N) and counter format (+00NNN) for each spelling variant.
"""
import math

from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('solr_escape')
def solr_escape(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Two-phase Solr +N escape probe.

    Scout: +1..+50.  Full: +1..+cap where cap = ceil(max(counter, branch) × 1.2).
    """
    phase = params.get('phase', 'scout')
    
    # Allow overriding cap directly via params
    if 'cap' in params:
        cap = int(params['cap'])
    elif phase == 'scout':
        cap = 50
    else:
        raw_cap = max(state.max_counter_seq, state.max_branch_seq) * 1.2
        cap = int(math.ceil(raw_cap)) if raw_cap > 50 else 50

    variants = config.spelling_variants if config.spelling_variants else [config.name]
    probes = []
    for spelling in variants:
        # Prefix every word in spelling with "+" to make them required terms in Solr
        required_spelling = " ".join(f"+{token}" for token in spelling.split() if token)
        for i in range(1, cap + 1):
            # Format B branch suffix / integer token (e.g. +143)
            probes.append(Probe(search_field=f'{required_spelling} +{i}'))
            # Format A counter suffix / 5-digit zero-padded token (e.g. +00143)
            probes.append(Probe(search_field=f'{required_spelling} +{i:05d}'))

    return probes
