"""Transport protocol + RequestsTransport implementation.

Transport is a Protocol so tests inject FakeTransport with zero coupling.
RequestsTransport wraps requests.Session with verify=False, token refresh,
and keepalive — ported from coopfood_scraper.py:28-34,94-108,128,154-165.
"""
from typing import Protocol, runtime_checkable
import json
import re


@runtime_checkable
class Transport(Protocol):
    """Protocol for HTTP transport to DKKD API."""

    def post_search(self, search_field: str, extra: dict | None = None) -> list[dict]:
        """Execute a search query. Returns list of record dicts."""
        ...

    def refresh_token(self) -> bool:
        """Refresh the h_token. Returns True on success."""
        ...

    def keepalive(self) -> None:
        """Send a keepalive request to maintain session."""
        ...


class RequestsTransport:
    """Real HTTP transport using requests library.

    Port of coopfood_scraper.py session/search/refresh logic.
    verify=False for the DKKD API's self-signed cert.
    """

    BASE_URL = 'https://dichvuthongtin.dkkd.gov.vn'
    SEARCH_URL = f'{BASE_URL}/inf/Public/Srv.aspx/GetSearch'
    HOME_PAGE = f'{BASE_URL}/inf/default.aspx'
    KEEPALIVE_URL = f'{BASE_URL}/inf/Public/Srv.aspx/KeepSession'

    HEADERS = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'),
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Content-Type': 'application/json; charset=utf-8',
        'X-Requested-With': 'XMLHttpRequest',
    }

    def __init__(self):
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.session.headers['Referer'] = self.HOME_PAGE
        self.session.verify = False
        self.h_token = ''
        self._fetch_token()

    def _fetch_token(self) -> None:
        """Fetch initial h_token from search page."""
        resp = self.session.get(self.HOME_PAGE)
        m = re.search(r'id="ctl00_hdParameter"[^>]*value="([^"]+)"', resp.text)
        if m:
            self.h_token = m.group(1)

    def post_search(self, search_field: str, extra: dict | None = None) -> list[dict]:
        """Execute search query against DKKD GetSearch API."""
        payload = {'searchField': search_field, 'h': self.h_token}
        if extra:
            payload.update(extra)
        try:
            resp = self.session.post(self.SEARCH_URL, json=payload)
            j = resp.json()
            d = j.get('d')
            if isinstance(d, str) and d:
                d = json.loads(d)
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def refresh_token(self) -> bool:
        """Re-fetch h_token. Returns True on success."""
        try:
            self._fetch_token()
            return bool(self.h_token)
        except Exception:
            return False

    def keepalive(self) -> None:
        """Send a keepalive GET to maintain session."""
        try:
            # The legacy keepalive is a POST with empty JSON
            self.session.post(self.KEEPALIVE_URL, json={}, timeout=10)
        except Exception:
            pass
