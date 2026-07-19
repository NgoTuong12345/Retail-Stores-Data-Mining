"""Hierarchical tree-walk strategy: exhaustive per-parent Format B branch probing.

Fixes the global-max cap bug in parent_mst: each parent MST gets its own branch
cap derived from observed records in state, with a 200-branch floor.

Port of docs/archive/walkthrough.md Phase 11 (systematic branch sweep) extended with
per-parent convergence and dynamic seeding from collected state records.
"""
import math

from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState
from dkkd.utils import parse_gdt


def _per_parent_max(state: SweepState) -> dict[str, int]:
    """Extract max observed branch sequence per parent MST from Format B records in state."""
    result: dict[str, int] = {}
    for record in state.store_map.values():
        gdt = record.get('Enterprise_Gdt_Code') or ''
        parsed = parse_gdt(gdt)
        if parsed['format'] == 'branch':
            mst = parsed['parent_mst']
            seq = parsed['branch_seq']
            result[mst] = max(result.get(mst, 0), seq)
    return result


@strategy('hierarchy_walk')
def hierarchy_walk(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Hierarchical BFS over Format B parent MSTs with per-parent branch cap.

    Seeds from config.all_parent_msts and all Format B parent MSTs in state.
    For each parent MST emits: bare query + MST-001..MST-cap where
    cap = max(ceil(per_parent_max_branch_seq * 1.5), min_branch_cap).

    Designed to run iteratively in CREATIVE_PLAYBOOK; newly discovered parents
    from one iteration are automatically included on the next call.
    """
    min_branch_cap: int = int(params.get('min_branch_cap', 200))

    per_parent = _per_parent_max(state)

    # Union: config seeds (seed + discovered) + state-extracted Format B parents
    all_msts = sorted(
        set(config.all_parent_msts) | set(per_parent.keys()) | state.discovered_msts
    )

    seen: set[str] = set()
    probes: list[Probe] = []

    for mst in all_msts:
        if mst not in seen:
            probes.append(Probe(search_field=mst))
            seen.add(mst)

        cap = max(int(math.ceil(per_parent.get(mst, 0) * 1.5)), min_branch_cap)
        for i in range(1, cap + 1):
            branch_key = f'{mst}-{i:03d}'
            if branch_key not in seen:
                probes.append(Probe(search_field=f'+{mst} +{i:03d}'))
                seen.add(branch_key)

    return probes
