"""DkkdEngine: brand-agnostic sweep loop with injected transport.

Port of coopfood_scraper.py:238-283 sweep cadence:
- 0.06s base throttle, 0.25s every 40th query
- Refresh token every 150 queries
- Keepalive every 120 queries
- Checkpoint every 200 queries
- Empty-response recovery after 20 consecutive empties
"""
import json
import time
from pathlib import Path

from dkkd.config import BrandConfig
from dkkd.ingest import Ingester
from dkkd.paths import checkpoint_json, output_dir
from dkkd.strategies.base import Probe


class DkkdEngine:
    """Brand-agnostic scrape engine. Takes a BrandConfig + injected Transport."""

    # Cadence constants — ported verbatim from legacy scraper
    THROTTLE_BASE = 0.06       # 60ms between queries
    THROTTLE_SLOW = 0.25       # 250ms every Nth query
    THROTTLE_SLOW_EVERY = 40
    REFRESH_EVERY = 150
    KEEPALIVE_EVERY = 120
    CHECKPOINT_EVERY = 200
    EMPTY_RECOVERY_THRESHOLD = 20

    def __init__(self, config: BrandConfig, transport, *, brands_dir: Path | None = None,
                 throttle: bool = True):
        self.config = config
        self.transport = transport
        self.brands_dir = brands_dir
        self.throttle = throttle  # False in tests to skip sleeps
        self.ingester = Ingester(config)
        self.total_queries = 0

    @property
    def store_map(self) -> dict[str, dict]:
        return self.ingester.store_map

    @store_map.setter
    def store_map(self, value: dict[str, dict]):
        self.ingester.store_map = value

    def sweep(self, probes: list[Probe], phase_name: str = '') -> int:
        """Run a list of probes through the transport, ingest results, return count added.

        Preserves the legacy cadence: throttle, refresh, keepalive, checkpoint.
        """
        before = len(self.store_map)
        empty_run = 0

        for i, probe in enumerate(probes):
            rows = self.transport.post_search(probe.search_field, probe.extra)
            self.total_queries += 1
            self.ingester.ingest(rows)

            if not rows:
                empty_run += 1
            else:
                empty_run = 0

            # Recovery after consecutive empties
            if empty_run >= self.EMPTY_RECOVERY_THRESHOLD:
                self.transport.refresh_token()
                empty_run = 0

            # Throttle
            if self.throttle:
                if (i + 1) % self.THROTTLE_SLOW_EVERY == 0:
                    time.sleep(self.THROTTLE_SLOW)
                else:
                    time.sleep(self.THROTTLE_BASE)

            # Periodic maintenance
            if (i + 1) % self.REFRESH_EVERY == 0:
                self.transport.refresh_token()
            if (i + 1) % self.KEEPALIVE_EVERY == 0:
                self.transport.keepalive()
            if (i + 1) % self.CHECKPOINT_EVERY == 0:
                self.save_checkpoint()

        added = len(self.store_map) - before
        return added

    def save_checkpoint(self) -> None:
        """Save current store_map to checkpoint file as [[id, record], ...] pairs."""
        cp_path = checkpoint_json(self.config.slug, self.brands_dir)
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        pairs = [[rid, record] for rid, record in self.store_map.items()]
        with open(cp_path, 'w', encoding='utf-8') as f:
            json.dump(pairs, f, ensure_ascii=False)

    def load_checkpoint(self) -> int:
        """Load store_map from checkpoint file. Returns count loaded."""
        cp_path = checkpoint_json(self.config.slug, self.brands_dir)
        if not cp_path.exists():
            return 0
        with open(cp_path, 'r', encoding='utf-8') as f:
            pairs = json.load(f)
        self.store_map = {rid: record for rid, record in pairs}
        return len(self.store_map)

    def export(self, fmt: str = 'json') -> Path:
        """Export store_map to output directory. Returns path to exported file."""
        out_dir = output_dir(self.config.slug, self.brands_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if fmt == 'json':
            out_path = out_dir / f'{self.config.slug}.json'
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(list(self.store_map.values()), f, ensure_ascii=False, indent=2)
        elif fmt == 'csv':
            import csv
            records = list(self.store_map.values())
            if not records:
                out_path = out_dir / f'{self.config.slug}.csv'
                out_path.write_text('')
                return out_path
            out_path = out_dir / f'{self.config.slug}.csv'
            fieldnames = list(records[0].keys())
            with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(records)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        return out_path
