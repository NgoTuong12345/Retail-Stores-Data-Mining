import pytest
from dkkd.sectors.gold.keywords import GOLD_KEYWORD_GROUPS, get_keywords

def test_keyword_group_count():
    assert len(GOLD_KEYWORD_GROUPS) == 6

def test_each_group_has_accented_and_plain():
    for group in GOLD_KEYWORD_GROUPS:
        assert 'accented' in group
        assert 'plain' in group
        assert group['accented'] != group['plain'] or group['accented'].isascii()

def test_get_keywords_all():
    kws = get_keywords('all')
    assert len(kws) == 15
    assert 'VÀNG BẠC ĐÁ QUÍ' in kws
    assert 'VANG BAC DA QUI' in kws
    assert 'KIM HÒAN' in kws

def test_get_keywords_high_signal():
    kws = get_keywords('high_signal')
    assert len(kws) == 11
    assert 'VÀNG BẠC ĐÁ QUÍ' in kws
    assert 'VANG BAC DA QUI' in kws
    assert 'KIM HÒAN' in kws
    for kw in kws:
        assert 'TRANG' not in kw.upper()

def test_get_keywords_invalid_tier():
    with pytest.raises(ValueError, match="Invalid tier: 'invalid'"):
        # type: ignore (testing runtime validation of invalid string input)
        get_keywords('invalid')
