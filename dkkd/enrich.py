"""Date interpolation and GDT status enrichment for DKKD store records.

Provides:
- DateInterpolator: piecewise-linear interpolation of DKKD registration Id â†’ date
- build_calibration_model(): fetch date samples from masothue.com branch pages
- apply_date_interpolation(): set Establishment_Date + Establishment_Year on records
- refine_entity_statuses(): set GDT Status based on parent entity MST mapping
- fetch_mst_branch_names(): scrape official branch names from masothue.com parent page
- enrich_store_names(): populate Name_MST column for vague-named DKKD records
"""
import json
import re
import time
import requests
from datetime import datetime
from dkkd.config import BrandConfig
from dkkd.utils import fold_ascii


class DateInterpolator:
    """Piecewise-linear interpolation of DKKD registration Id â†’ date.

    Built from a set of (Id, timestamp) calibration points collected from
    masothue.com branch pages. Supports extrapolation beyond the calibration
    range using the slope of the nearest segment.
    """

    def __init__(self, samples: list[tuple[int, float]]):
        self.samples = sorted(samples, key=lambda x: x[0])
        self.ids = [x[0] for x in self.samples]
        self.times = [x[1] for x in self.samples]

    def interpolate(self, target_id: int, **_) -> float | None:
        """Interpolate a date timestamp for a given DKKD registration Id."""
        if not self.samples:
            return None
        if target_id in self.ids:
            return self.times[self.ids.index(target_id)]
        if len(self.samples) == 1:
            return self.times[0]

        # Extrapolate left
        if target_id < self.ids[0]:
            slope = (self.times[1] - self.times[0]) / (self.ids[1] - self.ids[0])
            return self.times[0] + slope * (target_id - self.ids[0])

        # Extrapolate right
        if target_id > self.ids[-1]:
            slope = (self.times[-1] - self.times[-2]) / (self.ids[-1] - self.ids[-2])
            return self.times[-1] + slope * (target_id - self.ids[-1])

        # Interpolate within range
        for i in range(len(self.ids) - 1):
            if self.ids[i] <= target_id <= self.ids[i + 1]:
                slope = (self.times[i + 1] - self.times[i]) / (self.ids[i + 1] - self.ids[i])
                return self.times[i] + slope * (target_id - self.ids[i])

        return self.times[0]


def _parse_date(date_str: str) -> float | None:
    """Parse YYYY-MM-DD date string to Unix timestamp."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").timestamp()
    except Exception:
        return None


def _format_ts(ts: float) -> str:
    """Format Unix timestamp to YYYY-MM-DD string."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


_FORMAT_B_CALIB_RE = re.compile(r'^(\d{10})-(\d{3})$')


