"""Ingest: filter rows by brand regex on Name+Name_F, dedup by Id.

Also accepts records whose Enterprise_Gdt_Code matches a known parent MST,
even if the Name doesn't match brand_regex. This captures corporate entities
(warehouses, HQs, logistics, online operations) registered under the parent
company name rather than the brand name.
"""
import re
from dkkd.config import BrandConfig


class Ingester:
    """Filters incoming search results by brand regex and deduplicates by Id.

    Records are accepted if EITHER:
    1. Name or Name_F matches brand_regex, OR
    2. Enterprise_Gdt_Code starts with a known parent MST (seed or discovered)
    """

    def __init__(self, config: BrandConfig):
        self.config = config
        self.store_map: dict[str, dict] = {}
        self._regex = re.compile(config.brand_regex, re.IGNORECASE)
        self._parent_msts = set(config.seed_parent_msts) | set(config.discovered_msts)

    def update_parent_msts(self, new_msts: set[str]) -> None:
        """Add newly discovered MSTs to the acceptance set."""
        self._parent_msts |= new_msts

    def _matches_parent_mst(self, record: dict) -> bool:
        """Check if a record's GDT code is under a known parent MST."""
        if not self._parent_msts:
            return False
        gdt = record.get('Enterprise_Gdt_Code') or ''
        if not gdt:
            return False
        for mst in self._parent_msts:
            # Match branch-format: 'MST-NNN' or bare parent: 'MST'
            if gdt == mst or gdt.startswith(mst + '-'):
                return True
        return False

    def ingest(self, rows: list[dict | None]) -> int:
        """Filter rows by brand regex on Name+Name_F OR parent MST, dedup by Id.

        Returns count of newly added records.
        Port of coopfood_scraper.py:170-182, extended with MST-based acceptance.
        """
        added = 0
        for r in rows:
            if not r or not r.get('Id'):
                continue
            n = (r.get('Name') or '') + ' | ' + (r.get('Name_F') or '')
            name_match = self._regex.search(n)
            mst_match = self._matches_parent_mst(r)
            if not name_match and not mst_match:
                continue
            rid = r['Id']
            if rid not in self.store_map:
                self.store_map[rid] = r
                added += 1
        return added
