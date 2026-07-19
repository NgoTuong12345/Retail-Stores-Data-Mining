"""Back-test scraped store counts against an external reference report.

Reads brands/<slug>/output/<slug>.csv, filters Core_Operating_Store == 'Yes',
computes format and regional counts, compares against backtest: config, and
writes brands/<slug>/output/<slug>_backtest_report.md.
"""
import json
import re
from datetime import datetime as _dt
from pathlib import Path

from dkkd.paths import output_dir, state_json, checkpoint_json
from dkkd import config as cfg
from dkkd.conform import canonicalize_province, region_for_province


def _parse_province(addr):
    if not isinstance(addr, str):
        return "Unknown"
    parts = addr.split(',')
    if len(parts) < 2:
        return "Unknown"

    prov = parts[-1].strip()
    if prov.upper() in ['VIỆT NAM', 'VIETNAM']:
        prov = parts[-2].strip()

    return canonicalize_province(prov) or "Unknown"


# Traditional 8-region → North/Central/South rollup (dkkd.data.provinces' region field).
_REGION_8_TO_3 = {
    'Tây Bắc Bộ': 'North', 'Đông Bắc Bộ': 'North', 'Đồng Bằng Sông Hồng': 'North',
    'Bắc Trung Bộ': 'Central', 'Nam Trung Bộ': 'Central', 'Tây Nguyên': 'Central',
    'Đông Nam Bộ': 'South', 'ĐBSCL': 'South',
}


def _map_region(prov: str) -> str:
    return _REGION_8_TO_3.get(region_for_province(prov), 'South')  # Default to South


_BRANCH_RE = re.compile(r'^\d{10}-\d{3}$')

_PLAYBOOK_NAMES = {'brand_variants', 'solr_escape', 'parent_mst'}


def _fmt(ts: float | None) -> str:
    return _dt.fromtimestamp(ts).strftime('%Y-%m-%d') if ts else '—'


