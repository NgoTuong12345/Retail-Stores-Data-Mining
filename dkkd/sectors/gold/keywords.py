"""Gold/jewelry keyword taxonomy with accent variants.

6 keyword groups, each with accented (Vietnamese diacritics) and plain (ASCII) forms.
Used by the gold_discovery strategy to probe the DKKD API with maximum coverage.
"""

from typing import Literal

GOLD_KEYWORD_GROUPS: tuple[dict, ...] = (
    {'name': 'gold_generic', 'accented': 'VÀNG', 'plain': 'VANG', 'signal': 'high', 'variants': []},
    {'name': 'gold_silver', 'accented': 'VÀNG BẠC', 'plain': 'VANG BAC', 'signal': 'high', 'variants': []},
    {
        'name': 'gold_silver_gems',
        'accented': 'VÀNG BẠC ĐÁ QUÝ',
        'plain': 'VANG BAC DA QUY',
        'signal': 'high',
        'variants': ['VÀNG BẠC ĐÁ QUÍ', 'VANG BAC DA QUI'],
    },
    {
        'name': 'goldsmith',
        'accented': 'KIM HOÀN',
        'plain': 'KIM HOAN',
        'signal': 'high',
        'variants': ['KIM HÒAN'],
    },
    {'name': 'gold_shop', 'accented': 'TIỆM VÀNG', 'plain': 'TIEM VANG', 'signal': 'low', 'variants': []},
    {'name': 'jewelry', 'accented': 'TRANG SỨC', 'plain': 'TRANG SUC', 'signal': 'low', 'variants': []},
)

def get_keywords(tier: Literal['all', 'high_signal'] = 'all') -> list[str]:
    """Return flat list of keyword strings.

    Args:
        tier: 'all' (15 keywords), 'high_signal' (11 keywords, excludes low-signal groups)
    """
    if tier == 'high_signal':
        groups = [g for g in GOLD_KEYWORD_GROUPS if g['signal'] == 'high']
    elif tier == 'all':
        groups = list(GOLD_KEYWORD_GROUPS)
    else:
        raise ValueError(f"Invalid tier: '{tier}'. Expected 'all' or 'high_signal'.")

    keywords: list[str] = []
    for g in groups:
        if g['accented'] not in keywords:
            keywords.append(g['accented'])
        if g['plain'] != g['accented'] and g['plain'] not in keywords:
            keywords.append(g['plain'])
        for v in g.get('variants', []):
            if v not in keywords:
                keywords.append(v)
    return keywords
