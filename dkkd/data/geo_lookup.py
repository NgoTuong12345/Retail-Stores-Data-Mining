"""Centralized Geographic Lookup database for Vietnamese cities, districts, and wards.

Loads pre-compiled DKKD geographic IDs from geo_lookup.json and provides:
- ID to Name lookup
- Robust, diacritic-resilient name to ID search (handling prefix stripping, accent placement, and ASCII folding)
- Regex pattern generation for location-based live sweeps
- Address resolution from raw Vietnamese address strings into DKKD internal IDs
"""

import json
import re
import unicodedata
from pathlib import Path
from dkkd.utils import fold_ascii
from dkkd.geo import parse_geo
from dkkd.data.provinces import PROVINCES

# Load static JSON data lazily
_LOOKUP_DATA = None


def _load_data():
    global _LOOKUP_DATA
    if _LOOKUP_DATA is None:
        json_path = Path(__file__).resolve().parent / 'geo_lookup.json'
        if not json_path.exists():
            # Fallback to empty structure if file does not exist (e.g. in test env before setup)
            _LOOKUP_DATA = {"cities": {}, "districts": {}, "wards": {}}
        else:
            with open(json_path, 'r', encoding='utf-8') as f:
                _LOOKUP_DATA = json.load(f)
    return _LOOKUP_DATA


