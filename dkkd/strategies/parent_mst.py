"""Parent MST sweep: union seed+discovered+state MSTs, emit bare + branch probes.

Port of coopfood_scraper.py:355-361 MST discovery + the P6 phase sweep.
"""
import math

from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('parent_mst')
def parent_mst_sweep(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Union seed+discovered+state MSTs, emit bare MST + MST-001..NNN."""
    all_msts = (set(config.seed_parent_msts)
                | set(config.discovered_msts)
                | state.discovered_msts)
    all_msts_sorted = sorted(all_msts)  # deterministic order

    max_seq = state.max_branch_seq
    nnn = max(int(math.ceil(max_seq * 1.2)), 60) if max_seq > 0 else 60

    probes: list[Probe] = []
    for mst in all_msts_sorted:
        probes.append(Probe(search_field=mst))
        for seq in range(1, nnn + 1):
            probes.append(Probe(search_field=f'+{mst} +{seq:03d}'))

    return probes
