"""Passthrough strategy: executes a caller-supplied keyword list verbatim."""
from dkkd.strategies import strategy
from dkkd.strategies.base import Probe
from dkkd.config import BrandConfig
from dkkd.records import SweepState


@strategy('raw')
def raw(config: BrandConfig, state: SweepState, params: dict) -> list[Probe]:
    """Execute keywords from params['probes'] verbatim — no brand-variant joining.

    params:
        probes: semicolon-separated keyword strings, e.g. 'KW1;KW2;KW3'
    """
    keywords = [k.strip() for k in params.get('probes', '').split(';') if k.strip()]
    return [Probe(search_field=k) for k in keywords]
