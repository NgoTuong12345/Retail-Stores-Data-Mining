import json
import re
from pathlib import Path
from datetime import datetime
import requests
from dkkd.paths import output_dir

class TaxpayerClient:
    URL = "https://hoadondientu.gdt.gov.vn/api/query/guest-companies/regd-status"
    CAPTCHA_URL = "https://hoadondientu.gdt.gov.vn/api/captcha"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        })
        
    def get_captcha(self) -> dict | None:
        try:
            resp = self.session.get(self.CAPTCHA_URL, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None
        
    def query_taxpayer_status(self, mst: str, ckey: str = '', cvalue: str = '') -> dict | None:
        try:
            params = {
                "mst": mst,
                "ckey": ckey,
                "cvalue": cvalue
            }
            resp = self.session.get(self.URL, params=params, timeout=15)
            if resp.status_code == 429:
                return {"error_type": "rate_limit"}
            if resp.status_code == 401:
                return {"error_type": "invalid_captcha"}
            if resp.status_code != 200:
                return None
            
            d = resp.json()
            if not isinstance(d, dict) or not d.get('mst'):
                return None
            
            desc = d.get('trangThaiMoTa') or d.get('taxCodeStatus') or 'Đang hoạt động'
            if "đăng ký sử dụng" in desc:
                status = "NNT đang hoạt động"
            else:
                status = f"NNT {desc.lower()}" if not desc.startswith("NNT") else desc
            
            return {
                "mst": d.get('mst'),
                "name": d.get('tnnt') or d.get('tenNnt', ''),
                "status": status,
                "tax_office": d.get('tcqtqly') or d.get('coQuanThue', ''),
                "checked_at": datetime.now().isoformat(),
                "raw_data": d
            }
        except Exception:
            return None
            
def cache_path(slug: str, brands_dir: Path | None = None) -> Path:
    return output_dir(slug, brands_dir) / 'discovered_statuses.json'
    
def load_status_cache(slug: str, brands_dir: Path | None = None) -> dict:
    p = cache_path(slug, brands_dir)
    cache = {}
    if p.exists():
        with open(p, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            
    # Also load masothue branch statuses if they exist
    p_masothue = p.parent / 'masothue_store_statuses.json'
    if p_masothue.exists():
        try:
            with open(p_masothue, 'r', encoding='utf-8') as f:
                ms_cache = json.load(f)
                for mst, item in ms_cache.items():
                    # Map masothue result → GDT status string. Only map when
                    # there is a real signal: active, terminated (de-listed), or
                    # an explicit ceased status text. A page that resolves but
                    # exposes no status field (e.g. ad-gated địa điểm pages →
                    # empty tinh_trang) carries NO signal and must be skipped,
                    # never defaulted to ceased.
                    if item.get('is_active'):
                        status = "NNT đang hoạt động"
                    elif item.get('not_found'):
                        status = item.get('tinh_trang') or "NNT ngừng hoạt động"
                    elif item.get('tinh_trang'):
                        status = item['tinh_trang']
                    else:
                        continue
                    if mst not in cache:
                        cache[mst] = {
                            "status": status,
                            "name": item.get('name', ''),
                            "checked_at": item.get('checked_at', ''),
                            "raw_data": item
                        }
        except Exception as e:
            print(f"Warning: Failed to load masothue statuses: {e}")
            
    return cache
        
def save_status_cache(slug: str, cache: dict, brands_dir: Path | None = None) -> None:
    p = cache_path(slug, brands_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