def normalize_geo_name(name: str) -> str:
    """Normalize a Vietnamese geographic name for comparison and matching.
    
    1. Standardizes to NFC normalization and lowercase.
    2. Case-insensitively strips administrative prefix words (Thành phố, Quận, Xã, etc.).
    3. Normalizes accent placement (e.g. oá/óa) to prevent encoding mismatches.
    4. Converts to ASCII-folded lowercase (e.g. "cau giay").
    """
    if not name:
        return ""
    
    # Standardize normalization and case
    name = unicodedata.normalize('NFC', name).lower()
    
    # Strip common administrative prefix words
    prefixes = [
        "thành phố ", "thành phố", "tỉnh ", "tỉnh", "tp. ", "tp ",
        "quận ", "quận", "huyện ", "huyện", "thị xã ", "thị xã", "tx. ", "tx ",
        "phường ", "phường", "xã ", "xã", "thị trấn ", "thị trấn", "tt. ", "tt ", "p. ", "p "
    ]
    
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if name.startswith(p):
                name = name[len(p):].strip()
                changed = True
                break
                
    # Normalize accent placement on compound vowels
    replacements = [
        ("oá", "óa"), ("oà", "òa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
        ("uý", "úy"), ("uỳ", "ùy"), ("uỷ", "ủy"), ("uỹ", "ũy"), ("uỵ", "ụy"),
    ]
    for old, new in replacements:
        name = name.replace(old, new)
        
    return fold_ascii(name).strip()


class GeoLookup:
    """Singleton-like class providing queries against the DKKD geographic database."""
    
    def __init__(self):
        data = _load_data()
        self.cities = data.get("cities", {})
        self.districts = data.get("districts", {})
        self.wards = data.get("wards", {})
        
        # Build normalized index for fast lookup
        self._city_norm = {normalize_geo_name(name): cid for cid, name in self.cities.items()}
        
        # Multiple districts/wards can share the same name (e.g. "Châu Thành" or "Phường 1")
        # Build a mapping of normalized_name -> list of ids
        self._dist_norm = {}
        for did, info in self.districts.items():
            norm = normalize_geo_name(info["name"])
            if norm not in self._dist_norm:
                self._dist_norm[norm] = []
            self._dist_norm[norm].append(did)
            
        self._ward_norm = {}
        for wid, info in self.wards.items():
            norm = normalize_geo_name(info["name"])
            if norm not in self._ward_norm:
                self._ward_norm[norm] = []
            self._ward_norm[norm].append(wid)

        # City_Id -> (region, region_post_reform) (dkkd.data.provinces).
        # Matched by normalized name against the 63-province list; a couple of
        # City_Ids are post-2025-reform renames of an existing province (e.g.
        # "Thành phố Huế" for old "Tỉnh Thừa Thiên Huế") that don't equal any
        # PROVINCES.plain exactly, so fall back to substring containment —
        # same two-pass approach dkkd.conform.canonicalize_province uses.
        self._city_region: dict[str, str] = {}
        self._city_region_post_reform: dict[str, str] = {}
        for cid, name in self.cities.items():
            # Collapse punctuation (e.g. "Ba Ria - Vung Tau"'s dash) so it
            # doesn't defeat the exact/substring match below.
            norm = re.sub(r'[^a-z0-9 ]', ' ', normalize_geo_name(name))
            norm = re.sub(r'\s+', ' ', norm).strip()
            match = None
            for p in PROVINCES:
                if norm == p.plain.lower():
                    match = p
                    break
            if not match:
                for p in PROVINCES:
                    if norm in p.plain.lower() or p.plain.lower() in norm:
                        match = p
                        break
            if match:
                self._city_region[cid] = match.region
                self._city_region_post_reform[cid] = match.region_post_reform

    def get_region(self, city_id: str | int) -> str | None:
        """Get the traditional Vietnam region for a DKKD City_Id — the region
        of this province itself, not of whatever it merged into in 2025.
        """
        return self._city_region.get(str(city_id))

    def get_region_post_reform(self, city_id: str | int) -> str | None:
        """Get the region of the province this DKKD City_Id's province merged
        into under the July 2025 reform. Identical to get_region() except for
        the 8 provinces whose merger partner sits in a different region.
        """
        return self._city_region_post_reform.get(str(city_id))

    def get_city_name(self, city_id: str | int) -> str | None:
        """Get the city name by its City_Id."""
        return self.cities.get(str(city_id))

    def get_district_name(self, dist_id: str | int) -> str | None:
        """Get the district name by its District_Id."""
        info = self.districts.get(str(dist_id))
        return info["name"] if info else None

    def get_ward_name(self, ward_id: str | int) -> str | None:
        """Get the ward name by its Ward_Id."""
        info = self.wards.get(str(ward_id))
        return info["name"] if info else None

    def find_city_id(self, name: str) -> str | None:
        """Find the City_Id matching a city name."""
        return self._city_norm.get(normalize_geo_name(name))

    def find_district_ids(self, name: str, city_id: str | int | None = None) -> list[str]:
        """Find all matching District_Ids for a district name.
        
        If city_id is supplied, filters results to only those under the specified city.
        """
        norm = normalize_geo_name(name)
        dids = self._dist_norm.get(norm, [])
        if city_id is not None:
            city_id_str = str(city_id)
            dids = [did for did in dids if self.districts[did].get("city_id") == city_id_str]
        return dids

    def find_ward_ids(self, name: str, dist_id: str | int | None = None) -> list[str]:
        """Find all matching Ward_Ids for a ward name.
        
        If dist_id is supplied, filters results to only those under the specified district.
        """
        norm = normalize_geo_name(name)
        wids = self._ward_norm.get(norm, [])
        if dist_id is not None:
            dist_id_str = str(dist_id)
            wids = [wid for wid in wids if self.wards[wid].get("district_id") == dist_id_str]
        return wids

    def generate_regex(self, name: str, level: str) -> str:
        """Generate a robust, diacritic-resilient regex pattern to match this location name.
        
        Supports variations in prefixes (e.g. Q., P., TP.) and accent placement (HÓA vs HOÁ).
        """
        name_clean = name
        prefixes = []
        if level == 'city':
            prefixes = ["Thành phố ", "Thành Phố ", "Tỉnh "]
        elif level == 'district':
            prefixes = ["Quận ", "Huyện ", "Thị xã ", "Thành phố ", "Thị Xã ", "Thành Phố "]
        elif level == 'ward':
            prefixes = ["Phường ", "Xã ", "Thị trấn ", "Thị Trấn "]
            
        for p in prefixes:
            if name_clean.startswith(p):
                name_clean = name_clean[len(p):]
                break
                
        name_clean = name_clean.strip()
        
        # Tone mark replacements (old ↔ new placement)
        swaps = [
            ("ÓA", "OÁ"), ("ÒA", "OÀ"), ("ỎA", "OẢ"), ("ÕA", "OÃ"), ("ỌA", "OẠ"),
            ("OÁ", "ÓA"), ("OÀ", "ÒA"), ("OẢ", "ỎA"), ("OÃ", "ÕA"), ("OẠ", "ỌA"),
            ("óa", "oá"), ("òa", "oà"), ("ỏa", "oả"), ("õa", "oã"), ("ọa", "oạ"),
            ("oá", "óa"), ("oà", "òa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
        ]
        
        variants = {name_clean}
        for old, new in swaps:
            if old in name_clean:
                variants.add(name_clean.replace(old, new))
                
        all_forms = set()
        for v in variants:
            all_forms.add(v)
            all_forms.add(v.upper())
            all_forms.add(fold_ascii(v))
            all_forms.add(fold_ascii(v).upper())
            
        sorted_forms = sorted(list(all_forms), key=len, reverse=True)
        escaped_forms = [re.escape(f) for f in sorted_forms]
        alternatives = "|".join(escaped_forms)
        
        prefix_pattern = ""
        if level == 'city':
            prefix_pattern = r"(?:Thành\s+phố\s+|TP\.?\s*|Tỉnh\s+|T\.?\s*)?"
        elif level == 'district':
            prefix_pattern = r"(?:Quận\s+|Q\.?\s*|Huyện\s+|H\.?\s*|Thị\s+xã\s+|TX\.?\s*|Thành\s+phố\s+|TP\.?\s*)?"
        elif level == 'ward':
            prefix_pattern = r"(?:Phường\s+|P\.?\s*|Xã\s+|Thị\s+trấn\s+|TT\.?\s*)?"
            
        # Custom abbreviation overlays for top cities
        custom_abbrs = []
        if name == "Thành phố Hồ Chí Minh":
            custom_abbrs = ["HCM", "HCMC", "Sài Gòn", "Sai Gon", "TP.HCM", "TP HCM"]
        elif name == "Thành phố Hà Nội":
            custom_abbrs = ["HN", "TP.HN", "TP HN"]
        elif name == "Thành phố Đà Nẵng":
            custom_abbrs = ["ĐN", "DN"]
        elif name == "Thành phố Hải Phòng":
            custom_abbrs = ["HP"]
        elif name == "Thành phố Cần Thơ":
            custom_abbrs = ["CT"]
            
        if custom_abbrs:
            abbr_pattern = "|".join(re.escape(a) for a in custom_abbrs)
            alternatives = f"{alternatives}|{abbr_pattern}"
            
        return rf"\b{prefix_pattern}(?:{alternatives})\b"

    def resolve_address_ids(self, address: str) -> tuple[str | None, str | None, str | None]:
        """Resolve a raw address string into DKKD IDs: (City_Id, District_Id, Ward_Id).
        
        Uses semantic parsing to isolate name fields, then resolves them down
        the DKKD geographic tree.
        """
        if not address:
            return None, None, None
            
        raw_city, raw_dist, raw_ward = parse_geo(address)
        
        cid = None
        did = None
        wid = None
        
        if raw_city:
            cid = self.find_city_id(raw_city)
            
        if raw_dist:
            dids = self.find_district_ids(raw_dist, city_id=cid)
            if dids:
                did = dids[0]  # Take the first matched district under city
                # If city wasn't matched but we found a unique district, back-populate city
                if not cid:
                    cid = self.districts[did].get("city_id")
                    
        if raw_ward:
            wids = self.find_ward_ids(raw_ward, dist_id=did)
            if wids:
                wid = wids[0]
                # If district wasn't matched but we found a unique ward, back-populate district and city
                if not did:
                    did = self.wards[wid].get("district_id")
                    if did and not cid:
                        cid = self.districts[did].get("city_id")
                        
        return cid, did, wid


# Shared global instance
_instance = None


def get_geo_lookup() -> GeoLookup:
    """Get the global GeoLookup instance."""
    global _instance
    if _instance is None:
        _instance = GeoLookup()
    return _instance
