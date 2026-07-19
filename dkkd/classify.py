"""Store classification engine for DKKD store records.

Supports both brand-specific rules (WinMart/WinCommerce/MSN) and generic
regex-based rules (e.g. Co.op Food / Bách Hóa Xanh) driven by config.yaml.
"""
import re
from dkkd.geo import is_rural_address
from dkkd.config import BrandConfig, DEFAULT_CORPORATE_KEYWORDS


def _strip_admin_prefix(name: str) -> str:
    """Strip Vietnamese province/city admin prefixes (Tỉnh/Thành phố/TP.) from a name."""
    return (
        name.replace('Tỉnh ', '').replace('tỉnh ', '')
        .replace('Thành phố ', '').replace('Thành Phố ', '')
        .replace('TP. ', '').replace('TP ', '')
        .replace('thành phố ', '').replace('Thành phố', '')
        .strip()
    )


def classify_store(record: dict, config: BrandConfig) -> tuple[str, str, str]:
    """Classify a single store record based on brand configuration.

    Args:
        record: DKKD store record dict
        config: BrandConfig object

    Returns:
        (Store_Brand_Format, Store_Type_MSN, Core_Operating_Store)
    """
    name = str(record.get('Name', '')).upper()
    gdt = str(record.get('Enterprise_Gdt_Code') or '')
    addr = str(record.get('Ho_Address', ''))
    status = record.get('Status') or 'NNT đang hoạt động'
    est_date = record.get('Establishment_Date', '2010-01-01')

    rules = config.classification
    corp_keywords = rules.get('corporate_keywords', None)
    if corp_keywords is None:
        corp_keywords = DEFAULT_CORPORATE_KEYWORDS
    corp_gdt_codes = rules.get('corporate_gdt_codes', [])
    corp_regexes = rules.get('corporate_regexes', [])

    # Also treat bare parent MST registrations as corporate
    parent_msts = set(config.seed_parent_msts) | set(config.discovered_msts)
    is_bare_parent_mst = gdt in parent_msts

    # ── 1. Corporate / Logistics / HQ ──
    is_corporate = (
        any(k in name for k in corp_keywords)
        or gdt in corp_gdt_codes
        or any(re.search(pat, name, re.IGNORECASE) for pat in corp_regexes)
        or name.startswith('CÔNG TY CỔ PHẦN DỊCH VỤ THƯƠNG MẠI')
        or gdt.endswith('-000')
        or is_bare_parent_mst
        or (gdt and '-' not in gdt and not gdt.isdigit())
    )
    if is_corporate:
        return (f'{config.name} (Corporate/Logistics)',
                'Non-Operating / Corporate / Closed',
                'No')

    # ── 2. Inactive / Legacy / Closed ──
    is_active = (status == 'NNT đang hoạt động')
    if not is_active:
        return (f'{config.name} (Legacy/Closed)',
                'Non-Operating / Corporate / Closed',
                'No')

    # ── 3. Brand-specific Convenience / Format ──
    if config.slug == 'winmart':
        rural_kw = rules.get('rural_keywords', [])
        win_date = rules.get('win_launch_date', '2022-09-01')
        msn_map = rules.get('msn_format_map', {})

        is_convenience = ('+' in name or 'WINMART+' in name or 'VINMART+' in name)
        if not is_convenience:
            # Supermarket cap resolution happens in batch; mark as 'Pending' for now
            return ('WinMart (Supermarket)',
                    msn_map.get('WinMart (Supermarket)', 'WMT Sieu thi'),
                    'Pending')

        # Determine rural/urban status
        is_rural = False
        ward_name = record.get('Ward_Name') or ''
        dist_name = record.get('District_Name') or ''
        city_name = record.get('City_Name') or ''

        # Clean province name
        prov_clean = ''
        if city_name:
            prov_clean = _strip_admin_prefix(city_name)
        else:
            from dkkd.geo import parse_geo
            c_parsed, _, _ = parse_geo(addr)
            if c_parsed:
                prov_clean = _strip_admin_prefix(c_parsed)

        key_provinces = {
            'Hồ Chí Minh', 'Hà Nội', 'Đà Nẵng', 'Hải Phòng', 'Cần Thơ',
            'Bình Dương', 'Đồng Nai', 'Quảng Ninh', 'Bà Rịa - Vũng Tàu'
        }
        is_urban_prov = prov_clean in key_provinces

        import unicodedata
        ward_name = str(ward_name).strip()
        dist_name = str(dist_name).strip()

        # 1. Ward-level classification (highest accuracy)
        if ward_name:
            ward_upper = unicodedata.normalize('NFC', ward_name).upper()
            if ward_upper.startswith(('XÃ', 'XA ')):
                is_rural = True
            elif ward_upper.startswith(('THỊ TRẤN', 'THI TRAN', 'TT.', 'TT ')):
                is_rural = True
            elif ward_upper.startswith(('PHƯỜNG', 'PHUONG', 'P.', 'P ')):
                # Wards are urban ONLY in key urban provinces
                is_rural = not is_urban_prov
            else:
                is_rural = is_rural_address(addr, rural_kw)
        else:
            # 2. District-level fallback if Ward is missing
            if dist_name:
                dist_upper = unicodedata.normalize('NFC', dist_name).upper()
                if dist_upper.startswith(('HUYỆN', 'HUYEN', 'H.', 'H ')):
                    is_rural = True
                elif dist_upper.startswith(('QUẬN', 'QUAN', 'Q.', 'Q ')):
                    is_rural = False
                else:
                    is_rural = is_rural_address(addr, rural_kw)
            else:
                # 3. Address-level fallback
                is_rural = is_rural_address(addr, rural_kw)

        if is_rural:
            fmt = 'WinMart+ Nong thon (Rural)'
            return (fmt, msn_map.get(fmt, 'WM+ Nong thon'), 'Yes')

        if est_date >= win_date:
            fmt = 'WiN (Urban - All You Need)'
            return (fmt, msn_map.get(fmt, 'WiN'), 'Yes')

        fmt = 'WinMart+ Thanh thi (Urban)'
        return (fmt, msn_map.get(fmt, 'WM+ Thanh thi'), 'Yes')

    else:
        # Generic brand logic (Co.op Food, Bách Hóa Xanh, etc.)
        matched_format = None
        for pattern, label in config.store_type_rules:
            if re.search(pattern, name, re.IGNORECASE):
                matched_format = label
                break
        
        fmt = matched_format or config.default_store_type or config.name
        return (fmt, fmt, 'Yes')


