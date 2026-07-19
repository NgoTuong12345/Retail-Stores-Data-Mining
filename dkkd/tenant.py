# dkkd/tenant.py
"""Tenant separation & role tagging for supermarket/mall brands.

Splits swept records into three roles without dropping any:
  own_store        — operated by the brand's own parent entity
  in_brand_tenant  — a different company's booth registered INSIDE a brand outlet
  unrelated        — over-swept by MST-walk; brand token appears nowhere

Opt-in per brand via classification.tenant_separation.enabled. When disabled,
every record is tagged own_store (harmless; doubles as a contamination flag).
Non-destructive: sets store_role/host_store on records in place; checkpoint.json
raw rows and the Name/Name_F filter invariants (AGENTS.md) are untouched.
"""
import csv
import re
import unicodedata
from collections import defaultdict

from dkkd.config import BrandConfig

# Name fragments marking a record as some OTHER company's registration with the
# brand appearing only as a location suffix — never the brand's own outlet.
_THIRD_PARTY_MARKERS = (
    'ĐỊA ĐIỂM KINH DOANH',
    'GIAN HÀNG',
    'CÔNG TY',
    'HỘ KINH DOANH',
    'DOANH NGHIỆP TƯ NHÂN',
)


def base_mst(record: dict) -> str:
    """Return the 10-digit operator MST from a record, or '' if none is encoded.

    GDT wins over Enterprise_Code (mirrors postprocess Stage 2). Format B
    ('0309453012-001') → the head; a bare 10-digit code → itself; Format A
    ('00003', 5-digit) encodes no operator MST → falls through to Enterprise_Code.
    """
    for val in (record.get('Enterprise_Gdt_Code'), record.get('Enterprise_Code')):
        s = str(val or '')
        if '-' in s:
            head = s.split('-')[0]
            if head.isdigit() and len(head) == 10:
                return head
        elif s.isdigit() and len(s) >= 10:
            return s[:10]
    return ''


# Delimiters that end a host-outlet label after the brand token.
_HOST_STOP = re.compile(r'\s*(?:,|;|:|\.|-|–|\bSố\b|\bTầng\b|\bLầu\b|\bĐường\b|$)', re.IGNORECASE)


def parse_host(record: dict, regex: re.Pattern) -> str:
    """Extract a host-outlet label from a tenant record's address (name fallback).

    Captures the brand token + the place-words that follow it, up to the next
    delimiter: 'TTTM Co.opXtra Sư Vạn Hạnh, Số 11...' → 'Co.opXtra Sư Vạn Hạnh'.
    Returns '' when the brand token isn't found in any text field.
    # ponytail: naive suffix-capture; add a per-brand host_aliases map if labels
    # prove too noisy to group.
    """
    for field in ('Ho_Address', 'Name', 'Ho_Address_F', 'Name_F'):
        text = str(record.get(field) or '')
        m = regex.search(text)
        if not m:
            continue
        tail = text[m.end():].lstrip(' -–')
        stop = _HOST_STOP.search(tail)
        label = tail[:stop.start()] if stop else tail
        label = ' '.join(label.split()).strip(' -–,')
        token = ' '.join(m.group(0).split())
        return f'{token} {label}'.strip() if label else token
    return ''


def _host_key(label: str) -> str:
    """Case+diacritic+spacing-folded grouping key.

    'CO.OPXTRA SƯ VẠN HẠNH' and 'CO.OP XTRA Sư Vạn Hạnh' fold to the same key so
    tenants of one physical outlet group together regardless of spelling.
    """
    s = unicodedata.normalize('NFD', label or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _classify_role(
    record: dict, regex: re.Pattern, parent_msts: set[str],
    own_store_name_patterns: tuple[str, ...] = (),
) -> str:
    name = str(record.get('Name') or '')
    # 1. own_store: operated by a brand parent MST, a known official-entity name
    # (needed for Format-A business locations — their 5-digit GDT code encodes
    # no shared parent MST, so base_mst can't group them; e.g. AEON's MaxValu
    # banner stores are each registered as 'CÔNG TY TNHH AEON VIỆT NAM – ĐỊA
    # ĐIỂM KINH DOANH MAXVALU ...', a unique Enterprise_Code per store), or a
    # clean brand-named outlet.
    mst = base_mst(record)
    if mst and mst in parent_msts:
        return 'own_store'
    if any(re.search(p, name, re.IGNORECASE) for p in own_store_name_patterns):
        return 'own_store'
    if regex.search(name) and not any(m in name.upper() for m in _THIRD_PARTY_MARKERS):
        return 'own_store'
    # 2. in_brand_tenant: brand token anywhere in this record's own text
    for field in ('Name', 'Name_F', 'Ho_Address', 'Ho_Address_F'):
        if regex.search(str(record.get(field) or '')):
            return 'in_brand_tenant'
    # 3. unrelated: brand token nowhere
    return 'unrelated'


def tag_roles(stores: list[dict], config: BrandConfig) -> None:
    """Set store_role + host_store on every record in place.

    Disabled (default): all own_store, host_store ''. Enabled: real 3-way split.
    """
    enabled = bool(config.classification.get('tenant_separation', {}).get('enabled'))
    if not enabled:
        for r in stores:
            r['store_role'] = 'own_store'
            r['host_store'] = ''
        return
    regex = config.compiled_regex
    # seed_parent_msts only — NOT all_parent_msts. discovered_msts records MSTs
    # that were productive Solr search seeds during the sweep (e.g. a sibling
    # company whose branches co-occur with the brand token), not verified
    # brand-owned entities; treating them as own_store would wrongly fold a
    # third party's whole footprint into own_store (see coop-extra's
    # discovered.json: '0309453012' is Đại Thế Giới's MST, not Saigon Co.op's).
    parents = set(config.seed_parent_msts)
    own_store_name_patterns = tuple(
        config.classification.get('tenant_separation', {}).get('own_store_name_patterns', [])
    )
    for r in stores:
        role = _classify_role(r, regex, parents, own_store_name_patterns)
        r['store_role'] = role
        r['host_store'] = parse_host(r, regex) if role == 'in_brand_tenant' else ''


_HOST_EFFECTIVENESS_FIELDS = ['host_store', 'tenant_count', 'first_tenant_date', 'last_tenant_date']


def host_rollup(stores: list[dict]) -> list[dict]:
    """One row per host outlet with tenant_count and first/last tenant open date.

    Only in_brand_tenant rows count. Tenants with no parsed host fall into an
    '(unattributed)' bucket, sorted last. Sorted by tenant_count desc.
    """
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for r in stores:
        if r.get('store_role') != 'in_brand_tenant':
            continue
        label = r.get('host_store') or ''
        key = _host_key(label) or '(unattributed)'
        groups[key].append((label, r))

    rows = []
    for key, items in groups.items():
        labels = [l for l, _ in items if l]
        display = labels[0] if labels else '(unattributed)'
        dates = sorted(
            str(r.get('Establishment_Date') or '')
            for _, r in items if r.get('Establishment_Date')
        )
        rows.append({
            'host_store': display,
            'tenant_count': len(items),
            'first_tenant_date': dates[0] if dates else '',
            'last_tenant_date': dates[-1] if dates else '',
        })

    rows.sort(key=lambda x: (x['host_store'] == '(unattributed)', -x['tenant_count'], x['host_store']))
    return rows


def write_host_effectiveness(stores: list[dict], path) -> None:
    """Write the per-host tenant-count rollup CSV (UTF-8 BOM for Excel)."""
    rows = host_rollup(stores)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=_HOST_EFFECTIVENESS_FIELDS)
        w.writeheader()
        w.writerows(rows)