def _stats(errors: list[float]) -> dict:
    """Error-distribution stats shared by the date-backtest and founding-benchmark
    sections; each section's own _row() picks whichever keys it displays."""
    if not errors:
        return {}
    s = sorted(errors)
    cnt = len(s)
    return {
        'n': cnt,
        'mae': sum(s) / cnt,
        'median': s[cnt // 2],
        'p90': s[min(int(cnt * 0.9), cnt - 1)],
        'max': s[-1],
        'w30': sum(1 for e in s if e <= 30) / cnt * 100,
        'w90': sum(1 for e in s if e <= 90) / cnt * 100,
        'w1y': sum(1 for e in s if e <= 365) / cnt * 100,
    }


def _build_date_backtest_section(slug: str, brands_dir=None) -> str:
    """Leave-one-out cross-validation of DateInterpolator vs masothue ngay_hd ground truth.

    For each Format B store with a known ngay_hd date, rebuilds the piecewise-linear
    model from the remaining N-1 calibration points and measures the prediction error
    in calendar days. Returns a markdown section string ready to append to a report,
    or '' when no masothue_store_statuses.json exists for this brand.
    """
    from datetime import datetime as _dt
    from dkkd.enrich import (
        DateInterpolator, _parse_date, _build_mst_axis_model, PerMstDateInterpolator,
    )

    out = output_dir(slug, brands_dir)
    status_file = out / 'masothue_store_statuses.json'
    if not status_file.exists():
        return ''

    statuses = json.loads(status_file.read_text(encoding='utf-8'))

    cp = checkpoint_json(slug, brands_dir)
    if not cp.exists():
        return ''
    pairs = json.loads(cp.read_text(encoding='utf-8'))
    records = [item[1] if isinstance(item, list) else item for item in pairs]

    gdt_to_id: dict[str, int] = {}
    for r in records:
        gdt = str(r.get('Enterprise_Gdt_Code') or '').strip()
        try:
            gdt_to_id[gdt] = int(r['Id'])
        except (KeyError, ValueError):
            pass

    # Ground truth 4-tuples: (dkkd_id, timestamp, ngay_hd_str, gdt_code)
    ground_truth: list[tuple[int, float, str, str]] = []
    for gdt, entry in statuses.items():
        ngay_hd = (entry.get('ngay_hd') or '').strip()
        if not ngay_hd:
            continue
        store_id = gdt_to_id.get(gdt)
        if store_id is None:
            continue
        ts = _parse_date(ngay_hd)
        if ts:
            ground_truth.append((store_id, ts, ngay_hd, gdt))

    n = len(ground_truth)
    if n < 3:
        return (
            '\n---\n\n## Date Model Accuracy (LOO Cross-Validation)\n\n'
            f'Insufficient masothue calibration data: {n} ground-truth point(s), '
            'need ≥ 3 for leave-one-out validation.\n'
        )

    ground_truth.sort(key=lambda x: x[0])

    def _row(label: str, st: dict) -> str:
        if not st:
            return f'| {label} | 0 | — | — | — | — | — |'
        return (
            f'| {label} | {st["n"]} | {st["mae"]:.1f} | {st["median"]:.1f} | '
            f'{st["p90"]:.1f} | {st["w30"]:.0f}% | {st["w90"]:.0f}% |'
        )

    # LOO cross-validation pass — mirrors PerMstDateInterpolator production logic
    # by calling the same per-MST axis-selection builder (_build_mst_axis_model):
    # each Format B store's parent MST picks the suffix or Id axis by inner-LOO
    # (tie-break to the bounded suffix) and clamps to the domain window;
    # Format A / sparse MSTs fall back to the global Id model.
    # Errors are also stratified by the Date_Confidence bucket each store would
    # receive in production, to verify the confidence flag actually tracks error.
    interp_errors: list[float] = []
    extrap_errors: list[float] = []
    conf_errors: dict[str, list[float]] = {'high': [], 'medium': [], 'low': []}
    miss_list: list[tuple[float, int, str, str, str]] = []

    _fmt_b_re = re.compile(r'^(\d{10})-(\d{3})$')
    today_ts = _dt.now().timestamp()

    # Build the FULL-data production model once, purely to read each store's
    # production Date_Confidence label (the error itself is still measured by the
    # per-fold LOO model below).  This keeps the by-confidence table aligned with
    # what production actually labels, not with per-fold rebuilds that can let a
    # tiny MST clear the fit threshold by luck.
    _full_suffix: dict[str, list[tuple[int, float]]] = {}
    _full_id: dict[str, list[tuple[int, float]]] = {}
    for pt_id, pt_ts, _, pt_gdt in ground_truth:
        mb = _fmt_b_re.match(pt_gdt)
        if mb:
            _full_suffix.setdefault(mb.group(1), []).append((int(mb.group(2)), pt_ts))
            _full_id.setdefault(mb.group(1), []).append((pt_id, pt_ts))
    _full_per_mst = {}
    for mst, sfx in _full_suffix.items():
        mm = _build_mst_axis_model(sfx, _full_id[mst], today_ts)
        if mm is not None:
            _full_per_mst[mst] = mm
    full_model = PerMstDateInterpolator(
        _full_per_mst, DateInterpolator([(pid, pts) for pid, pts, _, _ in ground_truth])
    )

    for i, (test_id, test_ts, test_date, test_gdt) in enumerate(ground_truth):
        # Build training sets without this point — both candidate axes per MST.
        global_train: list[tuple[int, float]] = []
        per_mst_suffix: dict[str, list[tuple[int, float]]] = {}
        per_mst_id: dict[str, list[tuple[int, float]]] = {}
        for j, (pt_id, pt_ts, _, pt_gdt) in enumerate(ground_truth):
            if j == i:
                continue
            global_train.append((pt_id, pt_ts))
            mb = _fmt_b_re.match(pt_gdt)
            if mb:
                per_mst_suffix.setdefault(mb.group(1), []).append((int(mb.group(2)), pt_ts))
                per_mst_id.setdefault(mb.group(1), []).append((pt_id, pt_ts))

        if len(global_train) < 2:
            continue

        # Select model and x-value for the test point
        tm = _fmt_b_re.match(test_gdt)
        mst_model = None
        if tm:
            test_parent = tm.group(1)
            test_suffix = int(tm.group(2))
            sfx = per_mst_suffix.get(test_parent, [])
            if len(sfx) >= 2:
                mst_model = _build_mst_axis_model(sfx, per_mst_id[test_parent], today_ts)

        if mst_model is not None:
            pred_ts = mst_model.predict(test_suffix, test_id)
            is_interp = not mst_model.is_extrapolated(test_suffix, test_id)
        else:
            model = DateInterpolator(global_train)
            pred_ts = model.interpolate(test_id)
            train_ids = [p[0] for p in global_train]
            is_interp = min(train_ids) <= test_id <= max(train_ids)

        # Confidence bucket = the label PRODUCTION assigns this store (full-data
        # model), so the stratified accuracy reflects what downstream actually sees.
        conf = full_model.confidence(test_id, gdt_code=test_gdt)

        if pred_ts is None:
            continue
        err = abs(pred_ts - test_ts) / 86400.0
        if is_interp:
            interp_errors.append(err)
        else:
            extrap_errors.append(err)
        conf_errors[conf].append(err)
        miss_list.append((err, test_id, test_date, _fmt(pred_ts), conf))

    all_errors = interp_errors + extrap_errors
    if not all_errors:
        return ''

    a = _stats(all_errors)
    i_s = _stats(interp_errors)
    e_s = _stats(extrap_errors)
    h_s = _stats(conf_errors['high'])
    m_s = _stats(conf_errors['medium'])
    l_s = _stats(conf_errors['low'])

    miss_list.sort(reverse=True)
    worst_rows = '\n'.join(
        f'| {id_} | {actual} | {pred} | {err:.0f} | {conf} |'
        for err, id_, actual, pred, conf in miss_list[:5]
    )
    # Sanity flag: a high/medium store among the worst misses would mean the
    # confidence field is NOT tracking error (the claim it must support).
    worst_conf = {conf for *_ , conf in miss_list[:5]}
    conf_ok = 'high' not in worst_conf and 'medium' not in worst_conf

    print(
        f'  [backtest] Date LOO: {n} pts, MAE={a["mae"]:.0f}d, '
        f'{a["w30"]:.0f}% ≤30d, {a["w90"]:.0f}% ≤90d  | '
        f'by-conf MAE high={("%.0f" % h_s["mae"]) if h_s else "-"} '
        f'med={("%.0f" % m_s["mae"]) if m_s else "-"} '
        f'low={("%.0f" % l_s["mae"]) if l_s else "-"} '
        f'| worst-5 all-low={conf_ok}'
    )

    return f"""
---

## Date Model Accuracy (LOO Cross-Validation)

Leave-one-out cross-validation using **{n}** masothue.com `ngay_hd` ground-truth dates.
For each anchor the model is rebuilt from the remaining {n - 1} points and the held-out
store's date is predicted. Errors are in calendar days.

| Segment | N | MAE (days) | Median | P90 | ≤ 30 days | ≤ 90 days |
|---|---|---|---|---|---|---|
{_row('Interpolated (in-range)', i_s)}
{_row('Extrapolated (out-of-range)', e_s)}
{_row('**All**', a)}

**Overall: {a["w30"]:.0f}% within ±30 days, {a["w90"]:.0f}% within ±90 days** (MAE = {a["mae"]:.0f} days).

### Accuracy by `Date_Confidence` bucket

This verifies the per-store `Date_Confidence` flag tracks error against the
*activation* calibration target. (`Date_Confidence` rates founding-usability — see
the "Activation↔Founding Gap" section below; for chronological brands the two
coincide, so a flag good here is also good there.)

| Confidence | N | MAE (days) | Median | P90 | ≤ 30 days | ≤ 90 days |
|---|---|---|---|---|---|---|
{_row('high', h_s)}
{_row('medium', m_s)}
{_row('low', l_s)}

(`exact` masothue-sourced dates are excluded — they are ground truth, not predictions.)

### Worst misses (top 5)

| DKKD Id | Actual (ngay\\_hd) | Predicted | Error (days) | Confidence |
|---|---|---|---|---|
{worst_rows}
"""


def _build_founding_benchmark_section(slug: str, brands_dir=None) -> str:
    """Quantify the activation↔founding gap of the date model's output.

    ``Establishment_Date`` is an **activation / operation-start estimate** (masothue
    ``ngay_hd``), which the model in §"Date Model Accuracy" is calibrated on and
    LOO-validated against.  This section measures how well that estimate also serves
    as the legal founding date by comparing the model's *inferred* value against
    hand-fetched DKKD ``EnterpriseInfo`` ``FOUNDING_DATE`` (*Ngày thành lập*) in
    ``enterprise_details.json``.

    Founding never enters calibration, so this is a genuine out-of-distribution
    test, not memorisation.  For chronologically-filed brands founding ≈ activation
    and the estimate is a good founding proxy (days–weeks); for mass-refile chains
    (PNJ) the two diverge by years — which is why every suffix-axis store is fenced
    to ``low`` (see ``PerMstDateInterpolator.confidence``).  Stratifying by
    confidence tier shows the flag correctly fences the divergent brands: ``high``/
    ``medium`` stay founding-usable, ``low`` is where the activation estimate must
    not be read as founding.

    Returns '' when no ``enterprise_details.json`` ground truth exists.
    """
    from datetime import datetime as _dt
    from dkkd.enrich import build_calibration_model, build_global_id_date_model, _DECOUPLED_SLUGS
    from dkkd import config as _cfg

    out = output_dir(slug, brands_dir)
    det_file = out / 'enterprise_details.json'
    if not det_file.exists():
        return ''
    details = json.loads(det_file.read_text(encoding='utf-8'))

    cp = checkpoint_json(slug, brands_dir)
    if not cp.exists():
        return ''
    pairs = json.loads(cp.read_text(encoding='utf-8'))
    records = [item[1] if isinstance(item, list) else item for item in pairs]
    id_to_gdt = {str(r['Id']): str(r.get('Enterprise_Gdt_Code') or '').strip()
                 for r in records if r.get('Id')}

    status_file = out / 'masothue_store_statuses.json'
    statuses = (json.loads(status_file.read_text(encoding='utf-8'))
                if status_file.exists() else {})

    # Build the SHIPPED production model (calibrated on masothue activation only).
    # Global cross-brand fallback EXCLUDES this brand's own founding dates so the
    # benchmark stays a genuine held-out test (the target's enterprise_details is
    # the ground truth — letting it seed the curve would be circular).
    global_fallback = build_global_id_date_model(
        brands_dir, exclude_slugs=_DECOUPLED_SLUGS | {slug})
    model = build_calibration_model(_cfg.load(slug, brands_dir), records,
                                    masothue_statuses=statuses or None,
                                    global_fallback=global_fallback)
    has_conf = hasattr(model, 'confidence')

    # Ground-truth founding points: (dkkd_id, founding_ts, founding_str, gdt)
    truth: list[tuple[int, float, str, str]] = []
    for sid, v in details.items():
        if not v.get('name'):
            continue
        try:
            fts = _dt.strptime(v.get('established', ''), '%d/%m/%Y').timestamp()
        except (ValueError, TypeError):
            continue
        try:
            dkkd_id = int(sid)
        except (TypeError, ValueError):
            continue
        gdt = id_to_gdt.get(str(sid)) or str(v.get('mst') or '').strip()
        truth.append((dkkd_id, fts, v['established'], gdt))

    if len(truth) < 3:
        return (
            '\n---\n\n## Date Model vs Real Founding Date (Ngày thành lập)\n\n'
            f'Insufficient hand-fetched ground truth: {len(truth)} point(s), '
            'need ≥ 3. Re-run `scratch/bh_fetch.py` to extend the sample.\n'
        )

    def _row(label, st):
        if not st:
            return f'| {label} | 0 | — | — | — | — | — |'
        return (f'| {label} | {st["n"]} | {st["mae"]:.0f} | {st["median"]:.0f} | '
                f'{st["max"]:.0f} | {st["w90"]:.0f}% | {st["w1y"]:.0f}% |')

    conf_errors: dict[str, list[float]] = {'high': [], 'medium': [], 'global': [], 'low': []}
    miss_list: list[tuple[float, int, str, str, str]] = []
    for dkkd_id, fts, fstr, gdt in truth:
        pred = model.interpolate(dkkd_id, gdt_code=gdt)
        if pred is None:
            continue
        conf = model.confidence(dkkd_id, gdt_code=gdt) if has_conf else 'low'
        err = abs(pred - fts) / 86400.0
        conf_errors.setdefault(conf, []).append(err)
        miss_list.append((err, dkkd_id, fstr, _fmt(pred), conf))

    all_errors = [e for v in conf_errors.values() for e in v]
    if not all_errors:
        return ''
    a = _stats(all_errors)
    h_s, m_s, g_s, l_s = (_stats(conf_errors['high']), _stats(conf_errors['medium']),
                          _stats(conf_errors['global']), _stats(conf_errors['low']))

    miss_list.sort(reverse=True)
    worst_rows = '\n'.join(
        f'| {id_} | {actual} | {pred} | {err:.0f} | {conf} |'
        for err, id_, actual, pred, conf in miss_list[:5]
    )
    # Integrity = no high/medium store is off by more than a year.  (The older
    # "worst-5 must be all-low" rule false-alarms on uniformly-accurate brands,
    # where a high store legitimately tops a list of small errors.  The real
    # claim this section defends is that high/medium dates are never *years*
    # wrong — the exact failure that suffix-axis demotion fixed for PNJ.)
    _YEAR = 365.0
    conf_ok = not any(
        c in ('high', 'medium') and err > _YEAR for err, *_, c in miss_list
    )

    print(
        f'  [backtest] Founding GT: {a["n"]} pts, MAE={a["mae"]:.0f}d, '
        f'{a["w1y"]:.0f}% ≤1yr | by-conf MAE '
        f'high={("%.0f" % h_s["mae"]) if h_s else "-"} '
        f'med={("%.0f" % m_s["mae"]) if m_s else "-"} '
        f'global={("%.0f" % g_s["mae"]) if g_s else "-"} '
        f'low={("%.0f" % l_s["mae"]) if l_s else "-"} | hi/med-within-1yr={conf_ok}'
    )

    return f"""
---

## Activation↔Founding Gap (Establishment_Date vs real Ngày thành lập)

`Establishment_Date` is an **activation / operation-start estimate** (masothue
*Ngày hoạt động*), not a direct founding read. This section quantifies how well it
also serves as the legal founding date (*Ngày thành lập*), using **{a["n"]}**
hand-fetched DKKD `EnterpriseInfo` `FOUNDING_DATE` ground-truth points. Founding
never enters calibration, so this is a genuine out-of-distribution check. The two
quantities **coincide to days–weeks for chronologically-filed brands** but **diverge
by years for mass-refile chains** (PNJ founded a 2004–06 branch block whose activation
climbs to 2013–2020) — which is exactly why every suffix-axis store is fenced to
`low`. Errors in calendar days.

### Founding usability by `Date_Confidence` bucket

Reads as: *can a date at this tier be trusted as a founding date?* `high`/`medium`
(Id axis, founding-validated) should hold days–weeks; `global` is the cross-brand
national-registry fallback (accurate as a *registration* date, but not founding-
validated for decoupled chains); `low` is the bucket where the activation estimate
must **not** be read as founding.

| Confidence | N | MAE (days) | Median | Max | ≤ 90 days | ≤ 1 year |
|---|---|---|---|---|---|---|
{_row('high', h_s)}
{_row('medium', m_s)}
{_row('global', g_s)}
{_row('low', l_s)}
{_row('**All**', a)}

Confidence is the model's *inferred* tier (scored on the interpolated prediction).
Note `exact` (masothue-sourced) shipped dates are exact **activation** dates: they
equal founding for chronological brands but, for decoupled brands, are an
activation-only value — read them as founding only outside the suffix-axis chains.

### Largest activation↔founding gaps (top 5)

| DKKD Id | Real Ngày thành lập | Inferred (activation est.) | Gap (days) | Confidence |
|---|---|---|---|---|
{worst_rows}

**Founding-usability integrity:** no `high`/`medium` store off by > 1 year = **{conf_ok}**
(a `high`/`medium` store *years* off founding would mean the trust flag fails to fence
the decoupled brands — the exact failure the suffix-axis `low` cap prevents).
"""


def _build_closure_backtest_section(slug: str, brands_dir=None) -> str:
    """Precision/recall of Operating_Status=='Closed' against ground truth.

    Reads output/closure_ground_truth.json (keyed by dkkd_id, {label, status_raw}).
    Compares against Operating_Status/Operating_Evidence already resolved into
    checkpoint.json by postprocess.run_pipeline. Returns '' when no ground
    truth file exists.
    """
    out = output_dir(slug, brands_dir)
    gt_file = out / 'closure_ground_truth.json'
    if not gt_file.exists():
        return ''
    ground_truth = json.loads(gt_file.read_text(encoding='utf-8'))

    cp = checkpoint_json(slug, brands_dir)
    if not cp.exists():
        return ''
    pairs = json.loads(cp.read_text(encoding='utf-8'))
    records = [item[1] if isinstance(item, list) else item for item in pairs]
    by_id = {str(r.get('Id')): r for r in records if r.get('Id') is not None}

    rows = []  # (dkkd_id, actual_label, predicted_status, evidence)
    for sid, v in ground_truth.items():
        label = v.get('label')
        record = by_id.get(str(sid))
        if not label or record is None:
            continue
        predicted = record.get('Operating_Status', 'Unverified')
        evidence = record.get('Operating_Evidence', '')
        rows.append((sid, label, predicted, evidence))

    if len(rows) < 3:
        return (
            '\n---\n\n## Closure Signal Accuracy (Structural vs Ground Truth)\n\n'
            f'Insufficient ground truth: {len(rows)} point(s), need ≥ 3. '
            'Extend `closure_ground_truth.json` via `scratch/bh_fetch.py` + '
            '`scratch/build_closure_ground_truth.py`.\n'
        )

    tp = sum(1 for _, actual, pred, _ in rows if pred == 'Closed' and actual == 'Closed')
    fp = sum(1 for _, actual, pred, _ in rows if pred == 'Closed' and actual != 'Closed')
    fn = sum(1 for _, actual, pred, _ in rows if pred != 'Closed' and actual == 'Closed')
    tn = sum(1 for _, actual, pred, _ in rows if pred != 'Closed' and actual != 'Closed')

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and (precision + recall) > 0
          else None)

    def _pct(x):
        return f'{x * 100:.1f}%' if x is not None else '—'

    by_evidence: dict[str, list[bool]] = {}
    for _, actual, pred, evidence in rows:
        if pred == 'Closed':
            by_evidence.setdefault(evidence, []).append(actual == 'Closed')
    evidence_rows = '\n'.join(
        f'| {ev} | {len(flags)} | {_pct(sum(flags) / len(flags))} |'
        for ev, flags in sorted(by_evidence.items())
    ) or '| (none) | 0 | — |'

    return f"""
---

## Closure Signal Accuracy (Structural vs Ground Truth)

Compares `Operating_Status == 'Closed'` (structural signals in `operating_status.py`)
against **{len(rows)}** CAPTCHA-fetched / externally-labelled ground-truth points in
`closure_ground_truth.json`. Positive class = `Closed`.

### Confusion matrix

| | Actual Closed | Actual Operating |
|---|---|---|
| **Predicted Closed** | {tp} (TP) | {fp} (FP) |
| **Predicted not-Closed** | {fn} (FN) | {tn} (TN) |

### Overall

| Metric | Value |
|---|---|
| Precision | {_pct(precision)} |
| Recall | {_pct(recall)} |
| F1 | {_pct(f1)} |

### Precision by `Operating_Evidence` rung (predicted-Closed rows only)

| Evidence | n | Precision |
|---|---|---|
{evidence_rows}
"""


