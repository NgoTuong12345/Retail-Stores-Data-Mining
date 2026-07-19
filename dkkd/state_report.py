"""State report: build the JSON snapshot the LLM reads."""
import json
from datetime import datetime, timezone
from pathlib import Path

from dkkd.config import BrandConfig
from dkkd.records import SweepState
from dkkd.paths import state_json

from dkkd.strategies import list_names


def build(config: BrandConfig, state: SweepState) -> dict:
    """Build the state report JSON that the orchestrating LLM reads.

    Includes: total_records, phase_history, discovered items, derived counters,
    sample_records, convergence status, and hints (untried strategies).
    """
    from dkkd.convergence import converged

    # Strategies already run
    run_strategies = {p.get('strategy') for p in state.phase_history if p.get('strategy')}
    all_strategies = set(list_names())
    untried = sorted(all_strategies - run_strategies)

    # Convergence
    is_converged, conv_reason = converged(state.phase_history)

    # Sample records (up to 5)
    sample = list(state.store_map.values())[:5]

    report = {
        'total_records': state.total_records,
        'phase_history': state.phase_history,
        'discovered': {
            'spelling_variants': list(config.spelling_variants),
            'parent_msts': sorted(config.all_parent_msts),
            'sibling_brands': list(config.sibling_brands),
        },
        'derived': {
            'max_counter_seq': state.max_counter_seq,
            'max_branch_seq': state.max_branch_seq,
            'discovered_msts': sorted(state.discovered_msts),
            'mst_fragmentation_ratio': (
                round(len(state.discovered_msts) / state.total_records, 4)
                if state.total_records > 0 else 0.0
            ),
        },
        'sample_records': sample,
        'convergence': {
            'converged': is_converged,
            'zero_new_phases': sum(
                1 for p in state.phase_history[-3:] if p.get('added', 0) == 0
            ) if state.phase_history else 0,
            'rule': '3 consecutive phases with 0 new rows',
        },
        'hints': {
            'untried_strategies': untried,
            'suggested_next': untried[0] if untried else None,
            'rationale': f'{len(untried)} strategies not yet tried' if untried else 'all strategies exhausted',
        },
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }

    return report


def write(config: BrandConfig, state: SweepState, brands_dir: Path | None = None) -> Path:
    """Build and write state report to state.json."""
    report = build(config, state)
    path = state_json(config.slug, brands_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path
