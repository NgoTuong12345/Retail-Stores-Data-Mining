"""Base types for strategy functions."""
from typing import NamedTuple


class Probe(NamedTuple):
    """A single search probe to execute against the DKKD API."""
    search_field: str
    extra: dict | None = None
