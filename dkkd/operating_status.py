"""3-state operating status resolver for DKKD brand stores.

Public interface:
    load_locator_pins(slug, brands_dir) -> dict[int, str]
    resolve_operating_status(stores, config, *, locator_pins, gdt_cache,
                              closure_signals) -> None
"""
import csv
from pathlib import Path

from dkkd.config import BrandConfig
from dkkd.paths import output_dir

# Substrings (lowercased) that indicate a ceased/inactive GDT status (rung 3).
_CEASED_PHRASES = (
    'chấm dứt',
    'ngừng hoạt động',
    'không hoạt động',
    'giải thể',
    'tạm ngừng',
)

_VALID_MATCH_TYPES = {'Unique', 'Shared_Co-located'}


def load_locator_pins(slug: str, brands_dir: Path | None = None) -> dict[int, str]:
    """Return {dkkd_id: match_type} from output/{slug}_store_mapping.csv.

    Includes only rows where match_type in {'Unique', 'Shared_Co-located'}
    and dkkd_id is non-empty. Returns {} if file doesn't exist.
    """
    csv_path = output_dir(slug, brands_dir) / f'{slug}_store_mapping.csv'
    if not csv_path.exists():
        return {}

    pins: dict[int, str] = {}
    with open(csv_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            match_type = row.get('match_type', '').strip()
            dkkd_id_raw = row.get('dkkd_id', '').strip()
            if match_type in _VALID_MATCH_TYPES and dkkd_id_raw:
                try:
                    pins[int(dkkd_id_raw)] = match_type
                except ValueError:
                    pass
    return pins


def _extract_mst(record: dict) -> str | None:
    """Extract 10-digit MST from Enterprise_Gdt_Code or Enterprise_Code.

    Returns None if no valid 10-digit MST found.
    Mirrors the logic in postprocess.py Stage 2 (lines 181-199).
    """
    gdt = str(record.get('Enterprise_Gdt_Code') or '')
    code = str(record.get('Enterprise_Code') or '')

    # Try Enterprise_Gdt_Code first
    if gdt.isdigit() and len(gdt) >= 10:
        mst = gdt[:10]
        if not mst.startswith('00'):
            return mst
    if '-' in gdt:
        parts = gdt.split('-')
        if parts[0].isdigit() and len(parts[0]) == 10:
            mst = parts[0]
            if not mst.startswith('00'):
                return mst

    # Fall back to Enterprise_Code — valid regardless of '00' prefix.
    if code.isdigit() and len(code) == 10:
        return code
    if '-' in code:
        parts = code.split('-')
        if parts[0].isdigit() and len(parts[0]) == 10:
            return parts[0]

    return None


def _is_opted_in(config: BrandConfig) -> bool:
    return bool(config.classification.get('operating_status', {}).get('enabled'))


def resolve_operating_status(
    stores: list[dict],
    config: BrandConfig,
    *,
    locator_pins: dict[int, str] | None = None,
    gdt_cache: dict | None = None,
    closure_signals: dict[int, dict] | None = None,
) -> None:
    """Set Operating_Status and Operating_Evidence on each store record,
    then derive Core_Operating_Store from Operating_Status.

    Mutates stores in place. Returns None.
    """
    if locator_pins is None:
        locator_pins = {}

    opted_in = _is_opted_in(config)

    for record in stores:
        if opted_in:
            _resolve_optin(record, config, locator_pins, gdt_cache or {}, closure_signals)
        else:
            _resolve_legacy(record)


def _resolve_optin(
    record: dict,
    config: BrandConfig,
    locator_pins: dict[int, str],
    gdt_cache: dict,
    closure_signals: dict[int, dict] | None = None,
) -> None:
    """Evidence ladder for opt-in brands (first match wins)."""
    status_raw = record.get('Status') or ''
    status_lower = status_raw.lower()

    try:
        dkkd_id = int(record.get('Id', ''))
    except (ValueError, TypeError):
        dkkd_id = None

    signal = closure_signals.get(dkkd_id) if closure_signals and dkkd_id is not None else None

    # Rung 1: Corporate/Logistics name
    if str(record.get('Store_Brand_Format', '')).endswith('(Corporate/Logistics)'):
        record['Operating_Status'] = 'Closed'
        record['Operating_Evidence'] = 'corporate'
        record['Core_Operating_Store'] = 'No'
        return

    # Rung 2: Structural — parent-MST dissolution propagation
    if signal and signal.get('signal') == 'parent_dissolved':
        record['Operating_Status'] = 'Closed'
        record['Operating_Evidence'] = 'structural:parent-dissolved'
        record['Core_Operating_Store'] = 'No'
        return

    # Rung 3: Ceased status phrases
    if any(phrase in status_lower for phrase in _CEASED_PHRASES):
        record['Operating_Status'] = 'Closed'
        record['Operating_Evidence'] = 'status-ceased'
        record['Core_Operating_Store'] = 'No'
        return

    # Rung 4: Locator pin
    if dkkd_id is not None and dkkd_id in locator_pins:
        match_type = locator_pins[dkkd_id]
        record['Operating_Status'] = 'Operating'
        record['Operating_Evidence'] = f'locator:{match_type}'
        record['Core_Operating_Store'] = 'Yes'
        return

    # Rung 5: Structural — address-supersession
    if signal and signal.get('signal') == 'superseded':
        record['Operating_Status'] = 'Closed'
        record['Operating_Evidence'] = f"structural:superseded:{signal.get('newer_id')}"
        record['Core_Operating_Store'] = 'No'
        return

    # Rung 6: Own-MST GDT-active (not a seed parent MST)
    if status_raw == 'NNT đang hoạt động':
        gdt_raw = str(record.get('Enterprise_Gdt_Code') or '')
        is_branch = '-' in gdt_raw or (gdt_raw.isdigit() and len(gdt_raw) == 13)
        mst = _extract_mst(record)
        if is_branch or (mst is not None and mst not in config.seed_parent_msts):
            record['Operating_Status'] = 'Operating'
            record['Operating_Evidence'] = 'gdt-own-mst'
            record['Core_Operating_Store'] = 'Yes'
            return

    # Rung 7: Unverified
    record['Operating_Status'] = 'Unverified'
    record['Operating_Evidence'] = 'licensed-unverified'
    record['Core_Operating_Store'] = 'No'


def _resolve_legacy(record: dict) -> None:
    """Legacy derivation for non-opt-in brands. Does not re-derive Core_Operating_Store."""
    if record.get('Core_Operating_Store') == 'Yes':
        record['Operating_Status'] = 'Operating'
    else:
        record['Operating_Status'] = 'Closed'
    record['Operating_Evidence'] = 'legacy-classify'
