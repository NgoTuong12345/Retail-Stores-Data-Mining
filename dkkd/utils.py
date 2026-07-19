"""Pure-stdlib text utilities for DKKD scraper."""
import re
import unicodedata

_DMAP = str.maketrans({'đ': 'd', 'Đ': 'D'})


def fold_ascii(text: str, *, lower: bool = True) -> str:
    """Fold Vietnamese text to ASCII lowercase.

    Explicit đ/Đ→d/D mapping before NFD decomposition
    (đ has no canonical decomposition — NFD alone won't remove it).
    NFC normalization first per project rules.
    """
    text = unicodedata.normalize('NFC', text)
    text = text.translate(_DMAP)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if not unicodedata.category(c).startswith('M'))
    return text.lower() if lower else text


def parse_gdt(gdt: str | None) -> dict:
    """Parse Enterprise_Gdt_Code into structured format.

    Port of coopfood_scraper.py:184-193.
    """
    if not gdt:
        return {'format': 'empty'}
    if re.match(r'^\d{5}$', gdt):
        return {'format': 'counter', 'seq': int(gdt)}
    m = re.match(r'^(\d{10})-(\d{3})$', gdt)
    if m:
        return {'format': 'branch', 'parent_mst': m.group(1), 'branch_seq': int(m.group(2))}
    return {'format': 'other', 'raw': gdt}
