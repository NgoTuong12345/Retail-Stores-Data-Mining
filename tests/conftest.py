"""Shared test fixtures."""
import json

from dkkd.config import BrandConfig


def make_row(id_, name, name_f=''):
    return {'Id': id_, 'Name': name, 'Name_F': name_f}


def make_optin_config() -> BrandConfig:
    return BrandConfig(
        slug='test-brand',
        name='Test Brand',
        brand_regex='Test Brand',
        classification={'operating_status': {'enabled': True}},
        seed_parent_msts=['0306182043'],
    )


# --- Shared brands/test-brand/ fixture for dkkd.backtest tests ---

_CONVERGED_STATE = {
    'phase_history': [
        {'strategy': 'brand_variants', 'params': {}, 'probes': 10, 'added': 5, 'total': 5},
        {'strategy': 'solr_escape',    'params': {}, 'probes': 5,  'added': 0, 'total': 5},
        {'strategy': 'solr_escape',    'params': {}, 'probes': 50, 'added': 0, 'total': 5},
        {'strategy': 'parent_mst',     'params': {}, 'probes': 5,  'added': 0, 'total': 5},
    ],
    'convergence': {'converged': True, 'rule': '3 consecutive phases yielded 0 new rows'},
}

_MINIMAL_CONFIG = (
    "slug: test-brand\n"
    "name: Test Brand\n"
    "brand_regex: 'CO[\\.\\\\,\\-]?\\s*OP\\s*FOOD|COOPFOOD'\n"
    "spelling_variants:\n"
    "  - 'CO.OP FOOD'\n"
    "seed_parent_msts:\n"
    "  - '0309129418'\n"
)


def setup_test_brand(tmp_path, records, *, state=None, config=None, ground_truth=None):
    """Write a minimal brands/test-brand/ dir (config.yaml + state.json + checkpoint.json,
    optionally output/closure_ground_truth.json) for dkkd.backtest tests."""
    bd = tmp_path / 'test-brand'
    bd.mkdir()
    (bd / 'output').mkdir()
    (bd / 'config.yaml').write_text(config or _MINIMAL_CONFIG, encoding='utf-8')
    (bd / 'state.json').write_text(json.dumps(state or _CONVERGED_STATE), encoding='utf-8')
    (bd / 'checkpoint.json').write_text(json.dumps(records), encoding='utf-8')
    if ground_truth is not None:
        (bd / 'output' / 'closure_ground_truth.json').write_text(
            json.dumps(ground_truth), encoding='utf-8')
    return bd


class FakeTransport:
    """Mock transport for testing: returns canned responses keyed by search_field.

    Usage:
        transport = FakeTransport({
            'CO.OP FOOD': [{'Id': '1', 'Name': 'CO.OP FOOD Store 1'}],
            '+1': [{'Id': '2', 'Name': 'Store 2 CO.OP FOOD'}],
        })
    """

    def __init__(self, responses: dict[str, list[dict]] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict | None]] = []
        self.refresh_count = 0
        self.keepalive_count = 0

    def post_search(self, search_field: str, extra: dict | None = None) -> list[dict]:
        self.calls.append((search_field, extra))
        if search_field in self.responses:
            return list(self.responses[search_field])
        # Strip '+' characters for backwards compatibility with tests using exact dict matching
        stripped = search_field.replace("+", "")
        if stripped in self.responses:
            return list(self.responses[stripped])
        # Support single-space normalization of multiple terms
        normalized = " ".join(stripped.split())
        if normalized in self.responses:
            return list(self.responses[normalized])
        return []

    def refresh_token(self) -> bool:
        self.refresh_count += 1
        return True

    def keepalive(self) -> None:
        self.keepalive_count += 1
