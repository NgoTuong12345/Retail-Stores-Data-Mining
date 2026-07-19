"""Diff core + git plumbing comparing two DKKD checkpoint snapshots by Id.

diff_snapshots() is pure (no I/O) and trivially testable with synthetic
fixtures, matching the standing rule that closure-timing signals must come
from comparing two real, independent snapshots — never from validating one
inference against another. load_snapshot_from_git()/run_diff() are the I/O
layer: checkpoint.json is committed to git on every monthly-update run, so
two commits weeks apart already ARE two real snapshots — no new storage
mechanism is needed.

Public interface:
    _records_to_by_id(records) -> dict[str, dict]
    diff_snapshots(older, newer, *, older_date=None, newer_date=None) -> dict
    load_snapshot_from_git(rev, checkpoint_path, repo_root) -> dict[str, dict]
    run_diff(slug, since_rev, brands_dir=None) -> dict
"""
import json
import subprocess
from datetime import date
from pathlib import Path

from dkkd.geo import normalize_address_for_matching
from dkkd.paths import DEFAULT_BRANDS_DIR, checkpoint_json, output_dir


def _records_to_by_id(records: list[dict]) -> dict[str, dict]:
    """Convert a flat list of records into {str(Id): record}."""
    return {str(r['Id']): r for r in records}


def diff_snapshots(
    older: dict[str, dict], newer: dict[str, dict], *,
    older_date: str | None = None, newer_date: str | None = None,
) -> dict:
    """Compare two {id: record} snapshots and return the five signal categories.

    new_ids: ids in newer not in older, split into 'genuinely_new' (Establishment_Date
        falls inside [older_date, newer_date]) vs 'newly_discovered' (everything else,
        including undated records or missing snapshot dates — the conservative
        no-overclaim default, since our own scrape coverage is never guaranteed
        complete).
    vanished_ids: ids in older not in newer. Never labelled Closed — could be a real
        deregistration or a scrape-coverage gap in the newer run.
    relocations: same id in both, normalized Ho_Address differs (both present).
    status_changes: same id in both, Operating_Status present on both sides and
        differs; carries the two snapshot dates as the closure/reopening bracket.
    renamed: same id in both, Name differs (both present) — independent of address
        change, so it may co-fire with relocations for the same id.
    """
    older_ids = set(older.keys())
    newer_ids = set(newer.keys())

    genuinely_new = []
    newly_discovered = []
    for rid in sorted(newer_ids - older_ids):
        record = newer[rid]
        est_date = record.get('Establishment_Date')
        if est_date and older_date and newer_date and older_date <= est_date <= newer_date:
            genuinely_new.append(rid)
        else:
            newly_discovered.append(rid)

    vanished_ids = sorted(older_ids - newer_ids)

    relocations = {}
    status_changes = {}
    renamed = {}
    for rid in sorted(older_ids & newer_ids):
        old_record = older[rid]
        new_record = newer[rid]

        old_addr = old_record.get('Ho_Address') or ''
        new_addr = new_record.get('Ho_Address') or ''
        if old_addr and new_addr:
            if normalize_address_for_matching(old_addr) != normalize_address_for_matching(new_addr):
                relocations[rid] = {'old_address': old_addr, 'new_address': new_addr}

        old_status = old_record.get('Operating_Status') or ''
        new_status = new_record.get('Operating_Status') or ''
        if old_status and new_status and old_status != new_status:
            status_changes[rid] = {
                'old_status': old_status,
                'new_status': new_status,
                'bracket': [older_date, newer_date],
            }

        old_name = old_record.get('Name') or ''
        new_name = new_record.get('Name') or ''
        if old_name and new_name and old_name != new_name:
            renamed[rid] = {'old_name': old_name, 'new_name': new_name}

    return {
        'new_ids': {'genuinely_new': genuinely_new, 'newly_discovered': newly_discovered},
        'vanished_ids': vanished_ids,
        'relocations': relocations,
        'status_changes': status_changes,
        'renamed': renamed,
    }


def _git(*args: str, cwd: Path) -> str:
    """Run a git command in cwd, return stdout. Raises RuntimeError on failure.

    checkpoint.json contains Vietnamese UTF-8 text; text=True alone decodes with
    the platform default (cp1252 on Windows), which corrupts it. Decode explicitly.
    """
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, encoding='utf-8')
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _commit_date(rev: str, repo_root: Path) -> str:
    """Return the commit's committer date as YYYY-MM-DD."""
    out = _git('show', '-s', '--format=%cI', rev, cwd=repo_root)
    return out.strip()[:10]


