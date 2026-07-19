"""Convergence detection: 3 consecutive phases with 0 new rows."""


def converged(phase_history: list[dict]) -> tuple[bool, str]:
    """Check if scraping has converged.

    Rule: 3 consecutive trailing phases with added==0.
    Returns (is_converged, reason_string).
    """
    if len(phase_history) < 3:
        return False, f'Only {len(phase_history)} phases completed (need at least 3)'

    trailing = phase_history[-3:]
    if all(p.get('added', 0) == 0 for p in trailing):
        return True, '3 consecutive phases yielded 0 new rows — converged'

    return False, f'Last 3 phases added: {[p.get("added", 0) for p in trailing]}'
