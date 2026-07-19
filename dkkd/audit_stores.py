"""LLM-powered store audit for DKKD brands.

Workflow:
  1. generate_audit_sheet(slug) — build audit_sheet.json from checkpoint.json.
                                  Preserves existing decisions (idempotent/resumable).
  2. run_llm_audit(slug)        — classify unclassified rows via Claude API.
                                  Saves after each batch so interrupted runs resume.
  3. apply_audit_filter(stores, slug) — called by postprocess; drops rejected IDs.

Audit sheet schema (brands/.../audit_sheet.json):
  [
    {"id": 1125535, "name": "...", "name_f": "...", "address": "...",
     "status": "keep"|"reject"|"review"|null, "reason": "..."},
    ...
  ]

Non-destructive: checkpoint.json is never modified.
"""
import json
from pathlib import Path

from dkkd.paths import brand_dir, checkpoint_json
from dkkd.config import load as load_config

AUDIT_FILENAME = 'audit_sheet.json'
DEFAULT_BATCH = 20


# ── Path helper ───────────────────────────────────────────────────────────────

def audit_sheet_path(slug: str, brands_dir: Path | None = None) -> Path:
    return brand_dir(slug, brands_dir) / AUDIT_FILENAME


# ── Sheet generation ──────────────────────────────────────────────────────────

def generate_audit_sheet(slug: str, brands_dir: Path | None = None) -> Path:
    """Create or update audit_sheet.json from checkpoint.json.

    Existing status decisions are preserved.  New checkpoint IDs get status=null.
    Returns the path to the written file.
    """
    cp_path = checkpoint_json(slug, brands_dir)
    with open(cp_path, encoding='utf-8') as f:
        pairs = json.load(f)
    stores = [item[1] if isinstance(item, list) else item for item in pairs]

    sheet_path = audit_sheet_path(slug, brands_dir)
    existing: dict[int, dict] = {}
    if sheet_path.exists():
        for row in json.loads(sheet_path.read_text(encoding='utf-8')):
            existing[row['id']] = row

    rows = []
    for s in stores:
        sid = int(s.get('Id', 0))
        if sid in existing:
            rows.append(existing[sid])
        else:
            rows.append({
                'id': sid,
                'name': s.get('Name') or s.get('Name_F') or '',
                'name_f': s.get('Name_F') or '',
                'address': s.get('Ho_Address') or s.get('Ho_Address_F') or '',
                'status': None,
                'reason': '',
            })

    sheet_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    return sheet_path


# ── LLM audit ─────────────────────────────────────────────────────────────────


def _classify_batch(
    records: list[dict],
    brand_name: str,
    brand_regex: str,
    spelling_variants: list[str],
) -> list[dict] | None:
    """Call 'claude -p' to classify a batch of records.

    Returns list of {id, status, reason} or None on failure.
    Uses claude --print mode (no API key required).
    """
    import subprocess
    import re as _re

    variants_str = ', '.join(spelling_variants) if spelling_variants else brand_name
    prompt = (
        f'You are auditing store records for the brand "{brand_name}".\n\n'
        f'Brand regex: {brand_regex}\n'
        f'Known spellings: {variants_str}\n\n'
        'For each record, classify as:\n'
        f'  keep   — business IS a store/branch/location/entity of "{brand_name}"\n'
        f'  reject — different business that coincidentally contains matching tokens\n'
        '  review — ambiguous; cannot confidently keep or reject\n\n'
        'Output ONLY a JSON array, no markdown fences, no explanation:\n'
        '[{"id": <id>, "status": "keep"|"reject"|"review", "reason": "<1 sentence>"}]\n\n'
        f'Records:\n{json.dumps(records, ensure_ascii=False)}'
    )

    try:
        result = subprocess.run(
            ['claude', '-p', prompt],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding='utf-8', timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"claude -p call failed: {e}") from e

    if result.returncode != 0:
        raise RuntimeError(f"claude -p exited {result.returncode}: {result.stderr[:200]}")

    text = result.stdout.strip()
    # Extract the first JSON array from the response
    match = _re.search(r'\[.*\]', text, _re.DOTALL)
    if not match:
        return None
    return json.loads(match.group())