def _build_license_trends_section(slug: str, brands_dir=None) -> str:
    """One-license-many-stores distribution + per-MST growth curves.

    Groups checkpoint.json records by resolved MST (dkkd.operating_status._extract_mst)
    and reports the stores-per-MST distribution plus, for each of the top MSTs with 2+
    stores, its per-year openings curve (Establishment_Year as already computed — no
    date-model recalibration here). Returns '' when the checkpoint is absent or no
    record has a resolvable MST. No config flag: this is a factual count, not a
    classification with false-positive risk.
    """
    from dkkd.license_trends import mst_distribution, mst_growth_curve

    cp = checkpoint_json(slug, brands_dir)
    if not cp.exists():
        return ''
    pairs = json.loads(cp.read_text(encoding='utf-8'))
    records = [item[1] if isinstance(item, list) else item for item in pairs]

    dist = mst_distribution(records, top_n=10)
    if dist['total_stores'] == 0:
        return ''

    top_rows = '\n'.join(f'| {mst} | {count} |' for mst, count in dist['top_msts'])

    curve_sections = []
    for mst, count in dist['top_msts']:
        if count < 2:
            continue
        curve = mst_growth_curve(records, mst)
        if not curve:
            continue
        curve_rows = '\n'.join(f'| {year} | {n} |' for year, n in sorted(curve.items()))
        curve_sections.append(
            f"\n#### MST `{mst}` ({count} stores) — openings per year\n\n"
            f"| Year | Openings |\n|---|---|\n{curve_rows}\n"
        )

    return f"""
---

## License Trends (Stores per MST)

Groups all **{dist['total_stores']}** stores with a resolvable MST
(`dkkd.operating_status._extract_mst`) by license. **{dist['single_store_msts']}** of
**{dist['total_msts']}** MSTs hold exactly 1 store; **{dist['multi_store_msts']}** hold 2+.
"One license, many stores" is a structural fact here, not a dedup issue — see
`docs/archive/superpowers/specs/2026-07-01-license-trends-design.md`. Date-model accuracy caveats are
covered in the sections above; the growth curves below use `Establishment_Year` as-is.

### Top {len(dist['top_msts'])} of {dist['total_msts']} MSTs by store count

| MST | Store count |
|---|---|
{top_rows}
{''.join(curve_sections)}
"""


