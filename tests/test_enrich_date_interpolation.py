"""Tests for DateInterpolator, build_calibration_model, and apply_date_interpolation.

Covers:
- DateInterpolator: 2-point linear, piecewise, edge cases
- build_calibration_model: masothue_statuses path, fallback path, manual points path
- apply_date_interpolation: interpolation + exact masothue override for Format B
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path

from dkkd.config import BrandConfig
from dkkd.enrich import (
    DateInterpolator,
    GlobalDateInterpolator,
    PerMstDateInterpolator,
    _MstAxisModel,
    _build_mst_axis_model,
    build_calibration_model,
    build_global_id_date_model,
    apply_date_interpolation,
)


def _ts(date_str: str) -> float:
    return datetime.strptime(date_str, '%Y-%m-%d').timestamp()


def _date(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')


def _cfg(**kwargs) -> BrandConfig:
    base = dict(slug='test', name='Test', brand_regex='TEST',
                classification={})
    base.update(kwargs)
    return BrandConfig(**base)


# ─── DateInterpolator ─────────────────────────────────────────────────────────

class TestDateInterpolatorTwoPoints:
    def setup_method(self):
        self.model = DateInterpolator([
            (100, _ts('2010-01-01')),
            (1100, _ts('2020-01-01')),
        ])

    def test_exact_anchor_low(self):
        assert _date(self.model.interpolate(100)) == '2010-01-01'

    def test_exact_anchor_high(self):
        assert _date(self.model.interpolate(1100)) == '2020-01-01'

    def test_midpoint(self):
        # Id=600 is exactly halfway → ~2015-01-01 (within 2 days)
        mid_ts = self.model.interpolate(600)
        mid_date = datetime.fromtimestamp(mid_ts)
        assert abs((mid_date.year + mid_date.month / 12) - (2015.0)) <= 0.1

    def test_extrapolate_left(self):
        # Id < min anchor → extrapolated earlier than 2010-01-01
        ts = self.model.interpolate(50)
        assert ts < _ts('2010-01-01')

    def test_extrapolate_right(self):
        ts = self.model.interpolate(2100)
        assert ts > _ts('2020-01-01')

    def test_empty_model_returns_none(self):
        m = DateInterpolator([])
        assert m.interpolate(500) is None

    def test_single_point_returns_that_point(self):
        m = DateInterpolator([(500, _ts('2015-06-15'))])
        assert _date(m.interpolate(999)) == '2015-06-15'


class TestDateInterpolatorPiecewise:
    def setup_method(self):
        # Three points with different slopes between segments
        self.model = DateInterpolator([
            (100,  _ts('2010-01-01')),
            (600,  _ts('2013-01-01')),   # slow segment: 3 years / 500 units
            (1100, _ts('2020-01-01')),   # fast segment: 7 years / 500 units
        ])

    def test_piecewise_uses_correct_segment(self):
        # Id=350 is in the slow segment (100–600)
        ts350 = self.model.interpolate(350)
        # Id=850 is in the fast segment (600–1100)
        ts850 = self.model.interpolate(850)
        # Slow segment: 350 is 50% through → ~2011-07
        slow_date = datetime.fromtimestamp(ts350)
        assert abs((slow_date.year + slow_date.month / 12) - (2011.5)) <= 0.2
        # Fast segment: 850 is 50% through → ~2016-07
        fast_date = datetime.fromtimestamp(ts850)
        assert abs((fast_date.year + fast_date.month / 12) - (2016.5)) <= 0.2

    def test_exact_middle_anchor(self):
        assert _date(self.model.interpolate(600)) == '2013-01-01'


# ─── build_calibration_model ─────────────────────────────────────────────────

class TestBuildCalibrationModelMasothueStatuses:
    """build_calibration_model should use masothue ngay_hd when provided."""

    _STORES = [
        {'Id': '590598',  'Enterprise_Gdt_Code': '0306182043-001', 'Name': 'Store A'},
        {'Id': '2195946', 'Enterprise_Gdt_Code': '0306182043-010', 'Name': 'Store B'},
        {'Id': '9962751', 'Enterprise_Gdt_Code': '0306182043-022', 'Name': 'Store C'},
        {'Id': '5502552', 'Enterprise_Gdt_Code': '00274',           'Name': 'Format A'},  # no ngay_hd
    ]
    _MASOTHUE = {
        '0306182043-001': {'ngay_hd': '2010-12-06', 'is_active': True},
        '0306182043-010': {'ngay_hd': '2015-01-27', 'is_active': True},
        '0306182043-022': {'ngay_hd': '2023-11-07', 'is_active': True},
    }

    def _model(self):
        cfg = _cfg()
        return build_calibration_model(cfg, self._STORES, masothue_statuses=self._MASOTHUE)

    def test_uses_masothue_points_not_fallback(self):
        # With 3 masothue points the model must have exactly those 3 samples,
        # not the 2-point min/max fallback.
        model = self._model()
        assert len(model.samples) == 3

    def test_anchor_ids_match_masothue_keys(self):
        model = self._model()
        assert 590598 in model.ids
        assert 2195946 in model.ids
        assert 9962751 in model.ids

    def test_exact_date_for_calibration_id(self):
        model = self._model()
        result = _date(model.interpolate(590598))
        assert result == '2010-12-06'

    def test_format_a_store_ignored_by_calibration(self):
        # Format A has no ngay_hd in masothue_statuses → not a calibration point
        model = self._model()
        ids_in_model = model.ids
        assert 5502552 not in ids_in_model

    def test_masothue_without_ngay_hd_skipped(self):
        masothue = dict(self._MASOTHUE)
        masothue['0306182043-001'] = {'ngay_hd': '', 'is_active': True}  # empty date
        cfg = _cfg()
        model = build_calibration_model(cfg, self._STORES, masothue_statuses=masothue)
        # Only 2 usable points remain — model should still build from those 2
        assert len(model.samples) == 2
        assert 590598 not in model.ids


class TestBuildCalibrationModelFallback:
    """Without masothue data, falls back to 2-point min/max model."""

    _STORES = [
        {'Id': '384901',  'Enterprise_Gdt_Code': '00001', 'Name': 'First'},
        {'Id': '5000000', 'Enterprise_Gdt_Code': '00100', 'Name': 'Mid'},
        {'Id': '9000000', 'Enterprise_Gdt_Code': '00200', 'Name': 'Last'},
    ]

    def test_fallback_two_points_min_max(self):
        cfg = _cfg()
        model = build_calibration_model(cfg, self._STORES)
        assert len(model.samples) == 2
        assert 384901 in model.ids
        assert 9000000 in model.ids

    def test_fallback_min_date_config(self):
        cfg = _cfg(classification={'date_calibration_min_date': '2008-06-01'})
        model = build_calibration_model(cfg, self._STORES)
        assert _date(model.times[0]) == '2008-06-01'


class TestBuildCalibrationModelManualPoints:
    """Manual date_calibration_points take priority over masothue path."""

    _STORES = [
        {'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001', 'Name': 'A'},
    ]
    _MASOTHUE = {
        '0306182043-001': {'ngay_hd': '2010-12-06'},
    }

    def test_manual_points_take_priority(self):
        cfg = _cfg(classification={
            'date_calibration_points': {'200': '2012-03-15', '800': '2019-07-01'}
        })
        model = build_calibration_model(cfg, self._STORES, masothue_statuses=self._MASOTHUE)
        # Manual points win — the masothue path is not reached
        assert 200 in model.ids
        assert 800 in model.ids
        assert 100 not in model.ids


# ─── apply_date_interpolation ─────────────────────────────────────────────────

class TestApplyDateInterpolation:
    _MODEL = DateInterpolator([
        (100,  _ts('2010-01-01')),
        (1000, _ts('2020-01-01')),
    ])

    def test_sets_establishment_date_and_year(self):
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '00001'}]
        apply_date_interpolation(stores, self._MODEL, '2009-01-01')
        assert stores[0]['Establishment_Date'] == '2010-01-01'
        assert stores[0]['Establishment_Year'] == 2010

    def test_clamp_below_min_date(self):
        stores = [{'Id': '50', 'Enterprise_Gdt_Code': '00001'}]  # extrapolates before 2010
        apply_date_interpolation(stores, self._MODEL, '2010-01-01')
        assert stores[0]['Establishment_Date'] >= '2010-01-01'

    def test_exact_masothue_overrides_interpolation_for_format_b(self):
        # Format B store: interpolated date differs from ngay_hd — ngay_hd wins
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001'}]
        masothue = {'0306182043-001': {'ngay_hd': '2010-12-06'}}
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 masothue_statuses=masothue)
        assert stores[0]['Establishment_Date'] == '2010-12-06'
        assert stores[0]['Establishment_Year'] == 2010

    def test_format_a_not_overridden_by_masothue(self):
        # Format A store: no entry in masothue_statuses → keeps interpolated date
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '00274'}]
        masothue = {}
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 masothue_statuses=masothue)
        assert stores[0]['Establishment_Date'] == '2010-01-01'

    def test_masothue_empty_ngay_hd_not_applied(self):
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001'}]
        masothue = {'0306182043-001': {'ngay_hd': ''}}
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 masothue_statuses=masothue)
        # Empty ngay_hd → interpolated date kept
        assert stores[0]['Establishment_Date'] == '2010-01-01'

    def test_enterprise_details_overrides_interpolation(self):
        # CAPTCHA-sourced FOUNDING_DATE beats the interpolation model
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '00001'}]
        ed = {'100': {'established': '15/03/2008'}}
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 enterprise_details=ed)
        assert stores[0]['Establishment_Date'] == '2008-03-15'
        assert stores[0]['Establishment_Year'] == 2008
        assert stores[0]['Date_Confidence'] == 'exact'

    def test_enterprise_details_overrides_masothue(self):
        # CAPTCHA source beats masothue (highest priority)
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001'}]
        masothue = {'0306182043-001': {'ngay_hd': '2010-12-06'}}
        ed = {'100': {'established': '01/01/2005'}}
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 masothue_statuses=masothue, enterprise_details=ed)
        assert stores[0]['Establishment_Date'] == '2005-01-01'
        assert stores[0]['Date_Confidence'] == 'exact'

    def test_enterprise_details_missing_entry_not_applied(self):
        # Store not in enterprise_details → keeps prior result
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001'}]
        masothue = {'0306182043-001': {'ngay_hd': '2010-12-06'}}
        ed = {}  # empty — no entry for this store
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 masothue_statuses=masothue, enterprise_details=ed)
        assert stores[0]['Establishment_Date'] == '2010-12-06'

    def test_enterprise_details_empty_established_not_applied(self):
        stores = [{'Id': '100', 'Enterprise_Gdt_Code': '00001'}]
        ed = {'100': {'established': ''}}
        apply_date_interpolation(stores, self._MODEL, '2009-01-01',
                                 enterprise_details=ed)
        # Empty established → interpolated date kept
        assert stores[0]['Establishment_Date'] == '2010-01-01'


# ─── PerMstDateInterpolator ───────────────────────────────────────────────────

_TODAY = _ts('2026-06-30')


def _suffix_axis_model(pts):
    """Build an _MstAxisModel forced onto the suffix axis (for dispatch tests).

    Computes the real LOO fit_mae so confidence() behaves as in production.
    """
    from dkkd.enrich import _loo_mae
    times = [t for _, t in pts]
    lo, hi = min(times), max(max(times), _TODAY)
    fit = _loo_mae([(float(s), t) for s, t in pts])
    return _MstAxisModel('suffix', DateInterpolator(pts), lo, hi, len(pts), fit_mae=fit)


def _id_axis_model(pts):
    """Build an _MstAxisModel forced onto the Id axis (the validated, founding-
    accurate axis: coop-food / winmart / circle-k Id-axis brands hold days–weeks
    against real Ngày-thành-lập).  Used for the high/medium fit-logic coverage,
    since only the Id axis can earn high/medium confidence (see confidence()).
    """
    from dkkd.enrich import _loo_mae
    times = [t for _, t in pts]
    lo, hi = min(times), max(max(times), _TODAY)
    fit = _loo_mae([(float(i), t) for i, t in pts])
    return _MstAxisModel('id', DateInterpolator(pts), lo, hi, len(pts), fit_mae=fit)


class TestPerMstDateInterpolator:
    """PerMstDateInterpolator: per-MST axis dispatch for Format B, Id fallback otherwise."""

    def _make(self):
        # One parent MST forced onto a suffix-based model: suffix 1→2010, 10→2020
        per_mst = {
            '0300521758': _suffix_axis_model([
                (1,  _ts('2010-01-01')),
                (10, _ts('2020-01-01')),
            ]),
        }
        # Global Id fallback: Id 100→2012, Id 1000→2018
        fallback = DateInterpolator([
            (100,  _ts('2012-01-01')),
            (1000, _ts('2018-01-01')),
        ])
        return PerMstDateInterpolator(per_mst, fallback)

    def test_format_b_uses_suffix_model(self):
        m = self._make()
        result = _date(m.interpolate(99999, gdt_code='0300521758-001'))
        assert result == '2010-01-01'

    def test_format_b_suffix_midpoint(self):
        m = self._make()
        # Suffix 5 is (5-1)/(10-1) = 4/9 of the way between 2010 and 2020 → ~2014.4
        ts = m.interpolate(99999, gdt_code='0300521758-005')
        mid = datetime.fromtimestamp(ts)
        assert abs((mid.year + mid.month / 12) - (2014.4)) <= 0.3

    def test_clamp_to_observed_range_floor(self):
        # Suffix 0 would extrapolate below 2010; clamp pins it at the observed floor.
        m = self._make()
        result = _date(m.interpolate(99999, gdt_code='0300521758-000'))
        assert result == '2010-01-01'

    def test_format_b_unknown_mst_falls_back_to_global(self):
        m = self._make()
        result = _date(m.interpolate(100, gdt_code='9999999999-001'))
        assert result == '2012-01-01'

    def test_format_a_falls_back_to_global(self):
        m = self._make()
        result = _date(m.interpolate(100, gdt_code='00123'))
        assert result == '2012-01-01'

    def test_no_gdt_code_falls_back_to_global(self):
        m = self._make()
        result = _date(m.interpolate(100))
        assert result == '2012-01-01'

    def test_exposes_fallback_samples_for_compat(self):
        m = self._make()
        assert len(m.samples) == 2
        assert 100 in m.ids
        assert 1000 in m.ids

    def test_confidence_low_for_fallback(self):
        m = self._make()
        assert m.confidence(100, gdt_code='00123') == 'low'

    def test_confidence_medium_for_small_mst_in_range(self):
        m = self._make()  # MST has n=2 anchors
        assert m.confidence(99999, gdt_code='0300521758-005') == 'low'

    def test_confidence_high_for_dense_id_axis_in_range(self):
        # 8-anchor Id-axis MST, Id 4 in-range → high confidence.  Only the Id
        # axis can earn high: it is the one validated against real founding
        # (coop-food/winmart/circle-k hold days–weeks); see confidence() docstring.
        pts = [(i, _ts(f'{2010 + i}-01-01')) for i in range(1, 9)]
        per_mst = {'0300521758': _id_axis_model(pts)}
        model = PerMstDateInterpolator(per_mst, DateInterpolator([(1, _ts('2010-01-01')), (2, _ts('2011-01-01'))]))
        assert model.confidence(4, gdt_code='0300521758-004') == 'high'

    def test_confidence_low_when_extrapolated(self):
        pts = [(i, _ts(f'{2010 + i}-01-01')) for i in range(1, 9)]
        per_mst = {'0300521758': _id_axis_model(pts)}
        model = PerMstDateInterpolator(per_mst, DateInterpolator([(1, _ts('2010-01-01')), (2, _ts('2011-01-01'))]))
        # Id 50 is far beyond the [1..8] anchor range → extrapolated → low
        assert model.confidence(50, gdt_code='0300521758-004') == 'low'

    def test_confidence_medium_needs_at_least_five_anchors(self):
        # 4 well-fitting in-range anchors → still 'low' (fit_mae from <5 pts is
        # not a reliable estimate); 5 anchors with the same fit → 'medium'.
        four = [(i, _ts(f'{2010 + i}-01-01')) for i in range(1, 5)]
        five = [(i, _ts(f'{2010 + i}-01-01')) for i in range(1, 6)]
        fb = DateInterpolator([(1, _ts('2010-01-01')), (2, _ts('2011-01-01'))])
        m4 = PerMstDateInterpolator({'0300521758': _id_axis_model(four)}, fb)
        m5 = PerMstDateInterpolator({'0300521758': _id_axis_model(five)}, fb)
        assert m4.confidence(2, gdt_code='0300521758-002') == 'low'
        assert m5.confidence(3, gdt_code='0300521758-003') == 'medium'

    def test_confidence_low_for_dense_but_nonmonotonic_mst(self):
        # 9 Id anchors but Id order is uncorrelated with date (re-registration
        # pattern): many anchors yet a large fit_mae → must NOT be high/medium.
        years = [2010, 2003, 2018, 2001, 2020, 2005, 2016, 2008, 2022]
        pts = [(i + 1, _ts(f'{y}-06-01')) for i, y in enumerate(years)]
        per_mst = {'0300521758': _id_axis_model(pts)}
        model = PerMstDateInterpolator(per_mst, DateInterpolator([(1, _ts('2010-01-01')), (2, _ts('2011-01-01'))]))
        # Id 5 is in-range, MST has 9 anchors, but the axis does not fit →
        # confidence is downgraded to 'low', not falsely 'high'.
        assert model.confidence(5, gdt_code='0300521758-005') == 'low'

    def test_confidence_suffix_axis_capped_at_low(self):
        # Suffix-axis SELECTION is the production signature of a mass-refile /
        # decoupled-founding brand (PNJ, SJC, precita): the axis fits masothue
        # *activation* dates with a small fit_mae, but activation is divorced
        # from legal founding by years.  Validated against 173 real
        # Ngày-thành-lập dates — every suffix-axis 'medium' store was ~7 yr off
        # founding, while Id-axis high/medium held days–weeks.  By design, no
        # suffix-axis MST can ever be high/medium, regardless of how perfectly it
        # self-validates against activation (same epistemic bucket as Format A).
        pts = [(i, _ts(f'{2010 + i}-01-01')) for i in range(1, 9)]  # dense, ~0 fit_mae
        per_mst = {'0300521758': _suffix_axis_model(pts)}
        model = PerMstDateInterpolator(per_mst, DateInterpolator([(1, _ts('2010-01-01')), (2, _ts('2011-01-01'))]))
        # 8 anchors, in-range, near-perfect fit → 'high' on the Id axis; the
        # suffix-axis cap forces 'low'.
        assert model.confidence(99999, gdt_code='0300521758-004') == 'low'


class TestBuildMstAxisModel:
    """_build_mst_axis_model selects the axis with lower LOO, tie-break to suffix."""

    def test_picks_id_when_id_clearly_better(self):
        # Id is perfectly linear with date; suffix order is scrambled.
        suffix_pts = [(3, _ts('2010-01-01')), (1, _ts('2015-01-01')), (2, _ts('2020-01-01'))]
        id_pts     = [(100, _ts('2010-01-01')), (200, _ts('2015-01-01')), (300, _ts('2020-01-01'))]
        m = _build_mst_axis_model(suffix_pts, id_pts, _TODAY)
        assert m.axis == 'id'

    def test_picks_suffix_when_id_scrambled(self):
        # Suffix is linear with date; Ids are clustered (mass-refile) — PNJ pattern.
        suffix_pts = [(1, _ts('2010-01-01')), (2, _ts('2015-01-01')), (3, _ts('2020-01-01'))]
        id_pts     = [(400000, _ts('2010-01-01')), (400001, _ts('2020-01-01')), (400002, _ts('2015-01-01'))]
        m = _build_mst_axis_model(suffix_pts, id_pts, _TODAY)
        assert m.axis == 'suffix'

    def test_tie_breaks_to_suffix(self):
        # Both axes perfectly collinear → identical LOO → bounded suffix wins.
        suffix_pts = [(1, _ts('2010-01-01')), (5, _ts('2015-01-01')), (10, _ts('2020-01-01'))]
        id_pts     = [(100, _ts('2010-01-01')), (500, _ts('2015-01-01')), (1000, _ts('2020-01-01'))]
        m = _build_mst_axis_model(suffix_pts, id_pts, _TODAY)
        assert m.axis == 'suffix'

    def test_returns_none_for_single_point(self):
        m = _build_mst_axis_model([(1, _ts('2010-01-01'))], [(100, _ts('2010-01-01'))], _TODAY)
        assert m is None


class TestBuildCalibrationModelPerMst:
    """build_calibration_model returns PerMstDateInterpolator when Format B stores exist."""

    _STORES = [
        {'Id': '100',  'Enterprise_Gdt_Code': '0300521758-001', 'Name': 'A'},
        {'Id': '500',  'Enterprise_Gdt_Code': '0300521758-005', 'Name': 'B'},
        {'Id': '1000', 'Enterprise_Gdt_Code': '0300521758-010', 'Name': 'C'},
    ]
    _MASOTHUE = {
        '0300521758-001': {'ngay_hd': '2010-01-01'},
        '0300521758-005': {'ngay_hd': '2015-06-01'},
        '0300521758-010': {'ngay_hd': '2020-01-01'},
    }

    def test_returns_per_mst_interpolator(self):
        cfg = _cfg()
        model = build_calibration_model(cfg, self._STORES, masothue_statuses=self._MASOTHUE)
        assert isinstance(model, PerMstDateInterpolator)

    def test_per_mst_exact_anchor(self):
        cfg = _cfg()
        model = build_calibration_model(cfg, self._STORES, masothue_statuses=self._MASOTHUE)
        # Whichever axis is chosen, an exact anchor returns its exact date.
        result = _date(model.interpolate(100, gdt_code='0300521758-001'))
        assert result == '2010-01-01'

    def test_per_mst_midpoint_anchor(self):
        cfg = _cfg()
        model = build_calibration_model(cfg, self._STORES, masothue_statuses=self._MASOTHUE)
        result = _date(model.interpolate(500, gdt_code='0300521758-005'))
        assert result == '2015-06-01'

    def test_format_a_store_uses_global_fallback(self):
        cfg = _cfg()
        model = build_calibration_model(cfg, self._STORES, masothue_statuses=self._MASOTHUE)
        result = _date(model.interpolate(100, gdt_code='00123'))
        assert result is not None  # just verify it doesn't crash


class TestApplyDateInterpolationPerMst:
    """apply_date_interpolation passes gdt_code to PerMstDateInterpolator + sets confidence."""

    def test_per_mst_dispatch_via_apply(self):
        per_mst = {
            '0300521758': _suffix_axis_model([
                (1, _ts('2010-01-01')),
                (5, _ts('2015-01-01')),
            ]),
        }
        fallback = DateInterpolator([(100, _ts('2012-01-01')), (500, _ts('2016-01-01'))])
        model = PerMstDateInterpolator(per_mst, fallback)

        stores = [
            {'Id': '999', 'Enterprise_Gdt_Code': '0300521758-001'},  # Format B → suffix 1
            {'Id': '100', 'Enterprise_Gdt_Code': '00123'},           # Format A → Id fallback
        ]
        apply_date_interpolation(stores, model, '2005-01-01')

        # Format B: suffix 1 → 2010-01-01 from per-MST model
        assert stores[0]['Establishment_Date'] == '2010-01-01'
        assert stores[0]['Establishment_Year'] == 2010
        # Format A: Id=100 → 2012-01-01 from fallback, low confidence
        assert stores[1]['Establishment_Date'] == '2012-01-01'
        assert stores[1]['Date_Confidence'] == 'low'

    def test_exact_masothue_sets_confidence_exact(self):
        per_mst = {'0300521758': _suffix_axis_model([(1, _ts('2010-01-01')), (5, _ts('2015-01-01'))])}
        model = PerMstDateInterpolator(per_mst, DateInterpolator([(100, _ts('2012-01-01')), (500, _ts('2016-01-01'))]))
        stores = [{'Id': '999', 'Enterprise_Gdt_Code': '0300521758-001'}]
        masothue = {'0300521758-001': {'ngay_hd': '2011-03-15'}}
        apply_date_interpolation(stores, model, '2005-01-01', masothue_statuses=masothue)
        assert stores[0]['Establishment_Date'] == '2011-03-15'
        assert stores[0]['Date_Confidence'] == 'exact'


# ─── GlobalDateInterpolator ───────────────────────────────────────────────────

class TestGlobalDateInterpolator:
    """Global cross-brand fallback curve: 'global' confidence in-range, 'low' out."""

    def setup_method(self):
        self.model = GlobalDateInterpolator([
            (100, _ts('2010-01-01')),
            (1000, _ts('2020-01-01')),
        ])

    def test_interpolates_like_base(self):
        assert _date(self.model.interpolate(100)) == '2010-01-01'

    def test_confidence_global_in_range(self):
        assert self.model.confidence(500) == 'global'

    def test_confidence_global_at_anchor(self):
        assert self.model.confidence(100) == 'global'

    def test_confidence_low_when_extrapolated_high(self):
        assert self.model.confidence(5000) == 'low'

    def test_confidence_low_when_extrapolated_low(self):
        assert self.model.confidence(10) == 'low'


# ─── build_global_id_date_model ──────────────────────────────────────────────

class TestBuildGlobalIdDateModel:
    """Scans brands' enterprise_details.json into one cross-brand Id→date curve."""

    @staticmethod
    def _write(root: Path, slug: str, ed: dict):
        d = root / 'cat' / 'sub' / slug / 'output'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'enterprise_details.json').write_text(
            json.dumps(ed, ensure_ascii=False), encoding='utf-8')

    def test_collects_cross_brand_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 'brand-a', {
                '100': {'name': 'A', 'established': '01/01/2012'},
                '1000': {'name': 'B', 'established': '01/01/2018'},
            })
            model = build_global_id_date_model(root)
            assert isinstance(model, GlobalDateInterpolator)
            assert 100 in model.ids
            assert 1000 in model.ids
            assert _date(model.interpolate(100)) == '2012-01-01'

    def test_excludes_decoupled_brands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 'brand-a', {
                '100': {'name': 'A', 'established': '01/01/2012'},
                '1000': {'name': 'B', 'established': '01/01/2018'},
            })
            # pnj is a decoupled mass-refile chain: founding 2004 at a high Id
            # would bend the curve — must be excluded.
            self._write(root, 'pnj', {
                '500': {'name': 'P', 'established': '01/01/2004'},
            })
            model = build_global_id_date_model(root)
            assert 500 not in model.ids

    def test_explicit_exclude_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 'brand-a', {
                '100': {'name': 'A', 'established': '01/01/2012'},
                '1000': {'name': 'B', 'established': '01/01/2018'},
            })
            self._write(root, 'fpt-shop', {
                '500': {'name': 'F', 'established': '01/01/2015'},
            })
            # Excluding the target slug keeps a benchmark honestly held-out.
            model = build_global_id_date_model(root, exclude_slugs={'fpt-shop'})
            assert 500 not in model.ids
            assert 100 in model.ids

    def test_returns_none_with_too_few_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 'brand-a', {
                '100': {'name': 'A', 'established': '01/01/2012'},
            })
            assert build_global_id_date_model(root) is None

    def test_drops_pre_registry_founding_anchors(self):
        # A legacy entity back-loaded into the registry carries a pre-2010 founding
        # at a normal registry Id (founding decoupled from the Id clock — the P3
        # event-horizon case).  Such anchors poison the curve and must be dropped.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 'brand-a', {
                '100': {'name': 'A', 'established': '01/01/2012'},
                '1000': {'name': 'B', 'established': '01/01/2018'},
                '500': {'name': 'Legacy HQ', 'established': '10/09/1993'},
            })
            model = build_global_id_date_model(root)
            assert 500 not in model.ids   # 1993 anchor rejected
            assert 100 in model.ids
            assert 1000 in model.ids

    def test_skips_entries_without_name_or_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 'brand-a', {
                '100': {'name': 'A', 'established': '01/01/2012'},
                '200': {'name': '', 'established': '01/01/2013'},   # no name
                '300': {'name': 'C', 'established': ''},            # no date
                '1000': {'name': 'D', 'established': '01/01/2018'},
            })
            model = build_global_id_date_model(root)
            assert 100 in model.ids
            assert 1000 in model.ids
            assert 200 not in model.ids
            assert 300 not in model.ids