def resolve_supermarket_operating_status(stores: list[dict], cap: int) -> None:
    """Mark the top `cap` most-recently-registered supermarkets as core operating."""
    supermarkets = [
        r for r in stores
        if r.get('Store_Brand_Format') == 'WinMart (Supermarket)'
    ]
    supermarkets.sort(
        key=lambda x: x.get('Establishment_Date', '2010-01-01'),
        reverse=True,
    )

    active_ids = set(s['Id'] for s in supermarkets[:cap])

    for r in stores:
        if r.get('Store_Brand_Format') == 'WinMart (Supermarket)':
            if r['Id'] in active_ids:
                r['Store_Type_MSN'] = 'WMT Sieu thi'
                r['Core_Operating_Store'] = 'Yes'
            else:
                r['Store_Type_MSN'] = 'WMT Sieu thi (Commercially Closed / Warehouse)'
                r['Core_Operating_Store'] = 'No'


def resolve_operating_cap(stores: list[dict], cap: int) -> None:
    """Keep the top `cap` most recently registered stores as active, mark remainder as dormant."""
    brand_stores = [
        r for r in stores
        if r.get('Core_Operating_Store') == 'Yes'
    ]
    brand_stores.sort(
        key=lambda x: x.get('Establishment_Date', '2010-01-01'),
        reverse=True,
    )

    active_ids = set(s['Id'] for s in brand_stores[:cap])

    for r in stores:
        if r.get('Core_Operating_Store') == 'Yes':
            if r['Id'] not in active_ids:
                r['Core_Operating_Store'] = 'No'
                r['Store_Type_MSN'] = f'{r.get("Store_Type_MSN")} (Commercially Closed / Dormant)'


def resolve_address_deduplication(stores: list[dict], brand_name: str) -> None:
    """Group stores by normalized address and mark older duplicate counters as secondary/dormant."""
    import re
    address_groups = {}
    for r in stores:
        if r.get('Core_Operating_Store') != 'Yes':
            continue
        addr = r.get('Ho_Address') or r.get('Ho_Address_F') or ''
        
        # Normalize address string
        norm = addr.lower()
        norm = re.sub(r'[^a-z0-9\s]', '', norm)
        
        # Standardize common mall spellings
        norm = re.sub(r'\b(co\s*op\s*mart|coop\s*mart|co\s*opmart)\b', 'coopmart', norm)
        norm = re.sub(r'\b(vincom\s*plaza|vincom\s*center|vc)\b', 'vincom', norm)
        norm = re.sub(r'\b(big\s*c|go)\b', 'bigc', norm)
        norm = re.sub(r'\b(aeon\s*mall|aeon)\b', 'aeon', norm)
        norm = re.sub(r'\b(lotte\s*mart|lotte)\b', 'lotte', norm)
        norm = " ".join(norm.split())
        
        if norm not in address_groups:
            address_groups[norm] = []
        address_groups[norm].append(r)
        
    for group in address_groups.values():
        if len(group) <= 1:
            continue
        # Sort newest first based on Establishment_Date
        group.sort(
            key=lambda x: x.get('Establishment_Date', '2010-01-01'),
            reverse=True,
        )
        # Keep newest one as active, mark remainder as co-located counters
        for r in group[1:]:
            r['Core_Operating_Store'] = 'No'
            r['Store_Type_MSN'] = f"{r.get('Store_Type_MSN')} (Co-located Counter)"


def classify_all(stores: list[dict], config: BrandConfig) -> None:
    """Classify all stores in-place using brand configuration."""
    for r in stores:
        fmt, msn, core = classify_store(r, config)
        r['Store_Brand_Format'] = fmt
        r['Store_Type_MSN'] = msn
        r['Core_Operating_Store'] = core
