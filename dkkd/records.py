"""SweepState: derived counters from the record store."""
from dataclasses import dataclass, field
from dkkd.utils import parse_gdt


@dataclass
class SweepState:
    """Holds the current state of a brand's scrape: record store + phase history."""
    store_map: dict[str, dict]
    phase_history: list[dict] = field(default_factory=list)

    @property
    def total_records(self) -> int:
        return len(self.store_map)

    @property
    def discovered_msts(self) -> set[str]:
        """Parent MSTs extracted from branch-format Enterprise_Gdt_Code values."""
        msts = set()
        for r in self.store_map.values():
            gdt = r.get('Enterprise_Gdt_Code') or ''
            parsed = parse_gdt(gdt)
            if parsed['format'] == 'branch':
                msts.add(parsed['parent_mst'])
        return msts

    @property
    def max_counter_seq(self) -> int:
        """Max sequence number from counter-format GDT codes."""
        mx = 0
        for r in self.store_map.values():
            parsed = parse_gdt(r.get('Enterprise_Gdt_Code') or '')
            if parsed['format'] == 'counter':
                mx = max(mx, parsed['seq'])
        return mx

    @property
    def max_branch_seq(self) -> int:
        """Max branch sequence number from branch-format GDT codes."""
        mx = 0
        for r in self.store_map.values():
            parsed = parse_gdt(r.get('Enterprise_Gdt_Code') or '')
            if parsed['format'] == 'branch':
                mx = max(mx, parsed['branch_seq'])
        return mx