# ─── build_calibration_model: global_fallback ────────────────────────────────

class TestBuildCalibrationModelGlobalFallback:
    """global_fallback replaces the degenerate 2-point chord, but per-brand
    calibration (manual / masothue) still wins."""

    _STORES = [
        {'Id': '384901', 'Enterprise_Gdt_Code': '00001', 'Name': 'First'},
        {'Id': '9000000', 'Enterprise_Gdt_Code': '00200', 'Name': 'Last'},
    ]

    def _gf(self):
        return GlobalDateInterpolator([(100, _ts('2011-01-01')), (1000, _ts('2019-01-01'))])

    def test_uses_global_fallback_over_two_point(self):
        gf = self._gf()
        model = build_calibration_model(_cfg(), self._STORES, global_fallback=gf)
        assert model is gf

    def test_two_point_when_no_global_fallback(self):
        # Unchanged legacy behavior when no global_fallback supplied.
        model = build_calibration_model(_cfg(), self._STORES)
        assert len(model.samples) == 2
        assert 384901 in model.ids
        assert not isinstance(model, GlobalDateInterpolator)

    def test_masothue_beats_global_fallback(self):
        stores = [
            {'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001'},
            {'Id': '200', 'Enterprise_Gdt_Code': '0306182043-002'},
        ]
        masothue = {'0306182043-001': {'ngay_hd': '2012-01-01'},
                    '0306182043-002': {'ngay_hd': '2013-01-01'}}
        model = build_calibration_model(_cfg(), stores,
                                        masothue_statuses=masothue, global_fallback=self._gf())
        assert not isinstance(model, GlobalDateInterpolator)

    def test_manual_points_beat_global_fallback(self):
        cfg = _cfg(classification={
            'date_calibration_points': {'200': '2012-03-15', '800': '2019-07-01'}
        })
        model = build_calibration_model(cfg, self._STORES, global_fallback=self._gf())
        assert not isinstance(model, GlobalDateInterpolator)
        assert 200 in model.ids

    def test_force_global_overrides_manual_points(self):
        cfg = _cfg(classification={
            'date_calibration_force_global': True,
            'date_calibration_points': {'200': '2012-03-15', '800': '2019-07-01'},
        })
        gf = self._gf()
        model = build_calibration_model(cfg, self._STORES, global_fallback=gf)
        assert model is gf
        assert isinstance(model, GlobalDateInterpolator)

    def test_force_global_overrides_masothue(self):
        cfg = _cfg(classification={'date_calibration_force_global': True})
        stores = [
            {'Id': '100', 'Enterprise_Gdt_Code': '0306182043-001'},
            {'Id': '200', 'Enterprise_Gdt_Code': '0306182043-002'},
        ]
        masothue = {'0306182043-001': {'ngay_hd': '2012-01-01'},
                    '0306182043-002': {'ngay_hd': '2013-01-01'}}
        model = build_calibration_model(cfg, stores,
                                        masothue_statuses=masothue, global_fallback=self._gf())
        assert isinstance(model, GlobalDateInterpolator)

    def test_force_global_without_fallback_falls_through_to_two_point(self):
        # No global_fallback supplied -> nothing to force onto; legacy behavior.
        cfg = _cfg(classification={'date_calibration_force_global': True})
        model = build_calibration_model(cfg, self._STORES)
        assert not isinstance(model, GlobalDateInterpolator)


class TestApplyDateInterpolationGlobalTier:
    """A store dated by the global fallback is labelled Date_Confidence='global'."""

    def test_global_confidence_label(self):
        gf = GlobalDateInterpolator([(100, _ts('2011-01-01')), (1000, _ts('2019-01-01'))])
        stores = [{'Id': '500', 'Enterprise_Gdt_Code': '00001'}]
        apply_date_interpolation(stores, gf, '2009-01-01')
        assert stores[0]['Date_Confidence'] == 'global'

    def test_global_extrapolated_is_low(self):
        gf = GlobalDateInterpolator([(100, _ts('2011-01-01')), (1000, _ts('2019-01-01'))])
        stores = [{'Id': '5000', 'Enterprise_Gdt_Code': '00001'}]  # beyond anchor range
        apply_date_interpolation(stores, gf, '2009-01-01')
        assert stores[0]['Date_Confidence'] == 'low'

