"""masothue.com URL and status discovery helpers."""
import re
import time

import requests

from dkkd.utils import fold_ascii


_MASOTHUE_BASE = 'https://masothue.com'
_MASOTHUE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://masothue.com/',
    'Accept-Language': 'vi,en;q=0.9',
}
_MASOTHUE_STATUS_RE = re.compile(
    r"id='tax-status-html'><a[^>]*?title='([^']*)'"
)
_MASOTHUE_STATUS_PREFIX_RE = re.compile(
    r'^tra cứu mã số thuế (?:công ty|cá nhân)\s+'
)
_MASOTHUE_DATE_RE = re.compile(
    r"Ngày hoạt động</td><td[^>]*><span[^>]*>(\d{4}-\d{2}-\d{2})</span>"
)
_FORMAT_B_RE = re.compile(r'^(\d{10})-(\d{3})$')
_CF_BLOCKED = '__CF_BLOCKED__'


def _name_to_slug(name: str) -> str:
    """Convert a DKKD registered name to a masothue.com URL slug."""
    s = fold_ascii(name or '')
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def _masothue_get(path: str) -> tuple[str, str]:
    """GET a masothue.com path. Retries once after 12 s on HTTP 429."""
    url = _MASOTHUE_BASE + path
    try:
        resp = requests.get(url, headers=_MASOTHUE_HEADERS, timeout=15)
        if resp.status_code == 429:
            print(f'  [masothue] 429 rate-limit on {path}, sleeping 12s')
            time.sleep(12)
            resp = requests.get(url, headers=_MASOTHUE_HEADERS, timeout=15)
        if resp.status_code == 403 and resp.headers.get('Cf-Mitigated'):
            return 'cf_blocked', ''
        is_redirected = (resp.history
                         and any(r.status_code in (301, 302) for r in resp.history)
                         and resp.url.rstrip('/') == _MASOTHUE_BASE)
        if resp.status_code != 200 or is_redirected or 'không tồn tại' in resp.text or 'Oops' in resp.text:
            return 'not_found', ''
        return 'ok', resp.text
    except Exception as exc:
        return 'error', str(exc)


def _fetch_html_masothue(path: str) -> str:
    """GET a masothue.com path; return '' on missing/network error."""
    outcome, payload = _masothue_get(path)
    if outcome == 'ok':
        return payload
    if outcome == 'cf_blocked':
        return _CF_BLOCKED
    if outcome == 'error':
        print(f'  [masothue] fetch error {path}: {payload}')
    return ''


def sweep_masothue_urls(
    stores: list[dict],
    delay: float = 1.5,
    seed_parent_msts: set[str] | None = None,
) -> dict[str, str]:
    """Find exact masothue.com store-level URLs for Format B/store records."""
    url_map: dict[str, str] = {}
    parents = seed_parent_msts or set()

    format_b = []
    for r in stores:
        gdt = (r.get('Enterprise_Gdt_Code') or '').strip()
        code = (r.get('Enterprise_Code') or '').strip()

        target_code = ''
        if _FORMAT_B_RE.match(gdt):
            target_code = gdt
        elif gdt.isdigit() and len(gdt) == 10:
            target_code = gdt
        elif code.isdigit() and len(code) == 10:
            target_code = code

        if target_code in parents:
            target_code = ''

        if target_code:
            name = (r.get('Name_F') or r.get('Name') or '').strip()
            format_b.append((target_code, name))

    print(f'  [masothue] URL sweep: {len(format_b)} records to resolve')
    for gdt, name in format_b:
        if gdt in url_map:
            continue
        slug = _name_to_slug(name)
        if not slug:
            continue
        path = f'/{gdt}-{slug}'
        html = _fetch_html_masothue(path)
        if html == _CF_BLOCKED:
            print(f'  [masothue] Cloudflare Bot Fight Mode detected - aborting sweep after {len(url_map)} URLs resolved')
            break
        if html:
            url_map[gdt] = path
        time.sleep(delay)

    print(f'  [masothue] URL sweep complete: {len(url_map)}/{len(format_b)} store URLs verified')
    return url_map


def fetch_masothue_statuses(
    url_map: dict[str, str],
    delay: float = 1.5,
) -> dict[str, dict]:
    """Fetch Tinh trang and Ngay hoat dong for each masothue URL."""
    results: dict[str, dict] = {}

    for gdt, path in url_map.items():
        url = _MASOTHUE_BASE + path
        outcome, payload = _masothue_get(path)

        if outcome == 'cf_blocked':
            print(f'  [masothue] Cloudflare Bot Fight Mode - aborting fetch after {len(results)} results')
            break
        elif outcome == 'error':
            results[gdt] = {
                'tinh_trang': '',
                'ngay_hd': '',
                'url': url,
                'is_active': False,
                'not_found': False,
                'error': payload,
            }
        elif outcome == 'not_found':
            results[gdt] = {
                'tinh_trang': 'Không tồn tại',
                'ngay_hd': '',
                'url': url,
                'is_active': False,
                'not_found': True,
            }
        else:
            html = payload
            sm = _MASOTHUE_STATUS_RE.search(html)
            dm = _MASOTHUE_DATE_RE.search(html)
            tinh_trang = ''
            if sm:
                tinh_trang = _MASOTHUE_STATUS_PREFIX_RE.sub('', sm.group(1).strip()).strip()
            ngay_hd = dm.group(1) if dm else ''
            is_active = 'đang hoạt động' in tinh_trang.lower()
            results[gdt] = {
                'tinh_trang': tinh_trang,
                'ngay_hd': ngay_hd,
                'url': url,
                'is_active': is_active,
                'not_found': False,
            }
        time.sleep(delay)

    active = sum(1 for v in results.values() if v.get('is_active'))
    not_found = sum(1 for v in results.values() if v.get('not_found'))
    inactive = len(results) - active - not_found
    print(
        f'  [masothue] Status fetch complete: {active} active, '
        f'{inactive} inactive, {not_found} terminated (removed from masothue)'
    )
    return results
