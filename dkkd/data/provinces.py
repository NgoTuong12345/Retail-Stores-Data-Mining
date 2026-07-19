"""Vietnam 63 provinces with accented and plain (ASCII) names.

Each entry is a ProvinceInfo NamedTuple: (slug, accented, plain, region,
region_post_reform). Ordered with top-5 centrally-administered cities first,
followed by remaining provinces ordered geographically.

Both region fields use Vietnam's standard 8-region scheme (Tây Bắc Bộ / Đông
Bắc Bộ / Đồng Bằng Sông Hồng / Bắc Trung Bộ / Nam Trung Bộ / Tây Nguyên /
Đông Nam Bộ / ĐBSCL), but answer different questions:

- `region`: the traditional region for this (pre-July-2025) province itself —
  matches DKKD's actual City_Id granularity, since DKKD never collapsed old
  provinces onto merged ones. Use this for DKKD-sourced data.
- `region_post_reform`: the region of the province this one merged INTO under
  the July 2025 reform (old province -> 2025 merger map -> new province's
  region — same two-step derivation as ~/Documents/Retail Code/
  province_extraction). Use this when the input is current-day address text
  that could be using either the old or new province name (e.g. competitor-
  website scrapes), since old and new names both resolve to the same current
  administrative region.

These two only disagree for provinces whose 2025 merger partner sits in a
different traditional region — 8 of the 63: Hòa Bình, Bắc Giang, Vĩnh Phúc,
Bình Định, Phú Yên, Bình Thuận, Kon Tum, Long An. For every other province
the two columns are identical.
"""

from typing import NamedTuple, Literal

from dkkd.utils import fold_ascii

class ProvinceInfo(NamedTuple):
    slug: str
    accented: str
    plain: str
    region: str
    region_post_reform: str

TOP5_SLUGS = frozenset({'ha-noi', 'ho-chi-minh', 'da-nang', 'hai-phong', 'can-tho'})