def _build_registration_curve_section(slug: str, brands_dir=None) -> str:
    """Per-year DKKD registration count + median Id-gap diagnostic.

    DKKD Id is a nationwide-sequential counter, so a small median gap between
    consecutive Ids filed in the same Establishment_Year means those records
    were filed close together in real time (a mass filing/re-registration
    event), not organic day-by-day store openings spread across the year.
    Returns '' if the core-operating CSV or the required columns are absent.
    """
    import pandas as pd

    out = output_dir(slug, brands_dir)
    csv_path = out / f'{slug}.csv'
    if not csv_path.exists():
        return ''

    try:
        df = pd.read_csv(csv_path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return ''

    if 'Establishment_Year' not in df.columns or 'Id' not in df.columns:
        return ''

    df = df.dropna(subset=['Establishment_Year', 'Id'])
    if df.empty:
        return ''

    rows = []
    for year, grp in df.groupby('Establishment_Year'):
        ids = sorted(int(x) for x in grp['Id'].tolist())
        n = len(ids)
        if n >= 2:
            gaps = sorted(b - a for a, b in zip(ids, ids[1:]))
            median_gap = gaps[len(gaps) // 2]
            gap_str = f"{median_gap:,}"
        else:
            gap_str = "—"
        rows.append((str(int(year)), n, gap_str))
    rows.sort(key=lambda r: r[0])

    table_rows = "\n".join(f"| {y} | {n} | {g} |" for y, n, g in rows)
    total = sum(n for _, n, _ in rows)

    return f"""

## Registration Curve (approximate historical opening shape)

`Establishment_Date` is a per-record activation/registration estimate, not a
verified opening date. This table shows the count of DKKD registrations per
`Establishment_Year`, plus the **median DKKD Id gap** between consecutive
registrations filed within that year. DKKD `Id` is a nationwide-sequential
counter, so a small median gap signals a **mass filing/re-registration event**
compressed into a short real-world window — not organic day-by-day store
openings spread across the year. Read a low-median-gap spike as a filing
artifact, not literal growth.

| Establishment_Year | Registrations | Median Id Gap |
|---|---|---|
{table_rows}
| **Total** | **{total}** | |
"""


def run_greenfield_checks(slug: str, brand_config, brands_dir=None) -> Path:
    """Run structural quality invariants for a brand with no reference benchmark.

    Reads state.json and checkpoint.json — no live API. Writes a markdown
    report and returns its path.
    """
    out = output_dir(slug, brands_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load state.json
    sp = state_json(slug, brands_dir)
    state_data = json.loads(sp.read_text(encoding='utf-8')) if sp.exists() else {}
    convergence = state_data.get('convergence', {})
    phase_history = state_data.get('phase_history', [])

    # Load checkpoint.json
    cp = checkpoint_json(slug, brands_dir)
    pairs = json.loads(cp.read_text(encoding='utf-8')) if cp.exists() else []
    records = [item[1] if isinstance(item, list) else item for item in pairs]
    ids = [r.get('Id') for r in records if r.get('Id')]

    compiled = brand_config.compiled_regex

    # --- Run invariants ---
    results = []

    # 1. Convergence reached
    conv_ok = bool(convergence.get('converged'))
    results.append((
        'Convergence reached',
        conv_ok,
        convergence.get('rule', 'not converged') if conv_ok
        else f"converged=False — {convergence.get('rule', 'no state found')}",
    ))

    # 2. Dedup integrity
    unique_ids = len(set(ids))
    dedup_ok = len(ids) == unique_ids
    results.append((
        'Dedup integrity',
        dedup_ok,
        f"{len(ids)} records, all Ids unique" if dedup_ok
        else f"{len(ids)} records but only {unique_ids} unique Ids",
    ))

    # 3. Brand filter compliance
    mismatches = [
        r.get('Id', '?') for r in records
        if not (compiled.search(r.get('Name', '') or '')
                or compiled.search(r.get('Name_F', '') or ''))
    ]
    filter_ok = len(mismatches) == 0
    results.append((
        'Brand filter compliance',
        filter_ok,
        f"{len(records)}/{len(records)} match brand_regex" if filter_ok
        else f"{len(mismatches)} record(s) do not match brand_regex: {mismatches[:5]}",
    ))

    # 4. GDT branch coverage
    branch_count = sum(
        1 for r in records
        if _BRANCH_RE.match(r.get('Enterprise_Gdt_Code', '') or '')
    )
    gdt_ok = branch_count >= 1
    results.append((
        'GDT branch coverage',
        gdt_ok,
        f"{branch_count} branch-format codes found" if gdt_ok
        else "0 branch-format GDT codes — parent MST extraction may have failed",
    ))

    # 5. Playbook completeness
    strategies_run = {p.get('strategy') for p in phase_history}
    missing = _PLAYBOOK_NAMES - strategies_run
    playbook_ok = len(missing) == 0
    results.append((
        'Playbook completeness',
        playbook_ok,
        f"All {len(_PLAYBOOK_NAMES)} strategies in phase_history" if playbook_ok
        else f"Missing strategies: {sorted(missing)}",
    ))

    # --- Build report ---
    all_passed = all(ok for _, ok, _ in results)
    rows = '\n'.join(
        f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |"
        for name, ok, detail in results
    )
    status = 'All checks passed' if all_passed else 'One or more checks FAILED'
    report_content = f"""# {slug.replace('-', ' ').title()} — Greenfield Quality Check

{status}

| Invariant | Result | Detail |
|---|---|---|
{rows}
"""
    date_section = _build_date_backtest_section(slug, brands_dir)
    founding_section = _build_founding_benchmark_section(slug, brands_dir)
    registration_curve_section = _build_registration_curve_section(slug, brands_dir)
    closure_section = _build_closure_backtest_section(slug, brands_dir)
    license_trends_section = _build_license_trends_section(slug, brands_dir)
    report_path = out / f"{slug}_backtest_report.md"
    report_path.write_text(
        report_content + date_section + founding_section + registration_curve_section
        + closure_section + license_trends_section,
        encoding='utf-8')
    print(f"Greenfield report written to {report_path}")
    return report_path


def run_backtest(slug: str, *, brands_dir=None) -> Path | None:
    """Run the back-test reconciliation for a brand.

    Uses reference mode when backtest: config exists; greenfield invariant
    mode otherwise. Returns the path to the written report.
    """
    import pandas as pd

    brand_config = cfg.load(slug, brands_dir)
    backtest_cfg = brand_config.backtest

    if not backtest_cfg or 'expected_total' not in backtest_cfg:
        return run_greenfield_checks(slug, brand_config, brands_dir)

    out_dir = output_dir(slug, brands_dir)
    csv_path = out_dir / f"{slug}.csv"

    df = pd.read_csv(csv_path)

    # Filter commercially active stores
    df_active = df[df['Core_Operating_Store'] == 'Yes'].copy()

    # Parse province from address
    df_active['Province_Clean'] = df_active['Ho_Address'].apply(_parse_province)

    # Map to region
    df_active['Region'] = df_active['Province_Clean'].apply(_map_region)

    # Regional counts
    regional_counts = df_active['Region'].value_counts()
    north_cnt = regional_counts.get('North', 0)
    central_cnt = regional_counts.get('Central', 0)
    south_cnt = regional_counts.get('South', 0)
    total_active_cnt = len(df_active)

    # Format counts (using Store_Type_MSN)
    format_counts = df_active['Store_Type_MSN'].value_counts()

    # Count corporate: filter on Store_Brand_Format ending in ' (Corporate/Logistics)'
    corp_cnt = len(df[df['Store_Brand_Format'].str.endswith(' (Corporate/Logistics)', na=False)])

    # Count unverified: brands opted into the 3-state operating-status resolver have this file;
    # brands on the legacy path don't, and should show 0 (Unverified is an opt-in-only concept).
    unverified_path = out_dir / f"{slug}_unverified.csv"
    unverified_cnt = len(pd.read_csv(unverified_path)) if unverified_path.exists() else 0

    # Read expected figures from config
    report_label = backtest_cfg.get('report_label', 'Reference Report')
    expected_total = backtest_cfg['expected_total']
    expected_by_format = backtest_cfg.get('expected_by_format', {})
    expected_by_region = backtest_cfg.get('expected_by_region', {})

    # Calculate variance and percentages
    variance = total_active_cnt - expected_total
    variance_pct = (variance / expected_total) * 100 if expected_total else 0

    north_pct = (north_cnt / total_active_cnt) * 100 if total_active_cnt else 0
    central_pct = (central_cnt / total_active_cnt) * 100 if total_active_cnt else 0
    south_pct = (south_cnt / total_active_cnt) * 100 if total_active_cnt else 0

    exp_north = expected_by_region.get('North', 0)
    exp_central = expected_by_region.get('Central', 0)
    exp_south = expected_by_region.get('South', 0)
    exp_north_pct = (exp_north / expected_total) * 100 if expected_total else 0
    exp_central_pct = (exp_central / expected_total) * 100 if expected_total else 0
    exp_south_pct = (exp_south / expected_total) * 100 if expected_total else 0

    # Build format rows
    format_rows = []
    for fmt_label, exp_cnt in expected_by_format.items():
        scraped_cnt = int(format_counts.get(fmt_label, 0))
        fmt_variance = scraped_cnt - exp_cnt
        variance_str = f"+{fmt_variance}" if fmt_variance >= 0 else str(fmt_variance)
        format_rows.append(
            f"| **{fmt_label}** | {exp_cnt:,} | {scraped_cnt:,} | **{variance_str}** |"
        )

    # Corporate row
    format_rows.append(
        f"| **Non-Operating / Corporate / Closed** | — | {corp_cnt:,} | (not in report) |"
    )

    # Total row
    total_variance_str = f"+{variance}" if variance >= 0 else str(variance)
    format_rows.append(
        f"| **Total** | **{expected_total:,}** | **{total_active_cnt:,}** | **{total_variance_str}** |"
    )

    format_table = "\n".join(format_rows)

    # Build region rows
    region_rows = [
        f"| **Miền Bắc (North)** | {exp_north:,} | {north_cnt:,} | {exp_north_pct:.1f}% vs. **{north_pct:.1f}%** |",
        f"| **Miền Trung (Central)** | {exp_central:,} | {central_cnt:,} | {exp_central_pct:.1f}% vs. **{central_pct:.1f}%** |",
        f"| **Miền Nam (South)** | {exp_south:,} | {south_cnt:,} | {exp_south_pct:.1f}% vs. **{south_pct:.1f}%** |",
        f"| **Total** | **{expected_total:,}** | **{total_active_cnt:,}** | **100% vs. 100%** |",
    ]
    region_table = "\n".join(region_rows)

    # Calculate parity pct for headline
    parity_pct = 100 - abs(variance_pct)
    variance_sign = "+" if variance >= 0 else ""

    report_content = f"""# {slug.replace('-', ' ').title()} – {report_label} Reconciliation

This report reconciles the scraped DKKD active {slug} stores with the official {report_label} figures.

---

## 1. Network Size Reconciliation

Our scraped DKKD registry active network shows **{parity_pct:.2f}% parity** with the official {report_label}:

*   **Official {report_label}:** **{expected_total:,} active stores**
*   **Scraped DKKD Registry (Core Operating):** **{total_active_cnt:,} active locations**
*   **Variance:** **{variance_sign}{variance} locations ({variance_sign}{variance_pct:.2f}%)** in the DKKD registry. This represents:
    1.  **Registered Offices/Support Sites:** {corp_cnt:,} corporate and logistical sites.
    2.  **Pre-opening Locations:** Store licenses registered at DKKD that have not yet opened for business.
{f"    3.  **Unverified Locations:** {unverified_cnt:,} DKKD registrations with no positive operating-status evidence (not confirmed open, not confirmed closed — see Operating_Evidence in the core-operating CSV)." if unverified_cnt > 0 else ""}

---

## 2. Store Format Breakdown

| Format | {report_label} Store Count | Scraped DKKD Active Count | Variance |
| :--- | :---: | :---: | :---: |
{format_table}

---

## 3. Geographic Distribution

| Region | {report_label} Store Count | Scraped DKKD Active Count | Regional Weight ({report_label} vs. DKKD) |
| :--- | :---: | :---: | :---: |
{region_table}

### Insights:
*   **North Dominance:** More than **{north_pct:.1f}%** of the network is situated in the North.
*   **Central Region:** Accounts for **{central_pct:.1f}%** of active stores.
*   **South Region:** Accounts for **{south_pct:.1f}%** of active stores.
"""

    date_section = _build_date_backtest_section(slug, brands_dir)
    founding_section = _build_founding_benchmark_section(slug, brands_dir)
    registration_curve_section = _build_registration_curve_section(slug, brands_dir)
    closure_section = _build_closure_backtest_section(slug, brands_dir)
    license_trends_section = _build_license_trends_section(slug, brands_dir)
    report_path = out_dir / f"{slug}_backtest_report.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content + date_section + founding_section + registration_curve_section
                 + closure_section + license_trends_section)

    print(f"Backtest report written to {report_path}")
    print(f"Total active (Core_Operating_Store=Yes): {total_active_cnt}")
    print(f"  North: {north_cnt} ({north_pct:.1f}%)  Central: {central_cnt} ({central_pct:.1f}%)  South: {south_cnt} ({south_pct:.1f}%)")
    print(f"  Variance vs {report_label}: {variance_sign}{variance} ({variance_sign}{variance_pct:.2f}%)")

    return report_path
