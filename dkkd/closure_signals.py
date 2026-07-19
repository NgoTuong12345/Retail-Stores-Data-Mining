"""Cross-record structural closure signals for DKKD store records.

Pure functions (no I/O) computed once per brand's full record list, then
passed into operating_status.resolve_operating_status() via its
closure_signals parameter. Kept separate from operating_status.py because
these signals need the whole brand's records at once, while the resolver
loop is per-record.

Public interface:
    build_closure_signal_map(records, *, external_dissolved_msts=None,
                              seed_parent_msts=None) -> dict[int, dict]
    label_from_status(status_raw) -> 'Operating' | 'Closed'
"""
from dkkd.geo import normalize_address_for_matching
from dkkd.operating_status import _CEASED_PHRASES, _extract_mst


def label_from_status(status_raw: str) -> str:
    """Map a raw DKKD per-location status string to 'Closed' or 'Operating'."""
    status_lower = (status_raw or '').lower()
    return 'Closed' if any(p in status_lower for p in _CEASED_PHRASES) else 'Operating'


def parent_dissolution_map(
    records: list[dict], *, seed_parent_msts: set[str] | None = None
) -> dict[str, bool]:
    """Return {parent_mst: True} for every MST with at least one record whose
    OWN Status field reads a ceased phrase.

    Never flags a brand's own seed_parent_msts: measured on real Circle K data,
    a single sibling branch closing under that shared corporate MST predicted
    dissolution at only 47.6% precision (10/21) — the umbrella MST is not a
    reliable dissolution signal even though an unrelated MST with one ceased
    record still is.
    """
    seed = seed_parent_msts or set()
    dissolved: dict[str, bool] = {}
    for r in records:
        status_lower = (r.get('Status') or '').lower()
        if any(p in status_lower for p in _CEASED_PHRASES):
            mst = _extract_mst(r)
            if mst and mst not in seed:
                dissolved[mst] = True
    return dissolved


def build_address_clusters(records: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group records by (parent_mst, normalised Ho_Address); clusters of size 1 dropped."""
    clusters: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        mst = _extract_mst(r)
        addr = normalize_address_for_matching(r.get('Ho_Address') or '')
        if not mst or not addr:
            continue
        clusters.setdefault((mst, addr), []).append(r)
    return {key: recs for key, recs in clusters.items() if len(recs) >= 2}


def mark_superseded(records: list[dict]) -> dict[int, int]:
    """Return {dkkd_id: newer_dkkd_id} for every record superseded by a newer
    sibling at the same (parent_mst, normalised address). Within each cluster,
    the highest-Id record is treated as live; every other record maps to it."""
    superseded: dict[int, int] = {}
    for cluster in build_address_clusters(records).values():
        ided = []
        for r in cluster:
            try:
                ided.append((int(r['Id']), r))
            except (KeyError, TypeError, ValueError):
                continue
        if len(ided) < 2:
            continue
        ided.sort(key=lambda pair: pair[0])
        newest_id = ided[-1][0]
        for rid, _ in ided[:-1]:
            superseded[rid] = newest_id
    return superseded


def build_closure_signal_map(
    records: list[dict], *, external_dissolved_msts: set[str] | None = None,
    seed_parent_msts: set[str] | None = None,
) -> dict[int, dict]:
    """Build the {dkkd_id: signal} map consumed by resolve_operating_status.

    Each value is either {'signal': 'parent_dissolved'} or
    {'signal': 'superseded', 'newer_id': int}. Records with neither signal are
    absent from the map. Parent-dissolution takes precedence over supersession
    when both apply to the same record. seed_parent_msts is excluded from
    parent-dissolution (see parent_dissolution_map) but not from
    external_dissolved_msts, which represents a verified external signal rather
    than the unreliable single-sibling-ceased heuristic.
    """
    dissolved = parent_dissolution_map(records, seed_parent_msts=seed_parent_msts)
    if external_dissolved_msts:
        for mst in external_dissolved_msts:
            dissolved[mst] = True
    superseded = mark_superseded(records)

    signals: dict[int, dict] = {}
    for r in records:
        try:
            rid = int(r['Id'])
        except (KeyError, TypeError, ValueError):
            continue
        mst = _extract_mst(r)
        if mst and dissolved.get(mst):
            signals[rid] = {'signal': 'parent_dissolved'}
        elif rid in superseded:
            signals[rid] = {'signal': 'superseded', 'newer_id': superseded[rid]}
    return signals