PROVINCES: list[ProvinceInfo] = [
    # 5 centrally-administered cities
    ProvinceInfo('ha-noi', 'HÀ NỘI', 'HA NOI', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('ho-chi-minh', 'HỒ CHÍ MINH', 'HO CHI MINH', 'Đông Nam Bộ', 'Đông Nam Bộ'),
    ProvinceInfo('da-nang', 'ĐÀ NẴNG', 'DA NANG', 'Nam Trung Bộ', 'Nam Trung Bộ'),
    ProvinceInfo('hai-phong', 'HẢI PHÒNG', 'HAI PHONG', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('can-tho', 'CẦN THƠ', 'CAN THO', 'ĐBSCL', 'ĐBSCL'),
    # Northern provinces
    ProvinceInfo('ha-giang', 'HÀ GIANG', 'HA GIANG', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('cao-bang', 'CAO BẰNG', 'CAO BANG', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('bac-kan', 'BẮC KẠN', 'BAC KAN', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('tuyen-quang', 'TUYÊN QUANG', 'TUYEN QUANG', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('lao-cai', 'LÀO CAI', 'LAO CAI', 'Tây Bắc Bộ', 'Tây Bắc Bộ'),
    ProvinceInfo('dien-bien', 'ĐIỆN BIÊN', 'DIEN BIEN', 'Tây Bắc Bộ', 'Tây Bắc Bộ'),
    ProvinceInfo('lai-chau', 'LAI CHÂU', 'LAI CHAU', 'Tây Bắc Bộ', 'Tây Bắc Bộ'),
    ProvinceInfo('son-la', 'SƠN LA', 'SON LA', 'Tây Bắc Bộ', 'Tây Bắc Bộ'),
    ProvinceInfo('yen-bai', 'YÊN BÁI', 'YEN BAI', 'Tây Bắc Bộ', 'Tây Bắc Bộ'),
    ProvinceInfo('hoa-binh', 'HÒA BÌNH', 'HOA BINH', 'Tây Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('thai-nguyen', 'THÁI NGUYÊN', 'THAI NGUYEN', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('lang-son', 'LẠNG SƠN', 'LANG SON', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('quang-ninh', 'QUẢNG NINH', 'QUANG NINH', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('bac-giang', 'BẮC GIANG', 'BAC GIANG', 'Đông Bắc Bộ', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('phu-tho', 'PHÚ THỌ', 'PHU THO', 'Đông Bắc Bộ', 'Đông Bắc Bộ'),
    ProvinceInfo('vinh-phuc', 'VĨNH PHÚC', 'VINH PHUC', 'Đồng Bằng Sông Hồng', 'Đông Bắc Bộ'),
    ProvinceInfo('bac-ninh', 'BẮC NINH', 'BAC NINH', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('hai-duong', 'HẢI DƯƠNG', 'HAI DUONG', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('hung-yen', 'HƯNG YÊN', 'HUNG YEN', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('thai-binh', 'THÁI BÌNH', 'THAI BINH', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('ha-nam', 'HÀ NAM', 'HA NAM', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('nam-dinh', 'NAM ĐỊNH', 'NAM DINH', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    ProvinceInfo('ninh-binh', 'NINH BÌNH', 'NINH BINH', 'Đồng Bằng Sông Hồng', 'Đồng Bằng Sông Hồng'),
    # Central provinces
    ProvinceInfo('thanh-hoa', 'THANH HÓA', 'THANH HOA', 'Bắc Trung Bộ', 'Bắc Trung Bộ'),
    ProvinceInfo('nghe-an', 'NGHỆ AN', 'NGHE AN', 'Bắc Trung Bộ', 'Bắc Trung Bộ'),
    ProvinceInfo('ha-tinh', 'HÀ TĨNH', 'HA TINH', 'Bắc Trung Bộ', 'Bắc Trung Bộ'),
    ProvinceInfo('quang-binh', 'QUẢNG BÌNH', 'QUANG BINH', 'Bắc Trung Bộ', 'Bắc Trung Bộ'),
    ProvinceInfo('quang-tri', 'QUẢNG TRỊ', 'QUANG TRI', 'Bắc Trung Bộ', 'Bắc Trung Bộ'),
    ProvinceInfo('thua-thien-hue', 'THỪA THIÊN HUẾ', 'THUA THIEN HUE', 'Bắc Trung Bộ', 'Bắc Trung Bộ'),
    ProvinceInfo('quang-nam', 'QUẢNG NAM', 'QUANG NAM', 'Nam Trung Bộ', 'Nam Trung Bộ'),
    ProvinceInfo('quang-ngai', 'QUẢNG NGÃI', 'QUANG NGAI', 'Nam Trung Bộ', 'Nam Trung Bộ'),
    ProvinceInfo('binh-dinh', 'BÌNH ĐỊNH', 'BINH DINH', 'Nam Trung Bộ', 'Tây Nguyên'),
    ProvinceInfo('phu-yen', 'PHÚ YÊN', 'PHU YEN', 'Nam Trung Bộ', 'Tây Nguyên'),
    ProvinceInfo('khanh-hoa', 'KHÁNH HÒA', 'KHANH HOA', 'Nam Trung Bộ', 'Nam Trung Bộ'),
    ProvinceInfo('ninh-thuan', 'NINH THUẬN', 'NINH THUAN', 'Nam Trung Bộ', 'Nam Trung Bộ'),
    ProvinceInfo('binh-thuan', 'BÌNH THUẬN', 'BINH THUAN', 'Nam Trung Bộ', 'Tây Nguyên'),
    ProvinceInfo('kon-tum', 'KON TUM', 'KON TUM', 'Tây Nguyên', 'Nam Trung Bộ'),
    ProvinceInfo('gia-lai', 'GIA LAI', 'GIA LAI', 'Tây Nguyên', 'Tây Nguyên'),
    ProvinceInfo('dak-lak', 'ĐẮK LẮK', 'DAK LAK', 'Tây Nguyên', 'Tây Nguyên'),
    ProvinceInfo('dak-nong', 'ĐẮK NÔNG', 'DAK NONG', 'Tây Nguyên', 'Tây Nguyên'),
    ProvinceInfo('lam-dong', 'LÂM ĐỒNG', 'LAM DONG', 'Tây Nguyên', 'Tây Nguyên'),
    # Southern provinces
    ProvinceInfo('binh-phuoc', 'BÌNH PHƯỚC', 'BINH PHUOC', 'Đông Nam Bộ', 'Đông Nam Bộ'),
    ProvinceInfo('tay-ninh', 'TÂY NINH', 'TAY NINH', 'Đông Nam Bộ', 'Đông Nam Bộ'),
    ProvinceInfo('binh-duong', 'BÌNH DƯƠNG', 'BINH DUONG', 'Đông Nam Bộ', 'Đông Nam Bộ'),
    ProvinceInfo('dong-nai', 'ĐỒNG NAI', 'DONG NAI', 'Đông Nam Bộ', 'Đông Nam Bộ'),
    ProvinceInfo('ba-ria-vung-tau', 'BÀ RỊA VŨNG TÀU', 'BA RIA VUNG TAU', 'Đông Nam Bộ', 'Đông Nam Bộ'),
    ProvinceInfo('long-an', 'LONG AN', 'LONG AN', 'ĐBSCL', 'Đông Nam Bộ'),
    ProvinceInfo('tien-giang', 'TIỀN GIANG', 'TIEN GIANG', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('ben-tre', 'BẾN TRE', 'BEN TRE', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('tra-vinh', 'TRÀ VINH', 'TRA VINH', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('vinh-long', 'VĨNH LONG', 'VINH LONG', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('dong-thap', 'ĐỒNG THÁP', 'DONG THAP', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('an-giang', 'AN GIANG', 'AN GIANG', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('kien-giang', 'KIÊN GIANG', 'KIEN GIANG', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('hau-giang', 'HẬU GIANG', 'HAU GIANG', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('soc-trang', 'SÓC TRĂNG', 'SOC TRANG', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('bac-lieu', 'BẠC LIÊU', 'BAC LIEU', 'ĐBSCL', 'ĐBSCL'),
    ProvinceInfo('ca-mau', 'CÀ MAU', 'CA MAU', 'ĐBSCL', 'ĐBSCL'),
]

REGION_BY_ACCENTED: dict[str, str] = {p.accented: p.region for p in PROVINCES}
REGION_POST_REFORM_BY_ACCENTED: dict[str, str] = {p.accented: p.region_post_reform for p in PROVINCES}

def get_province_amplifiers(tier: Literal['all', 'top5', 'rest'] = 'all') -> list[ProvinceInfo]:
    """Return province list filtered by tier."""
    if tier == 'top5':
        return [p for p in PROVINCES if p.slug in TOP5_SLUGS]
    elif tier == 'rest':
        return [p for p in PROVINCES if p.slug not in TOP5_SLUGS]
    elif tier == 'all':
        return list(PROVINCES)
    raise ValueError(f"Invalid tier: '{tier}'. Expected 'all', 'top5', or 'rest'.")

def get_accent_variants(name: str) -> list[str]:
    """Generate both old and new accent placements for compound vowels (e.g., HÓA/HOÁ, HÒA/HOÀ)."""
    variants = {name}
    replacements = [
        ("ÓA", "OÁ"), ("ÒA", "OÀ"), ("ỎA", "OẢ"), ("ÕA", "OÃ"), ("ỌA", "OẠ"),
        ("OÁ", "ÓA"), ("OÀ", "ÒA"), ("OẢ", "ỎA"), ("OÃ", "ÕA"), ("OẠ", "ỌA"),
        ("óa", "oá"), ("òa", "oà"), ("ỏa", "oả"), ("õa", "oã"), ("ọa", "oạ"),
        ("oá", "óa"), ("oà", "òa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
    ]
    for old, new in replacements:
        if old in name:
            variants.add(name.replace(old, new))
    return sorted(list(variants))


def _ascii_fold(text: str) -> str:
    """Case-preserving Vietnamese ASCII fold used by province callers."""
    return fold_ascii(text, lower=False)


def get_all_province_amplifiers() -> list[str]:
    """Return standard, accent-variant, ASCII-folded, and uppercase province forms."""
    amplifiers: set[str] = set()
    for province in PROVINCES:
        names = {province.accented, province.accented.title()}
        for name in names:
            amplifiers.add(name)
            amplifiers.add(name.upper())
            for variant in get_accent_variants(name):
                amplifiers.add(variant)
                amplifiers.add(variant.upper())
            folded = _ascii_fold(name)
            amplifiers.add(folded)
            amplifiers.add(folded.upper())
    return sorted(amplifiers)