def load_snapshot_from_git(rev: str, checkpoint_path: Path, repo_root: Path) -> dict[str, dict]:
    """Load a {id: record} snapshot from checkpoint_path as it existed at rev."""
    relpath = checkpoint_path.resolve().relative_to(repo_root.resolve()).as_posix()
    try:
        raw = _git('show', f'{rev}:{relpath}', cwd=repo_root)
    except RuntimeError as e:
        raise RuntimeError(f"{relpath} did not exist at {rev} ({e})") from e
    pairs = json.loads(raw)
    records = [item[1] if isinstance(item, list) else item for item in pairs]
    return _records_to_by_id(records)


def _build_report(slug: str, older_date: str, newer_date: str, result: dict) -> str:
    lines = [
        f"# Snapshot Diff: {slug}",
        "",
        f"Comparing `{older_date}` -> `{newer_date}`.",
        "",
        f"- New (genuinely_new): {len(result['new_ids']['genuinely_new'])}",
        f"- New (newly_discovered — scrape coverage catch-up, not a real opening): "
        f"{len(result['new_ids']['newly_discovered'])}",
        f"- Vanished (unverified — NOT the same as Closed): {len(result['vanished_ids'])}",
        f"- Relocations: {len(result['relocations'])}",
        f"- Status changes: {len(result['status_changes'])}",
        f"- Renamed: {len(result['renamed'])}",
        "",
    ]
    if result['status_changes']:
        lines += [
            "## Status changes (real closure/reopening bracket)",
            "",
            "| Id | Old status | New status | Bracket |",
            "|---|---|---|---|",
        ]
        for rid, ev in sorted(result['status_changes'].items()):
            lines.append(f"| {rid} | {ev['old_status']} | {ev['new_status']} | "
                          f"{ev['bracket'][0]}..{ev['bracket'][1]} |")
        lines.append("")
    if result['relocations']:
        lines += [
            "## Relocations",
            "",
            "| Id | Old address | New address |",
            "|---|---|---|",
        ]
        for rid, ev in sorted(result['relocations'].items()):
            lines.append(f"| {rid} | {ev['old_address']} | {ev['new_address']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _append_status_transitions(slug: str, status_changes: dict, out_dir: Path) -> None:
    """Append new status_changes events to <slug>_status_transitions.json.

    Append-only and idempotent: an event with the same id+old_status+new_status+bracket
    is never duplicated even if run_diff runs again over the same window.
    """
    path = out_dir / f"{slug}_status_transitions.json"
    existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    seen = {(e['id'], e['old_status'], e['new_status'], tuple(e['bracket'])) for e in existing}
    for rid, ev in status_changes.items():
        key = (rid, ev['old_status'], ev['new_status'], tuple(ev['bracket']))
        if key not in seen:
            existing.append({'id': rid, **ev})
            seen.add(key)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')


def run_diff(slug: str, since_rev: str, brands_dir: Path | None = None) -> dict:
    """Diff since_rev's checkpoint.json against the current on-disk checkpoint.json
    for slug. Writes a human-readable report and appends to the append-only
    status-transitions log. Returns the diff_snapshots() result.
    """
    repo_root = DEFAULT_BRANDS_DIR.parent
    cp_path = checkpoint_json(slug, brands_dir)

    older = load_snapshot_from_git(since_rev, cp_path, repo_root)
    older_date = _commit_date(since_rev, repo_root)

    with open(cp_path, 'r', encoding='utf-8') as f:
        pairs = json.load(f)
    newer_records = [item[1] if isinstance(item, list) else item for item in pairs]
    newer = _records_to_by_id(newer_records)
    newer_date = date.today().isoformat()

    result = diff_snapshots(older, newer, older_date=older_date, newer_date=newer_date)

    out_dir = output_dir(slug, brands_dir)
    report_path = out_dir / f"{slug}_snapshot_diff_{newer_date}.md"
    report_path.write_text(_build_report(slug, older_date, newer_date, result), encoding='utf-8')

    _append_status_transitions(slug, result['status_changes'], out_dir)

    return result