def _dedup_x(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Collapse duplicate x-values by averaging their timestamps; return sorted."""
    by_x: dict[float, list[float]] = {}
    for x, t in samples:
        by_x.setdefault(x, []).append(t)
    return sorted((x, sum(v) / len(v)) for x, v in by_x.items())


def _loo_mae(samples: list[tuple[float, float]]) -> float | None:
    """Leave-one-out MAE (in days) of a piecewise DateInterpolator on one axis.

    Returns None when fewer than 3 points (LOO not meaningful).
    """
    if len(samples) < 3:
        return None
    errs = []
    for i in range(len(samples)):
        train = _dedup_x([p for j, p in enumerate(samples) if j != i])
        if len(train) < 2:
            continue
        pred = DateInterpolator(train).interpolate(samples[i][0])
        if pred is None:
            continue
        errs.append(abs(pred - samples[i][1]) / 86400.0)
    return sum(errs) / len(errs) if errs else None


# Domain sanity bound for any interpolated date: a store cannot be registered
# before Vietnam's business registry era (~2000) nor in the future.  This bounds
# a degenerate Id-axis slope (near-duplicate Ids) without truncating valid
# in-domain extrapolation the way an observed-range clamp would.
_DATE_FLOOR_TS = datetime(2000, 1, 1).timestamp()


class _MstAxisModel:
    """A per-parent-MST date model on a chosen x-axis (suffix or Id), with a
    domain sanity bound used to clamp out-of-range extrapolation.

    axis:    'suffix' (branch NNN integer) or 'id' (global DKKD Id).
    model:   piecewise DateInterpolator fitted on (axis-value â†’ timestamp) points.
    lo/hi:   clamp window [2000-01-01, today] applied to every prediction.
    n:       number of calibration anchors.
    fit_mae: the chosen axis's own leave-one-out MAE in days (None if n < 3) â€”
             measures how well the model self-validates, and is the primary
             confidence signal.  A high-anchor MST whose axis does not correlate
             with date (non-monotonic re-registration, e.g. SJC) has many anchors
             but a large fit_mae, so it is correctly NOT high-confidence.
    """

    # Confidence thresholds on the model's own LOO MAE (calendar-meaningful):
    # a quarter for 'high', a year for 'medium'.
    _HIGH_FIT_DAYS = 90.0
    _MED_FIT_DAYS = 365.0
    # Minimum anchors for each tier â€” a fit_mae from < 5 points is not a reliable
    # estimate (a 3-point LOO trains on 2), so such MSTs stay 'low' regardless.
    _HIGH_MIN_N = 8
    _MED_MIN_N = 5

    def __init__(self, axis: str, model: 'DateInterpolator', lo: float, hi: float,
                 n: int, fit_mae: float | None = None):
        self.axis = axis
        self.model = model
        self.lo = lo
        self.hi = hi
        self.n = n
        self.fit_mae = fit_mae

    def predict(self, suffix: int, target_id: int) -> float | None:
        x = suffix if self.axis == 'suffix' else target_id
        pred = self.model.interpolate(x)
        if pred is None:
            return None
        return max(self.lo, min(self.hi, pred))

    def is_extrapolated(self, suffix: int, target_id: int) -> bool:
        x = suffix if self.axis == 'suffix' else target_id
        return not (self.model.ids[0] <= x <= self.model.ids[-1])


def _build_mst_axis_model(suffix_pts: list[tuple[int, float]],
                          id_pts: list[tuple[int, float]],
                          today_ts: float) -> '_MstAxisModel | None':
    """Select the better x-axis for one parent MST and build its clamped model.

    Within a parent MST the DKKD Id order usually tracks filing order, which is
    chronological â€” so Id is the default, *bounded-axis*-aware choice.  But when a
    brand mass-refiles many branches in a single DKKD session (PNJ, precita) the
    Ids cluster while the real GDT dates span years; there the bounded branch
    suffix (1â€“999) is the safer signal.

    Selection rule: pick the axis with the lower unclamped leave-one-out MAE,
    *tie-breaking to the bounded suffix axis* â€” Id is chosen only when it is
    strictly better.  This keeps Id for the monotonic brands (coop-food, winmart,
    circle-k â€¦) while rejecting Id's catastrophic extrapolation on the scrambled
    ones.  Predictions are clamped to the domain window [2000-01-01, today] so a
    degenerate slope (near-duplicate Ids) cannot produce a wild date, without
    truncating valid in-domain extrapolation.
    """
    if len(suffix_pts) < 2:
        return None
    lo, hi = _DATE_FLOOR_TS, today_ts
    n = len(suffix_pts)

    suf_loo = _loo_mae([(float(s), t) for s, t in suffix_pts])
    id_loo = _loo_mae([(float(i), t) for i, t in id_pts])
    use_id = (id_loo is not None) and (suf_loo is None or id_loo < suf_loo)

    if use_id:
        return _MstAxisModel('id', DateInterpolator(id_pts), lo, hi, n, fit_mae=id_loo)
    return _MstAxisModel('suffix', DateInterpolator(suffix_pts), lo, hi, n, fit_mae=suf_loo)


class PerMstDateInterpolator:
    """Per-parent-MST date interpolation with automatic x-axis selection.

    For Format B stores (XXXXXXXXXX-NNN), each parent MST has its own model that
    uses whichever x-axis (branch suffix or global DKKD Id) leave-one-out
    cross-validation showed to be more accurate for that MST (see
    ``_build_mst_axis_model``).  Predictions are clamped to the MST's observed
    calibration date range.

    For Format A stores (00XXX) or stores whose parent MST lacks a model: falls
    back to the global Id-based DateInterpolator built from all calibration points.

    Args:
        per_mst:  Mapping of parent MST â†’ _MstAxisModel.
        fallback: Global Id-based DateInterpolator used when no per-MST model
                  applies (Format A stores, or MSTs with < 2 calibration points).
    """

    def __init__(self, per_mst: dict[str, '_MstAxisModel'], fallback: 'DateInterpolator'):
        self.per_mst = per_mst
        self.fallback = fallback
        # Expose fallback attributes for compatibility with callers that inspect
        # model.samples / model.ids / model.times directly (e.g. tests).
        self.samples = fallback.samples
        self.ids = fallback.ids
        self.times = fallback.times

    def _mst_for(self, gdt_code: str) -> 'tuple[_MstAxisModel, int] | None':
        m = _FORMAT_B_CALIB_RE.match(gdt_code)
        if not m:
            return None
        entry = self.per_mst.get(m.group(1))
        if entry is None:
            return None
        return entry, int(m.group(2))

    def interpolate(self, target_id: int, gdt_code: str = '', **_) -> float | None:
        """Interpolate a date for *target_id* (DKKD Id) given an optional *gdt_code*.

        When *gdt_code* is a Format B code whose parent MST has a model, that
        model's selected axis is used and the prediction clamped to its observed
        date range.  Otherwise delegates to the global Id-based fallback model.
        """
        hit = self._mst_for(gdt_code)
        if hit:
            entry, suffix = hit
            return entry.predict(suffix, target_id)
        return self.fallback.interpolate(target_id)

    def confidence(self, target_id: int, gdt_code: str = '') -> str:
        """Qualitative confidence of the interpolated date for downstream filtering.

        The date *value* is an activation/operation-start estimate (see
        ``apply_date_interpolation``); ``Date_Confidence`` rates whether that value
        is also trustworthy **as a founding date** (*NgÃ y thÃ nh láº­p*) â€” the way
        downstream consumers read ``Establishment_Date``.  A tier above ``low`` is
        therefore only honest where founding validation exists.  Two guards enforce
        that:

        1. **Axis guard (founding-validated axis only).** Only the global DKKD
           **Id** axis has been validated against real *NgÃ y thÃ nh láº­p*: across
           173 hand-fetched founding dates the Id-axis ``high``/``medium`` stores
           held daysâ€“weeks (coop-food/winmart/circle-k), while *every* suffix-axis
           store was years off â€” PNJ's suffix-axis ``medium`` block averaged
           ~7 yr error.  Suffix-axis selection is itself the production signature
           of a mass-refile / decoupled-founding brand (PNJ, SJC, precita): the
           axis fits masothue *activation* dates well (small ``fit_mae``) but
           activation is divorced from founding by years, and *no in-data signal*
           separates "activation = founding" from "activation â‰  founding".  Given
           the brutal error asymmetry (a deserved-good suffix brand merely loses a
           badge â€” its date still emits; a decoupled brand keeping ``medium`` ships
           a multi-year error labelled trustworthy), **suffix-axis is capped at
           ``low`` by design** â€” the same epistemic bucket as the unvalidated
           Format A / global fallback.  This is intentional and permanent.
        2. **Fit guard.** Among Id-axis MSTs, the tier is driven by the model's
           *own* leave-one-out fit (``fit_mae``), not just anchor count â€” a brand
           with many anchors but a non-monotonic axis has a large ``fit_mae`` and
           is correctly NOT high-confidence.

        'high'   â€” Id axis, in-range, â‰¥ 8 anchors, self-validates to â‰¤ 90 days.
        'medium' â€” Id axis, in-range, â‰¥ 5 anchors, self-validates to â‰¤ 365 days.
        'low'    â€” suffix axis (founding-unvalidated), extrapolated, sparse
                   (< 5 anchors / no fit), poor fit, or global / Format A fallback.
        """
        hit = self._mst_for(gdt_code)
        if not hit:
            return 'low'
        entry, suffix = hit
        if entry.is_extrapolated(suffix, target_id) or entry.fit_mae is None:
            return 'low'
        # Axis guard: suffix-axis founding accuracy is unvalidated (and, where
        # checked, always wrong) â€” never promote it above 'low'.
        if entry.axis == 'suffix':
            return 'low'
        if entry.n >= _MstAxisModel._HIGH_MIN_N and entry.fit_mae <= _MstAxisModel._HIGH_FIT_DAYS:
            return 'high'
        if entry.n >= _MstAxisModel._MED_MIN_N and entry.fit_mae <= _MstAxisModel._MED_FIT_DAYS:
            return 'medium'
        return 'low'


# Decoupled mass-refile chains: their legal founding predates their DKKD Id by
# years (old houses equitized mid-2000s, back-loaded into the registry), so their
# founding dates are outliers on the national Idâ†’date curve and must be excluded
# when building the global cross-brand fallback.  See date-inference wiki P1/P6.
_DECOUPLED_SLUGS = frozenset({'pnj', 'sjc', 'precita'})

# Registry event horizon: DKKD Ids start ~2010, so any founding date before this is
# a legacy entity back-loaded into the system â€” its founding is decoupled from the
# Id clock and must not anchor the global curve (date-inference wiki P3).
_REGISTRY_FLOOR_DATE = '2010-01-01'


class GlobalDateInterpolator(DateInterpolator):
    """Cross-brand global Idâ†’date curve, used as the fallback for brands that have
    no per-brand calibration (no masothue/manual points).

    The DKKD ``Id`` is a *national* registry sequence, so a curve fit on many
    brands' real founding dates predicts any chronologically-filed brand's
    registration date to days â€” validated held-out on FPT Shop (MAE 2d, 40/40
    year-match) vs the degenerate 2-point chord it replaces (MAE 897d, 0/40).

    Confidence is its own ``'global'`` tier for in-range predictions: it is
    national-registry-accurate, but â€” like ``low`` â€” is **not** founding-validated
    for decoupled brands, so it is kept distinct from the founding-validated Id-axis
    ``high``/``medium`` tiers.  Out-of-range (extrapolated) predictions fall to
    ``'low'``.
    """

    def confidence(self, target_id: int, gdt_code: str = '', **_) -> str:
        if not self.ids or not (self.ids[0] <= target_id <= self.ids[-1]):
            return 'low'
        return 'global'


def build_global_id_date_model(brands_dir, exclude_slugs=_DECOUPLED_SLUGS) -> 'GlobalDateInterpolator | None':
    """Build one global cross-brand Idâ†’date curve from every brand's
    ``enterprise_details.json`` founding dates (the only real, per-store legal dates
    in the repo).

    Decoupled mass-refile chains (``_DECOUPLED_SLUGS``) are skipped â€” their founding
    predates their Id by years and would bend the curve.  Pass ``exclude_slugs`` to
    additionally drop the target brand when building a held-out benchmark model.

    Anchors whose founding predates the ~2010 registry event horizon are also dropped:
    a legacy entity back-loaded into the registry (e.g. a 1993-founded HQ at a normal
    ~2010 Id) has its founding decoupled from the Id clock and a single such point
    poisons the curve's low-Id segment (the P3 case in the date-inference wiki).

    Returns ``None`` when fewer than 2 anchors are found (caller keeps the legacy
    2-point fallback).
    """
    from dkkd.paths import DEFAULT_BRANDS_DIR
    brands_dir = brands_dir or DEFAULT_BRANDS_DIR
    floor_ts = _parse_date(_REGISTRY_FLOOR_DATE)
    anchors: list[tuple[int, float]] = []
    for ed_file in brands_dir.glob('**/output/enterprise_details.json'):
        slug = ed_file.parent.parent.name
        if slug in exclude_slugs:
            continue
        try:
            ed = json.loads(ed_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for sid, v in ed.items():
            if not isinstance(v, dict) or not v.get('name'):
                continue
            iso = _parse_dkkd_date(v.get('established', '') or '')
            ts = _parse_date(iso) if iso else None
            if ts is None or ts < floor_ts:
                continue
            try:
                anchors.append((int(sid), ts))
            except (TypeError, ValueError):
                continue
    if len(anchors) < 2:
        return None
    deduped = _dedup_x([(float(i), t) for i, t in anchors])
    return GlobalDateInterpolator([(int(x), t) for x, t in deduped])


def build_calibration_model(config: BrandConfig, stores: list[dict],
                             masothue_statuses: dict[str, dict] | None = None,
                             global_fallback: 'DateInterpolator | None' = None) -> 'DateInterpolator | PerMstDateInterpolator':
    """Build a DateInterpolator from manual points, masothue statuses, or a fallback curve.

    Priority order:
    0. ``date_calibration_force_global: true`` in config skips straight to
       ``global_fallback``, overriding every per-brand source below â€” for brands
       whose own manual/masothue calibration is worse than the national curve
       (e.g. hand-guessed manual points with no computed confidence tier; see
       date-inference wiki). No-op (falls through to priority 1) if no
       ``global_fallback`` is supplied.
    1. Manual date_calibration_points in config (highest fidelity)
    2. ngay_hd values from masothue_statuses (pre-fetched, no HTTP needed)
    3. ``global_fallback`` cross-brand Idâ†’date curve, when supplied (national
       registry clock â€” far better than a per-brand straight line; see P6)
    4. 2-point min/max fallback (min_idâ†’date_calibration_min_date, max_idâ†’now)
    """
    cls = config.classification
    if cls.get('date_calibration_force_global') and global_fallback is not None:
        print(f"  [enrich] date_calibration_force_global set; using national cross-brand "
              f"Idâ†’date curve ({len(global_fallback.samples)} anchors)")
        return global_fallback

    manual_points = cls.get('date_calibration_points')
    if manual_points:
        samples = []
        for kid, date_str in manual_points.items():
            ts = _parse_date(date_str)
            if ts:
                samples.append((int(kid), ts))
        if len(samples) >= 2:
            print(f"  [enrich] Built interpolation model from {len(samples)} manual calibration points")
            return DateInterpolator(samples)

    # Use pre-fetched masothue ngay_hd values when available â€” avoids live HTTP
    # and produces a piecewise model that captures non-linear registration rate.
    # For Format B stores (XXXXXXXXXX-NNN) we also build a per-parent-MST model
    # using branch suffix (NNN) as the x-axis, which correlates much more strongly
    # with the actual GDT activation date than the global DKKD Id (râ‰ˆ0.90 vs 0.68).
    if masothue_statuses:
        global_samples: list[tuple[int, float]] = []
        # Per parent MST collect both candidate x-axes: (suffix, ts) and (id, ts).
        per_mst_suffix: dict[str, list[tuple[int, float]]] = {}
        per_mst_id: dict[str, list[tuple[int, float]]] = {}
        for r in stores:
            gdt = (r.get('Enterprise_Gdt_Code') or '').strip()
            entry = masothue_statuses.get(gdt, {})
            ngay_hd = entry.get('ngay_hd', '')
            if not ngay_hd:
                continue
            ts = _parse_date(ngay_hd)
            if not ts:
                continue
            try:
                store_id = int(r['Id'])
            except (KeyError, ValueError):
                continue
            global_samples.append((store_id, ts))
            mb = _FORMAT_B_CALIB_RE.match(gdt)
            if mb:
                parent_mst = mb.group(1)
                suffix = int(mb.group(2))
                per_mst_suffix.setdefault(parent_mst, []).append((suffix, ts))
                per_mst_id.setdefault(parent_mst, []).append((store_id, ts))

        if len(global_samples) >= 2:
            fallback = DateInterpolator(global_samples)
            today_ts = datetime.now().timestamp()
            per_mst_models: dict[str, _MstAxisModel] = {}
            for mst, suffix_pts in per_mst_suffix.items():
                m = _build_mst_axis_model(suffix_pts, per_mst_id[mst], today_ts)
                if m is not None:
                    per_mst_models[mst] = m
            if per_mst_models:
                n_id = sum(1 for m in per_mst_models.values() if m.axis == 'id')
                print(
                    f"  [enrich] Built per-MST interpolation: "
                    f"{len(per_mst_models)} MST model(s) "
                    f"({n_id} Id-axis, {len(per_mst_models) - n_id} suffix-axis) "
                    f"+ global fallback ({len(global_samples)} pts)"
                )
                return PerMstDateInterpolator(per_mst_models, fallback)
            print(f"  [enrich] Built interpolation model from {len(global_samples)} masothue ngay_hd points")
            return fallback

    # No per-brand calibration (manual / masothue) available.  Prefer the global
    # cross-brand Idâ†’date curve over the degenerate 2-point chord when one is
    # supplied â€” the DKKD Id is a national registry clock (date-inference wiki P6).
    if global_fallback is not None:
        print(f"  [enrich] No per-brand calibration; using global cross-brand "
              f"Idâ†’date fallback ({len(global_fallback.samples)} anchors)")
        return global_fallback

    if not stores:
        return DateInterpolator([])
    # Fallback: linear model between min/max Id
    min_id = min(int(r['Id']) for r in stores)
    max_id = max(int(r['Id']) for r in stores)
    min_ts = _parse_date(cls.get('date_calibration_min_date', '2010-01-01'))
    max_ts = datetime.now().timestamp()
    return DateInterpolator([(min_id, min_ts), (max_id, max_ts)])


def _parse_dkkd_date(raw: str) -> str | None:
    """Convert DD/MM/YYYY (DKKD EnterpriseInfo format) to YYYY-MM-DD. Returns None on failure."""
    try:
        d, m, y = raw.strip().split('/')
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        return None


def apply_date_interpolation(stores: list[dict], model: DateInterpolator,
                              min_date_str: str,
                              masothue_statuses: dict[str, dict] | None = None,
                              enterprise_details: dict[str, dict] | None = None) -> None:
    """Set Establishment_Date and Establishment_Year on each store record.

    Source priority (low â†’ high):
    1. Interpolation model  â€” Id â†’ date (piecewise-linear, masothue-calibrated)
    2. masothue ngay_hd     â€” exact activation date per Format B branch
    3. enterprise_details   â€” CAPTCHA-fetched DKKD ``FOUNDING_DATE`` (real legal source)

    Modifies stores in-place.
    """
    min_ts = _parse_date(min_date_str) or 0
    max_ts = datetime.now().timestamp()

    has_conf = hasattr(model, 'confidence')
    for r in stores:
        target_id = int(r['Id'])
        gdt = (r.get('Enterprise_Gdt_Code') or '').strip()
        est_ts = model.interpolate(target_id, gdt_code=gdt)
        if est_ts is None:
            continue
        est_ts = max(min_ts, min(max_ts, est_ts))
        est_date = _format_ts(est_ts)
        r['Establishment_Date'] = est_date
        r['Establishment_Year'] = int(est_date.split('-')[0])
        # Confidence of the *interpolated* estimate (overwritten to 'exact' below
        # when a better source is available for this store).
        r['Date_Confidence'] = model.confidence(target_id, gdt_code=gdt) if has_conf else 'low'

    # Priority 2: exact masothue ngay_hd for Format B stores where available.
    if masothue_statuses:
        exact_count = 0
        for r in stores:
            gdt = (r.get('Enterprise_Gdt_Code') or '').strip()
            entry = masothue_statuses.get(gdt, {})
            ngay_hd = entry.get('ngay_hd', '')
            if ngay_hd:
                r['Establishment_Date'] = ngay_hd
                r['Establishment_Year'] = int(ngay_hd.split('-')[0])
                r['Date_Confidence'] = 'exact'
                exact_count += 1
        if exact_count:
            print(f"  [enrich] Overrode {exact_count} Establishment_Date with exact masothue ngay_hd")

    # Priority 3 (highest): CAPTCHA-fetched DKKD EnterpriseInfo FOUNDING_DATE.
    # Keyed by store Id (string). Format: DD/MM/YYYY â†’ converted to YYYY-MM-DD.
    if enterprise_details:
        exact_count = 0
        for r in stores:
            entry = enterprise_details.get(str(r['Id']), {})
            raw = entry.get('established', '')
            iso = _parse_dkkd_date(raw) if raw else None
            if iso:
                r['Establishment_Date'] = iso
                r['Establishment_Year'] = int(iso.split('-')[0])
                r['Date_Confidence'] = 'exact'
                exact_count += 1
        if exact_count:
            print(f"  [enrich] Overrode {exact_count} Establishment_Date with DKKD EnterpriseInfo founding date")


def refine_entity_statuses(stores: list[dict], entity_status_map: dict[str, str]) -> None:
    """Set GDT Status field based on parent entity MST mapping.

    For each store, check if its Enterprise_Gdt_Code starts with any known
    parent MST. If so, set the corresponding status. Otherwise, default to
    'NNT Ä‘ang hoáº¡t Ä‘á»™ng' (actively operating).

    This is critical for distinguishing legacy VinMart+ stores (ceased entity
    0107078094) from active WinCommerce stores (entity 0104918404).

    Modifies stores in-place.
    """
    for r in stores:
        gdt = str(r.get('Enterprise_Gdt_Code', ''))
        name = str(r.get('Name', ''))
        matched_status = None

        for mst, status in entity_status_map.items():
            if gdt.startswith(mst):
                matched_status = status
                break

        # Additional heuristic: VinMart+ in name with old entity patterns
        if matched_status is None:
            if ('VINMART+' in name or 'VINMART +' in name) and \
               'WINCOMMERCE' not in name and 'VINCOMMERCE' not in name:
                matched_status = entity_status_map.get(
                    '0107078094',
                    'NNT ngá»«ng HÄ nhÆ°ng chÆ°a hoÃ n thÃ nh thá»§ tá»¥c cháº¥m dá»©t hiá»‡u lá»±c MST'
                )

        r['Status'] = matched_status or 'NNT Ä‘ang hoáº¡t Ä‘á»™ng'


# ---------------------------------------------------------------------------
# MST Name Enrichment
# ---------------------------------------------------------------------------

_VAGUE_NAME_PATTERNS = [
    # Bare store types with no location suffix
    re.compile(r'^Cá»¬A HÃ€NG TRANG Sá»¨C PNJ\s*$', re.IGNORECASE),
    re.compile(r'^TRUNG TÃ‚M KIM HOÃ€N PNJ\s*$', re.IGNORECASE),
    re.compile(r'^Cá»¬A HÃ€NG VÃ€NG Báº C PNJ\s*$', re.IGNORECASE),
    # Long corporate-style names with no location after the last dash
    re.compile(
        r'^(?:CHI NHÃNH |Äá»ŠA ÄIá»‚M KINH DOANH (?:CHI NHÃNH )?)?'
        r'(?:CÃ”NG TY (?:TNHH|Cá»” PHáº¦N) )?VÃ€NG Báº C ÄÃ QUÃ PHÃš NHUáº¬N'
        r'\s*[-â€“]\s*(?:Cá»¬A HÃ€NG TRANG Sá»¨C PNJ|TRUNG TÃ‚M KIM HOÃ€N PNJ|Cá»¬A HÃ€NG VÃ€NG Báº C PNJ SILVER)\s*$',
        re.IGNORECASE,
    ),
]


def _is_vague_name(name: str) -> bool:
    """Return True when the DKKD Name field carries no location information."""
    name = (name or '').strip()
    if not name:
        return True
    for pat in _VAGUE_NAME_PATTERNS:
        if pat.match(name):
            return True
    return False


def fetch_mst_branch_names(
    parent_mst: str,
    masothue_parent_url: str,
    headers: dict | None = None,
) -> dict[str, str]:
    """Fetch all registered branch names for *parent_mst* from masothue.com.

    Makes a single HTTP GET to the parent company's masothue.com page
    (e.g. https://masothue.com/0300521758-...) and extracts the official
    registered name for each branch suffix (NNN).

    Returns:
        A dict mapping branch suffix string (e.g. '009') to the official
        registered name, e.g.::

            {'009': 'CHI NHÃNH CÃ”NG TY CP VÃ€NG Báº C ÄÃ QUÃ PHÃš NHUáº¬N â€“ CHI NHÃNH PNJ Cáº¦N THÆ ',
             '039': 'CHI NHÃNH ... PNJ LONG AN', ...}

        Returns an empty dict on HTTP failure.
    """
    _headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'vi,en;q=0.9',
        'Referer': 'https://masothue.com/',
    }
    if headers:
        _headers.update(headers)

    try:
        resp = requests.get(masothue_parent_url, headers=_headers, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        print(f'  [enrich] fetch_mst_branch_names failed for {parent_mst}: {exc}')
        return {}

    # Pattern: href='/MSTXXXXXXXX-NNN-slug' title='...'>OFFICIAL NAME</a>
    # NOTE: masothue renders each branch entry twice â€” once with the human
    # name and once with the raw GDT code as link text (e.g. "0300521758-042").
    # We only keep the FIRST match per suffix (the human-readable name) and
    # explicitly skip any match whose text looks like a raw MST code.
    _raw_mst_re = re.compile(r'^\d{10}-\d{3}$')
    pattern = re.compile(
        rf"href='(/{re.escape(parent_mst)}-([0-9]{{3}})-[^']+)'\s+"
        rf"title='[^']*'>([^<]+)</a>"
    )
    suffix_to_name: dict[str, str] = {}
    for _path, suffix, name in pattern.findall(resp.text):
        name = name.strip()
        if suffix in suffix_to_name:
            continue                      # keep first (human-readable) match
        if _raw_mst_re.match(name):
            continue                      # skip raw GDT code entries
        suffix_to_name[suffix] = name

    print(
        f'  [enrich] fetch_mst_branch_names: {len(suffix_to_name)} '
        f'branch names fetched for {parent_mst}'
    )
    return suffix_to_name


def enrich_store_names(
    stores: list[dict],
    config: BrandConfig,
) -> int:
    """Populate the Name_MST column with official masothue.com names.

    For each record whose DKKD ``Name`` field is considered 'vague' (no
    location suffix, see ``_is_vague_name``), look up the official registered
    branch name from masothue.com and write it to ``Name_MST``.

    Records with a meaningful ``Name`` still receive ``Name_MST`` as an
    additional audit column (set to the same value so it is always non-empty).

    Triggered only when the brand config contains a ``name_enrichment`` block::

        name_enrichment:
          masothue_parent_urls:
            - parent_mst: "0300521758"
              url: "https://masothue.com/0300521758-..."

    Args:
        stores: List of store dicts (modified in-place).
        config: Brand configuration.

    Returns:
        Number of records whose Name_MST differs from Name (i.e. was enriched).
    """
    ne_config = config.classification.get('name_enrichment')
    if not ne_config:
        return 0

    parent_entries = ne_config.get('masothue_parent_urls', [])
    if not parent_entries:
        return 0

    # Build consolidated suffixâ†’name map across all parent MSTs
    suffix_name_map: dict[str, str] = {}   # '0300521758-009' â†’ official name
    for entry in parent_entries:
        parent_mst = entry.get('parent_mst', '')
        url = entry.get('url', '')
        if not parent_mst or not url:
            continue
        branch_map = fetch_mst_branch_names(parent_mst, url)
        for suffix, name in branch_map.items():
            full_key = f'{parent_mst}-{suffix}'
            suffix_name_map[full_key] = name

    if not suffix_name_map:
        return 0

    enriched = 0
    for r in stores:
        raw_name = (r.get('Name') or '').strip()
        gdt = (r.get('Enterprise_Gdt_Code') or '').strip()

        # Resolve official name from MST map (keyed by full GDT code)
        official_name = suffix_name_map.get(gdt, '')

        if not official_name:
            # Fallback: also check Enterprise_Code for direct matches
            official_name = suffix_name_map.get(r.get('Enterprise_Code', ''), '')

        if official_name and _is_vague_name(raw_name):
            r['Name_MST'] = official_name
            enriched += 1
        else:
            # Keep Name_MST = raw Name so the column is always populated
            r['Name_MST'] = official_name or raw_name

    return enriched


def refine_statuses_from_dpi(stores: list[dict], dpi_status_file: str, config: BrandConfig | None = None) -> None:
    """Cross-reference stores against a DPI Excel/CSV dissolution list.
    
    Identifies inactive/dissolved tax codes from the DPI spreadsheet and
    updates DKKD store statuses and operating flags to closed in-place.
    """
    import pandas as pd
    from pathlib import Path
    
    path = Path(dpi_status_file)
    if not path.exists():
        print(f"  [dpi] Warning: DPI status file does not exist: {path}")
        return
        
    print(f"  [dpi] Loading DPI status file: {path.name}")
    try:
        if path.suffix.lower() in ('.xlsx', '.xls'):
            df = pd.read_excel(path, dtype=str)
        else:
            df = pd.read_csv(path, dtype=str)
    except Exception as e:
        print(f"  [dpi] Error loading file: {e}")
        return
        
    # Standardize column names
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # Identify tax code column
    code_col = None
    for col in df.columns:
        if any(k in col for k in ['gdt', 'tax_code', 'mÃ£ sá»‘ thuáº¿', 'ma so thue', 'mst']):
            code_col = col
            break
    if not code_col:
        for col in df.columns:
            if any(k in col for k in ['mÃ£ sá»‘', 'ma so', 'tax', 'code', 'doanh nghiá»‡p', 'doanh nghiep']):
                code_col = col
                break
    if not code_col:
        for col in df.columns:
            sample = df[col].dropna().head(20).astype(str).tolist()
            if any(re.match(r'^\d{10}(?:-\d{3})?$', s.strip()) for s in sample):
                code_col = col
                break
                
    if not code_col:
        print("  [dpi] Error: Could not find tax code / MST column in the DPI file.")
        return
        
    print(f"  [dpi] Found tax code column: '{code_col}'")
    
    # Identify status column (optional)
    status_col = None
    for col in df.columns:
        if any(k in col for k in ['tráº¡ng thÃ¡i', 'trang thai', 'ghi chÃº', 'ghi chu', 'notes', 'tÃ¬nh tráº¡ng', 'tinh trang', 'status']):
            status_col = col
            break
            
    # Load inactive tax codes
    inactive_codes = set()
    parent_msts = set(config.seed_parent_msts or []) if config else set()
    for _, row in df.iterrows():
        code = str(row.get(code_col) or '').strip().replace(' ', '')
        if not code or code == 'nan':
            continue
        # Skip active parent MSTs to prevent parent code collapse
        if code in parent_msts or code.replace('-', '') in parent_msts:
            continue
            
        is_inactive = True
        if status_col and "unmatched" not in Path(dpi_status_file).name.lower():
            status_val = str(row.get(status_col) or '').lower()
            if any(kw in status_val for kw in ['giáº£i thá»ƒ', 'giai the', 'cháº¥m dá»©t', 'cham dut', 'táº¡m ngá»«ng', 'tam ngung', 'Ä‘Ã³ng cá»­a', 'dong cua', 'closed', 'dormant', 'suspended', 'ngÆ°ng', 'ngung']):
                is_inactive = True
            else:
                is_inactive = False
            
        if is_inactive and len(code) > 5:
            inactive_codes.add(code)
            inactive_codes.add(code.replace('-', ''))

    if not inactive_codes:
        print("  [dpi] No dissolved or inactive tax codes identified in DPI file.")
        return
        
    print(f"  [dpi] Loaded {len(inactive_codes)} inactive tax codes from DPI file.")
    
    # Cross-reference DKKD records
    updated_count = 0
    for r in stores:
        gdt = str(r.get('Enterprise_Gdt_Code') or '').strip().replace(' ', '')
        code = str(r.get('Enterprise_Code') or '').strip().replace(' ', '')
        
        is_matched = False
        # Match using exact keys to prevent parent code collapse
        for c in [gdt, gdt.replace('-', ''), code, code.replace('-', '')]:
            if not c or c not in inactive_codes:
                continue
            # If the matched key is a 10-digit parent MST, but the store is a 13-digit branch, skip
            is_branch = '-' in gdt or (gdt.isdigit() and len(gdt) == 13)
            is_inactive_parent = len(c) == 10 and c.isdigit()
            if is_branch and is_inactive_parent:
                continue
            is_matched = True
            break
                
        if is_matched:
            r['Status'] = 'Cháº¥m dá»©t hoáº¡t Ä‘á»™ng'
            r['Core_Operating_Store'] = 'No'
            r['Store_Type_MSN'] = f"{r.get('Store_Type_MSN', 'Closed')} (DPI Closed / Dissolved)"
            updated_count += 1
            
    print(f"  [dpi] Cross-reference complete: marked {updated_count} stores as CLOSED.")


# ---------------------------------------------------------------------------
# Format A branch status resolution
# ---------------------------------------------------------------------------

_FORMAT_A_GDT_RE = re.compile(r'^\d{5}$')
_FORMAT_B_GDT_RE = re.compile(r'^\d{10}-\d{3}$')
# Captures everything after "Táº I " up to "CÃ”NG TY" or end-of-string.
# Handles both branch names ("CHI NHÃNH ... Táº I HÃ€ Ná»˜I") and store names
# ("... Táº I BÃŒNH DÆ¯Æ NG CÃ”NG TY TNHH ...").
_TAI_RE = re.compile(r'Táº I\s+(.+?)(?=\s+CÃ”NG\s+TY|\s*$)', re.UNICODE)


def resolve_format_a_branch_statuses(
    stores: list[dict],
    branch_statuses: dict[str, dict],
    seed_parent_msts: list[str],
) -> int:
    """Set ceased Status for Format A (00XXX GDT) stores via branch-name city matching.

    Format A stores are Ä‘á»‹a Ä‘iá»ƒm kinh doanh with no individual GDT tax code.
    Only CEASED branch statuses are propagated â€” active status is deliberately
    withheld so stores without a locator pin land on Rung 5 (Unverified) rather
    than being falsely promoted by Rung 4 (gdt-own-mst).

    Steps:
    1. Build {city_folded â†’ branch_gdt_code} from branch_statuses entries whose
       names contain "Táº I [CITY]".
    2. For each Format A store with empty Status:
       a. Extract city from "Táº I [CITY]" in Name â†’ fold â†’ look up branch code.
       b. Substring fallback handles partial names (e.g. "BÃ€ Rá»ŠA" â†’ "BÃ€ Rá»ŠA-VÅ¨NG TÃ€U").
       c. If no city hint, fall back to seed_parent_msts.
    3. Set r['Status'] ONLY if the resolved status is a ceased/inactive phrase.

    Args:
        stores: Store records, mutated in place.
        branch_statuses: Unified dict keyed by GDT code with {status, name, ...}.
                         Should include both Format B branch codes and parent MSTs.
        seed_parent_msts: Ordered list of parent MST codes for no-city fallback.

    Returns:
        Number of Format A stores marked ceased.
    """
    if not branch_statuses:
        return 0

    # Build city_folded â†’ branch_gdt_code from branch names
    city_to_gdt: dict[str, str] = {}
    for gdt_code, entry in branch_statuses.items():
        if not _FORMAT_B_GDT_RE.match(gdt_code):
            continue
        bname = (entry.get('name') or '').upper()
        m = _TAI_RE.search(bname)
        if m:
            city_folded = fold_ascii(m.group(1).strip())
            if city_folded:
                city_to_gdt[city_folded] = gdt_code

    # Parent status for the no-Táº I (HCMC/direct) fallback
    parent_status: str | None = None
    for pmst in (seed_parent_msts or []):
        entry = branch_statuses.get(pmst, {})
        s = entry.get('status')
        if s:
            parent_status = s
            break

    # Ceased phrases mirror operating_status._CEASED_PHRASES
    _CEASED = ('cháº¥m dá»©t', 'ngá»«ng hoáº¡t Ä‘á»™ng', 'khÃ´ng hoáº¡t Ä‘á»™ng', 'giáº£i thá»ƒ', 'táº¡m ngá»«ng')

    ceased = 0
    for r in stores:
        gdt = str(r.get('Enterprise_Gdt_Code') or '')
        if not (_FORMAT_A_GDT_RE.match(gdt) and gdt.startswith('00')):
            continue
        if r.get('Status'):
            continue  # already enriched by an earlier stage

        name = str(r.get('Name') or '').upper()
        m = _TAI_RE.search(name)
        matched_code: str | None = None

        if m:
            city_folded = fold_ascii(m.group(1).strip())
            matched_code = city_to_gdt.get(city_folded)
            if not matched_code:
                # Substring fallback: "ba ria" âŠ‚ "ba ria vung tau"
                for key, code in city_to_gdt.items():
                    if city_folded in key or key in city_folded:
                        matched_code = code
                        break

        branch_status: str | None = None
        if matched_code:
            branch_status = branch_statuses[matched_code].get('status') or None

        effective_status = branch_status or parent_status
        # Only propagate ceased status â€” active status is not per-store evidence.
        # Stores without a ceased signal stay empty and land on Unverified (Rung 5)
        # unless a locator pin promotes them to Operating (Rung 3).
        if effective_status and any(p in effective_status.lower() for p in _CEASED):
            r['Status'] = effective_status
            ceased += 1

    fmt_a_total = sum(
        1 for r in stores
        if _FORMAT_A_GDT_RE.match(str(r.get('Enterprise_Gdt_Code') or ''))
        and str(r.get('Enterprise_Gdt_Code', '')).startswith('00')
    )
    print(
        f'  [enrich] resolve_format_a_branch_statuses: {ceased}/{fmt_a_total} Format A stores marked ceased '
        f'({len(city_to_gdt)} city keywords mapped)'
    )
    return ceased