def run_llm_audit(
    slug: str,
    brands_dir: Path | None = None,
    batch_size: int = DEFAULT_BATCH,
    verbose: bool = True,
) -> dict:
    """Classify unclassified stores in audit_sheet.json via 'claude -p'.

    Saves progress after each batch (resumable if interrupted).
    Returns a summary dict: {total, already_classified, newly_classified, keep, reject, review}.
    """
    sheet_path = audit_sheet_path(slug, brands_dir)
    if not sheet_path.exists():
        raise FileNotFoundError(
            f"Audit sheet not found at {sheet_path}. "
            "Run generate_audit_sheet() first."
        )

    config = load_config(slug, brands_dir)
    sheet: list[dict] = json.loads(sheet_path.read_text(encoding='utf-8'))

    unclassified = [r for r in sheet if r.get('status') is None]
    already_done = len(sheet) - len(unclassified)

    if verbose:
        print(f"  Audit sheet: {len(sheet)} total, {already_done} already classified, "
              f"{len(unclassified)} to classify")

    if not unclassified:
        counts = _count_statuses(sheet)
        return {'total': len(sheet), 'already_classified': already_done,
                'newly_classified': 0, **counts}

    by_id = {r['id']: r for r in sheet}
    brand_regex = getattr(config, 'brand_regex', '')
    spelling_variants = getattr(config, 'spelling_variants', []) or []

    newly = 0
    total_batches = (len(unclassified) + batch_size - 1) // batch_size

    for i in range(0, len(unclassified), batch_size):
        batch = unclassified[i:i + batch_size]
        batch_num = i // batch_size + 1

        if verbose:
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} records)...", end=' ', flush=True)

        payload = [
            {'id': r['id'], 'name': r['name'], 'name_f': r['name_f'], 'address': r['address']}
            for r in batch
        ]

        results = _classify_batch(payload, config.name, brand_regex, spelling_variants)
        if results is None:
            if verbose:
                print("WARNING: could not parse LLM response, skipping batch")
            continue

        for r in results:
            rid = r.get('id')
            if rid in by_id:
                by_id[rid]['status'] = r.get('status')
                by_id[rid]['reason'] = r.get('reason', '')
                newly += 1

        # Save progress after each batch (resume support)
        sheet_path.write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding='utf-8')

        if verbose:
            statuses = [r.get('status') for r in results]
            k = statuses.count('keep')
            rj = statuses.count('reject')
            rv = statuses.count('review')
            print(f"keep={k} reject={rj} review={rv}")

    counts = _count_statuses(sheet)
    return {
        'total': len(sheet),
        'already_classified': already_done,
        'newly_classified': newly,
        **counts,
    }


def _count_statuses(sheet: list[dict]) -> dict:
    keep = sum(1 for r in sheet if r.get('status') == 'keep')
    reject = sum(1 for r in sheet if r.get('status') == 'reject')
    review = sum(1 for r in sheet if r.get('status') == 'review')
    null = sum(1 for r in sheet if r.get('status') is None)
    return {'keep': keep, 'reject': reject, 'review': review, 'unclassified': null}


# ── Postprocess integration ───────────────────────────────────────────────────

def apply_audit_filter(
    stores: list[dict],
    slug: str,
    brands_dir: Path | None = None,
) -> tuple[list[dict], int]:
    """Filter rejected stores. Called by postprocess after loading checkpoint.

    Returns (filtered_stores, n_rejected).
    If no audit_sheet.json exists, returns (stores, 0) unchanged.
    """
    sheet_path = audit_sheet_path(slug, brands_dir)
    if not sheet_path.exists():
        return stores, 0

    sheet: list[dict] = json.loads(sheet_path.read_text(encoding='utf-8'))
    rejected_ids = {r['id'] for r in sheet if r.get('status') == 'reject'}
    if not rejected_ids:
        return stores, 0

    filtered = [s for s in stores if int(s.get('Id', 0)) not in rejected_ids]
    return filtered, len(stores) - len(filtered)


# ── Convenience CLI wrapper ───────────────────────────────────────────────────

def audit_brand(
    slug: str,
    brands_dir: Path | None = None,
    batch_size: int = DEFAULT_BATCH,
    generate_only: bool = False,
    verbose: bool = True,
) -> dict:
    """Full audit flow: generate sheet + optional LLM classification."""
    sheet_path = generate_audit_sheet(slug, brands_dir)
    sheet = json.loads(sheet_path.read_text(encoding='utf-8'))
    unclassified = sum(1 for r in sheet if r.get('status') is None)

    if verbose:
        print(f"  Generated audit sheet → {sheet_path}")
        print(f"  Records: {len(sheet)} total, {unclassified} unclassified")

    if generate_only or unclassified == 0:
        if verbose and unclassified == 0:
            print("  All records already classified. Use --reset to reclassify.")
        return _count_statuses(sheet)

    return run_llm_audit(slug, brands_dir, batch_size=batch_size, verbose=verbose)
