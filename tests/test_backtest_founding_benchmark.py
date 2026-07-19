"""Tests for _build_founding_benchmark_section — validation of the shipped date
model against hand-fetched real *Ngày thành lập* (founding) ground truth.

Covers:
- No enterprise_details.json → returns ''
- < 3 founding points → 'Insufficient' message
- Accurate Id-axis brand → high tier present, integrity holds
- Decoupled suffix-axis brand (PNJ pattern) → every store labelled 'low',
  multi-year errors never carry high/medium, integrity flag True
"""
import json
import pathlib
import tempfile

from dkkd.backtest import _build_founding_benchmark_section


_MINIMAL_CONFIG = (
    "slug: test-brand\n"
    "name: Test Brand\n"
    "brand_regex: 'TEST'\n"
)


def _write(brands_dir, slug, *, records, details, statuses=None, config=_MINIMAL_CONFIG):
    bd = brands_dir / slug
    out = bd / 'output'
    out.mkdir(parents=True, exist_ok=True)
    (bd / 'config.yaml').write_text(config, encoding='utf-8')
    (bd / 'checkpoint.json').write_text(json.dumps(records), encoding='utf-8')
    (out / 'enterprise_details.json').write_text(
        json.dumps(details, ensure_ascii=False), encoding='utf-8')
    if statuses is not None:
        (out / 'masothue_store_statuses.json').write_text(
            json.dumps(statuses), encoding='utf-8')


def _run(**kw):
    with tempfile.TemporaryDirectory() as d:
        bdir = pathlib.Path(d)
        _write(bdir, 'test-brand', **kw)
        return _build_founding_benchmark_section('test-brand', brands_dir=bdir)


def test_missing_details_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        bdir = pathlib.Path(d)
        bd = bdir / 'test-brand'
        (bd / 'output').mkdir(parents=True)
        (bd / 'config.yaml').write_text(_MINIMAL_CONFIG, encoding='utf-8')
        (bd / 'checkpoint.json').write_text('[]', encoding='utf-8')
        assert _build_founding_benchmark_section('test-brand', brands_dir=bdir) == ''


def test_two_points_insufficient():
    records = [
        [None, {'Id': '100', 'Enterprise_Gdt_Code': '0123456789-001'}],
        [None, {'Id': '200', 'Enterprise_Gdt_Code': '0123456789-002'}],
    ]
    details = {
        '100': {'name': 'A', 'established': '01/01/2010', 'mst': '0123456789-001'},
        '200': {'name': 'B', 'established': '01/01/2012', 'mst': '0123456789-002'},
    }
    result = _run(records=records, details=details)
    assert 'Insufficient' in result


class TestAccurateIdAxis:
    """Id spread tracks date (chronological filing); founding ≈ activation."""

    def _fixtures(self, n=8):
        records, details, statuses = [], {}, {}
        for i in range(1, n + 1):
            sid = str(1000 * i)                       # Ids well spread → Id axis wins
            gdt = f'0123456789-{i:03d}'
            d = f'{2010 + i}-03-15'                    # activation ramp
            records.append([None, {'Id': sid, 'Enterprise_Gdt_Code': gdt}])
            statuses[gdt] = {'ngay_hd': d}
            # founding within ~2 weeks of activation
            details[sid] = {'name': f'S{i}', 'established': f'01/03/{2010 + i}', 'mst': gdt}
        return records, details, statuses

    def test_high_tier_present_and_accurate(self):
        records, details, statuses = self._fixtures(8)
        result = _run(records=records, details=details, statuses=statuses)
        assert 'Activation↔Founding Gap' in result
        assert '| high |' in result
        # Integrity must hold: no high/medium store is years off.
        assert 'off by > 1 year = **True**' in result


class TestDecoupledSuffixAxis:
    """PNJ pattern: clustered Ids + suffix-ramped activation, but founding is
    an early near-constant block → activation estimate is years off founding.
    Every such store must be labelled 'low' and integrity must still hold."""

    def _fixtures(self, n=8):
        records, details, statuses = [], {}, {}
        for i in range(1, n + 1):
            sid = str(400000 + i)                     # clustered Ids → Id axis loses
            gdt = f'0300521758-{i:03d}'
            activation = f'{2013 + i}-01-01'          # activation ramps with suffix
            records.append([None, {'Id': sid, 'Enterprise_Gdt_Code': gdt}])
            statuses[gdt] = {'ngay_hd': activation}
            details[sid] = {'name': f'B{i}', 'established': '15/05/2004', 'mst': gdt}
        return records, details, statuses

    def test_all_low_and_integrity_holds(self):
        records, details, statuses = self._fixtures(8)
        result = _run(records=records, details=details, statuses=statuses)
        assert 'Activation↔Founding Gap' in result
        # No high/medium tier should appear with any count — suffix axis caps at low.
        assert '| high | 0 |' in result
        assert '| medium | 0 |' in result
        # Multi-year errors exist but never carry a trustworthy flag.
        assert 'off by > 1 year = **True**' in result
        # Worst misses must all be 'low'.
        worst = result.split('Largest activation↔founding gaps')[1]
        assert ' high |' not in worst
        assert ' medium |' not in worst
