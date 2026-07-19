"""Deterministic-strategy auto-runner.

Chains brand_variants → solr_escape(scout) → solr_escape(full) → parent_mst,
calling converged() after each phase, halting on convergence.
No LLM in this inner loop — the agent's reasoning engages only after the
deterministic playbook plateaus.
"""
from pathlib import Path

from dkkd import config as cfg
from dkkd.engine import DkkdEngine
from dkkd.records import SweepState
from dkkd import state_report
from dkkd.convergence import converged

from dkkd.strategies import get as get_strategy
from dkkd.data.provinces import get_all_province_amplifiers


# The deterministic playbook — order matters
PLAYBOOK = [
    ('brand_variants', {}),
    ('solr_escape', {'phase': 'scout'}),
    ('solr_escape', {'phase': 'full'}),
    ('parent_mst', {}),
]


def _provinces_from_records(state: SweepState) -> list[str]:
    """Extract distinct province/city names from collected records' addresses."""
    seen = set()
    for record in state.store_map.values():
        addr = record.get('Ho_Address', '') or ''
        parts = [p.strip() for p in addr.split(',') if p.strip()]
        if parts:
            seen.add(parts[-1])
    return sorted(seen)


# Creative amplifier playbook — runs after PLAYBOOK converges (--creative flag)
# Ordered: compound (all provinces + Việt Nam, 27.8% eff) → gdt_bare →
# token_mining (one-shot, 0.3% eff) → hierarchy_walk → solr_escape(full, catches late registrations)
CREATIVE_PLAYBOOK = [
    ('corporate_sweep', lambda state: {}),
    ('compound',       lambda state: {'amplifiers': 'Việt Nam;VIET NAM;' + ';'.join(set(_provinces_from_records(state)) | set(get_all_province_amplifiers()))}),
    ('gdt_bare',       lambda state: {'cap': max(state.max_counter_seq * 2, 100)}),
    ('token_mining',   lambda state: {}),
    ('hierarchy_walk', lambda state: {}),
    ('solr_escape',    lambda state: {'phase': 'full'}),
]


def run_loop(slug: str, *, transport=None, brands_dir: Path | None = None,
             throttle: bool = True, creative: bool = False) -> SweepState:
    """Run the deterministic playbook to convergence.

    Args:
        slug: Brand slug (e.g. 'coop-food')
        transport: Injected transport (None → RequestsTransport)
        brands_dir: Override brands directory (for tests)
        throttle: Whether to apply rate limiting (False in tests)
        creative: If True, run creative amplifier phases after PLAYBOOK

    Returns:
        Final SweepState after all phases or convergence.
    """
    brand_config = cfg.load(slug, brands_dir)

    if transport is None:
        from dkkd.transport import RequestsTransport
        transport = RequestsTransport()

    engine = DkkdEngine(brand_config, transport, brands_dir=brands_dir, throttle=throttle)
    engine.load_checkpoint()

    # Load existing phase history
    phase_history = _load_history(slug, brands_dir)
    state = SweepState(store_map=engine.store_map, phase_history=phase_history)

    for strategy_name, params in PLAYBOOK:
        strategy_fn = get_strategy(strategy_name)
        probes = strategy_fn(brand_config, state, params)

        added = engine.sweep(probes, strategy_name)
        engine.save_checkpoint()

        state.phase_history.append({
            'strategy': strategy_name,
            'params': params,
            'probes': len(probes),
            'added': added,
            'total': len(engine.store_map),
        })
        state.store_map = engine.store_map

        # Write state report after each phase
        state_report.write(brand_config, state, brands_dir)

        # Enrich config with any newly discovered MSTs
        new_msts = state.discovered_msts - set(brand_config.seed_parent_msts)
        if new_msts:
            cfg.enrich(slug, 'discovered_msts', sorted(new_msts), brands_dir)
            brand_config = cfg.load(slug, brands_dir)  # reload
            engine.ingester.update_parent_msts(new_msts)  # accept corporate entities under new MSTs

        is_conv, reason = converged(state.phase_history)
        if is_conv:
            break

    if creative:
        state = run_creative_loop(state, brand_config, engine, slug, brands_dir)

    # Automatically trigger the postprocessing pipeline to classify, enrich, and export
    from dkkd.postprocess import run_pipeline
    run_pipeline(slug, brands_dir=brands_dir)

    return state


def _should_skip_creative(strategy_name: str, state: SweepState) -> bool:
    """Skip strategies that are provably redundant given current state (BHX lessons)."""
    history = state.phase_history

    if strategy_name == 'token_mining':
        # Skip if token_mining already ran and no new records were added since
        last_tm_idx = None
        for i, p in enumerate(history):
            if p['strategy'] == 'token_mining':
                last_tm_idx = i
        if last_tm_idx is not None:
            added_since = sum(p['added'] for p in history[last_tm_idx + 1:])
            if added_since == 0:
                return True

    if strategy_name == 'gdt_bare':
        # Skip if solr_escape(full) already ran with meaningful yield
        for p in history:
            if (p['strategy'] == 'solr_escape'
                    and p.get('params', {}).get('phase') == 'full'
                    and p['added'] > 0):
                return True

    return False


def run_creative_loop(state: SweepState, brand_config, engine: DkkdEngine,
                      slug: str, brands_dir: Path | None = None) -> SweepState:
    """Run creative amplifier strategies after the deterministic playbook plateaus.

    Iterates CREATIVE_PLAYBOOK, parameterising each strategy from live state
    signals. Stops when convergence.converged() returns True across the full
    combined phase history (deterministic + creative).
    """
    current_creative_run: set[str] = set()
    all_creative_names = {name for name, _ in CREATIVE_PLAYBOOK}

    for strategy_name, param_fn in CREATIVE_PLAYBOOK:
        params = param_fn(state)

        # BHX lesson: skip strategies that are provably redundant
        if _should_skip_creative(strategy_name, state):
            current_creative_run.add(strategy_name)
            state.phase_history.append({
                'strategy': strategy_name,
                'params': params,
                'probes': 0,
                'added': 0,
                'total': len(engine.store_map),
                'skipped': True,
            })
            continue

        strategy_fn = get_strategy(strategy_name)
        probes = strategy_fn(brand_config, state, params)

        added = engine.sweep(probes, strategy_name)
        engine.save_checkpoint()

        state.phase_history.append({
            'strategy': strategy_name,
            'params': params,
            'probes': len(probes),
            'added': added,
            'total': len(engine.store_map),
        })
        current_creative_run.add(strategy_name)
        state.store_map = engine.store_map

        state_report.write(brand_config, state, brands_dir)

        new_msts = state.discovered_msts - set(brand_config.seed_parent_msts)
        if new_msts:
            cfg.enrich(slug, 'discovered_msts', sorted(new_msts), brands_dir)
            brand_config = cfg.load(slug, brands_dir)
            engine.ingester.update_parent_msts(new_msts)  # accept corporate entities under new MSTs

        # Only check convergence if we have run all creative strategies at least once.
        # This prevents early termination due to historical zero-yield phases.
        if all_creative_names.issubset(current_creative_run):
            is_conv, _ = converged(state.phase_history)
            if is_conv:
                break

    return state


def _load_history(slug: str, brands_dir: Path | None = None) -> list[dict]:
    """Load phase history from existing state.json."""
    import json
    from dkkd.paths import state_json
    path = state_json(slug, brands_dir)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('phase_history', [])
    return []
