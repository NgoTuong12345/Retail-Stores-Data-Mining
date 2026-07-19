"""Per-MST (license) store-count distribution and growth curves.

Pure functions, no I/O — dkkd/backtest.py's _build_license_trends_section reads
the checkpoint and calls into these. "One license, many stores" is a real,
bimodal structural fact in this data (a handful of umbrella MSTs hold dozens+
of branches; the rest are single-store MSTs) — not a dedup bug.

Public interface:
    group_by_mst(records) -> dict[str, list[dict]]
    mst_distribution(records, *, top_n=10) -> dict
    mst_growth_curve(records, mst) -> dict[int, int]
"""
from dkkd.operating_status import _extract_mst


def group_by_mst(records: list[dict]) -> dict[str, list[dict]]:
    """Group records by their resolved MST. Records with no resolvable MST are dropped."""
    groups: dict[str, list[dict]] = {}
    for r in records:
        mst = _extract_mst(r)
        if mst:
            groups.setdefault(mst, []).append(r)
    return groups


def mst_distribution(records: list[dict], *, top_n: int = 10) -> dict:
    """Distribution of store counts across MSTs (licenses)."""
    groups = group_by_mst(records)
    single_store_msts = sum(1 for recs in groups.values() if len(recs) == 1)
    multi_store_msts = sum(1 for recs in groups.values() if len(recs) >= 2)
    total_stores = sum(len(recs) for recs in groups.values())
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    top_msts = [(mst, len(recs)) for mst, recs in ordered[:top_n]]
    return {
        'single_store_msts': single_store_msts,
        'multi_store_msts': multi_store_msts,
        'total_msts': len(groups),
        'total_stores': total_stores,
        'top_msts': top_msts,
    }


def mst_growth_curve(records: list[dict], mst: str) -> dict[int, int]:
    """{Establishment_Year: opening_count} for one MST's records. Records with no
    Establishment_Year are excluded (not bucketed under a sentinel year)."""
    groups = group_by_mst(records)
    curve: dict[int, int] = {}
    for r in groups.get(mst, []):
        year = r.get('Establishment_Year')
        if year is not None:
            curve[int(year)] = curve.get(int(year), 0) + 1
    return curve
