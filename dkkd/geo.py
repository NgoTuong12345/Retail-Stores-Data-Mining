"""Address parsing, rural/urban detection, and address normalization.

Provides utilities for:
- Extracting city/district/ward from Vietnamese address strings
- Detecting rural vs urban addresses via Vietnamese locality keywords
- Normalizing addresses for fuzzy spatial matching (legacy migration audit)
"""
import re
import unicodedata

from dkkd.utils import fold_ascii

_NOISE_WORDS = re.compile(
    r'\b(duong|so|phuong|quan|huyen|xa|tp|thanh pho|tinh|'
    r'viet nam|vietnam|ap|thon|ban|to|pho|kp|khu pho)\b'
)


def parse_geo(addr: str) -> tuple[str | None, str | None, str | None]:
    """Extract (city, district, ward) from a Vietnamese DKKD address string.

    Parses address fields semantically from right to left, with a positional fallback.
    Uses NFC normalization to resolve typing variations (NFD/combining characters).

    Returns:
        Tuple of (city_name, district_name, ward_name). Any may be None.
    """
    if not addr:
        return None, None, None

    addr = unicodedata.normalize('NFC', addr)
    parts = [p.strip() for p in addr.split(',')]
    if len(parts) < 2:
        return None, None, None

    city_name = dist_name = ward_name = None

    # Determine city (last part, excluding Việt Nam)
    if parts[-1].upper() in ('VIỆT NAM', 'VIETNAM'):
        parts = parts[:-1]
    if parts:
        city_name = parts[-1]
        parts = parts[:-1]  # Exclude city from further scanning

    # Scan remaining parts from right to left to find district and ward semantically
    for p in reversed(parts):
        p_upper = p.upper()
        
        # 1. Ward detection
        is_p = p_upper.startswith('PHƯỜNG') or p_upper.startswith('P.') or p_upper.startswith('P ')
        is_x = p_upper.startswith('XÃ') or p_upper.startswith('XA ')
        is_tt = p_upper.startswith('THỊ TRẤN') or p_upper.startswith('THỊ TRÂN') or p_upper.startswith('TT.') or p_upper.startswith('TT ')
        
        if not ward_name and (is_p or is_x or is_tt):
            ward_name = p
            continue
            
        # 2. District detection (avoid matching the city name itself)
        is_q = p_upper.startswith('QUẬN') or p_upper.startswith('Q.') or p_upper.startswith('Q ')
        is_h = p_upper.startswith('HUYỆN') or p_upper.startswith('H.') or p_upper.startswith('H ')
        is_tx = p_upper.startswith('THỊ XÃ') or p_upper.startswith('TX.') or p_upper.startswith('TX ')
        is_tp = p_upper.startswith('THÀNH PHỐ') or p_upper.startswith('TP.') or p_upper.startswith('TP ')
        
        if not dist_name and (is_q or is_h or is_tx or (is_tp and (not city_name or p_upper != city_name.upper()))):
            dist_name = p
            continue

    # Fallback to positional matching if semantic matching did not resolve everything
    if not dist_name or not ward_name:
        orig_parts = [p.strip() for p in addr.split(',')]
        if orig_parts[-1].upper() in ('VIỆT NAM', 'VIETNAM'):
            orig_parts = orig_parts[:-1]
            
        if len(orig_parts) >= 2 and not dist_name:
            p_dist = orig_parts[-2]
            dist_upper = p_dist.upper()
            if any(k in dist_upper for k in ('QUẬN', 'HUYỆN', 'THỊ XÃ', 'THÀNH PHỐ')):
                dist_name = p_dist

        if len(orig_parts) >= 3 and not ward_name:
            p_ward = orig_parts[-3]
            ward_upper = p_ward.upper()
            if any(k in ward_upper for k in ('PHƯỜNG', 'XÃ', 'THỊ TRẤN')):
                ward_name = p_ward

    return city_name, dist_name, ward_name


def is_rural_address(addr: str, rural_keywords: list[str]) -> bool:
    """Check if an address string contains rural Vietnamese locality markers.

    Uses NFC normalization, boundary-aware regex matching, and masks common false
    positives (such as "Gò Vấp" matching "Ấp" or "Thị xã" matching "Xã").

    Args:
        addr: Vietnamese address string
        rural_keywords: List of uppercase keywords indicating rural areas
                       (e.g. ['XÃ', 'ẤP', 'THÔN', 'HUYỆN'])

    Returns:
        True if address contains any rural keyword.
    """
    if not addr:
        return False
    
    # Normalize address string
    addr_norm = unicodedata.normalize('NFC', addr).upper()
    
    # Mask known urban keywords that cause false positives
    addr_norm = re.sub(r'\bTHỊ XÃ\b|\bTHI XA\b|\bTX\b|\bTX\.', 'URBAN_TOWN', addr_norm)
    addr_norm = re.sub(r'\bGÒ VẤP\b|\bGO VAP\b', 'URBAN_DISTRICT', addr_norm)
    addr_norm = re.sub(r'\bXÃ ĐÀN\b|\bXA DAN\b', 'URBAN_STREET', addr_norm)
    addr_norm = re.sub(r'\bĐÌNH THÔN\b|\bDINH THON\b', 'URBAN_STREET', addr_norm)
    addr_norm = re.sub(r'\bHÀ HUYÊN\b|\bHA HUYEN\b', 'URBAN_NAME', addr_norm)
    
    for kw in rural_keywords:
        kw_upper = kw.upper()
        
        if kw_upper in ('XÃ', 'XA'):
            # Match 'XÃ' / 'XA' with word boundary, and ensure not preceded by 'THỊ' / 'THI'
            pattern = r'(?<!THỊ\s)(?<!THI\s)\b' + re.escape(kw_upper) + r'\b'
            if re.search(pattern, addr_norm):
                return True
        elif kw_upper in ('ẤP', 'AP'):
            # Match 'ẤP' / 'AP' as a distinct word
            pattern = r'\b' + re.escape(kw_upper) + r'\b'
            if re.search(pattern, addr_norm):
                return True
        elif kw_upper in ('THÔN', 'THON'):
            # Match 'THÔN' / 'THON' as a distinct word
            pattern = r'\b' + re.escape(kw_upper) + r'\b'
            if re.search(pattern, addr_norm):
                return True
        else:
            # General word boundary check for other keywords (e.g. HUYỆN, HAMLET)
            pattern = r'\b' + re.escape(kw_upper) + r'\b'
            if re.search(pattern, addr_norm):
                return True
                
    return False


def normalize_address_for_matching(addr: str) -> str:
    """Normalize a Vietnamese address for fuzzy spatial matching.

    Strips diacritics, removes common geographic noise words,
    and retains only alphanumeric characters. Used for comparing
    legacy closed store addresses against active store addresses
    during the migration audit.

    Args:
        addr: Vietnamese address string

    Returns:
        Lowercase alphanumeric-only normalized string.
    """
    if not addr:
        return ""
    s = fold_ascii(addr)
    s = _NOISE_WORDS.sub('', s)
    s = re.sub(r'[^a-z0-9]', '', s)
    return s
