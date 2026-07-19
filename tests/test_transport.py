"""Tests for Transport protocol and FakeTransport fixture."""
import pytest
from tests.conftest import FakeTransport
from dkkd.transport import Transport


class TestFakeTransport:
    def test_implements_protocol(self):
        ft = FakeTransport()
        assert isinstance(ft, Transport)

    def test_returns_canned_responses(self):
        ft = FakeTransport({'query1': [{'Id': '1'}]})
        assert ft.post_search('query1') == [{'Id': '1'}]
        assert ft.post_search('unknown') == []

    def test_tracks_calls(self):
        ft = FakeTransport()
        ft.post_search('a', {'sortField': 'Id'})
        ft.post_search('b')
        assert len(ft.calls) == 2
        assert ft.calls[0] == ('a', {'sortField': 'Id'})

    def test_refresh_and_keepalive(self):
        ft = FakeTransport()
        assert ft.refresh_token() is True
        ft.keepalive()
        assert ft.refresh_count == 1
        assert ft.keepalive_count == 1
