# Date Inference (`Establishment_Date` / `Date_Confidence`)

**Status:** active
**Last updated:** 2026-06-30

**TL;DR:** `Establishment_Date` is an **activation / operation-start estimate** (masothue
*Ngày hoạt động*), not a direct legal-founding read. `Date_Confidence` rates how
trustworthy that value is **as a founding date**: `high`/`medium` (Id-axis) ≈ founding to
days–weeks; `low` (suffix-axis / sparse / Format A) must **not** be read as founding;
`exact` = exact activation date. ~2010 is the registry's event horizon — pre-2010 founding
is unrecoverable from the model's inputs.

## Current understanding

- **Two clocks, not one.** masothue `ngay_hd` = *activation* (operation start); DKKD
  `EnterpriseInfo.FOUNDING_DATE` (*Ngày thành lập*) = *legal founding*. The model
  calibrates on activation but the column is read as founding. They **coincide for
  chronologically-filed brands** and **diverge by years for mass-re-registered ones**
  `[empirical]`.
- **`Id` is a data-entry clock, not a founding clock.** The global DKKD `Id` is assigned
  when a record enters the modern system. Id ≈ 400,000 maps to ~2017, yet PNJ branches
  with `FOUNDING_DATE` 2004–06 carry that Id ⇒ they were *entered* ~2017, ~11 yr after
  founding `[empirical]` (see `scratch/axis_gate_test.py` Gate 2 output).
- **~2010–2011 unified-registration epoch = founding floor.** Vietnam unified business
  registration + tax code ~2010–2011; legacy entities were back-loaded from then on, so
  their `Id`/`ngay_hd` are entry dates `[documented]`. Encoded as the `2010-01-01`
  calibration floor; records do floor to it `[empirical]`.
- **Per-MST x-axis selection.** For Format B (`MST-NNN`), each parent MST picks the axis
  (global `Id` vs branch `suffix`) with lower leave-one-out MAE, tie-breaking to the
  bounded suffix. Id wins for chronologically-filed brands; suffix wins only when a brand
  mass-refiles (clustered Ids, dates ramping by suffix) `[empirical]`.
- **The F&B-vs-gold gap is per-company structure, NOT sector.** There is no sector field
  in the data. doji (gold) selects the Id axis and is accurate (`high`, MAE 68d); gs25
  (F&B) selects suffix. The decoupled brands (PNJ, SJC) are old houses that equitized in
  the mid-2000s, creating a 2004–06 founding cohort whose activation trickled to 2013–20
  `[empirical]` / `[inferred]`.

### Per-brand founding accuracy (live model, 173 ground-truth points, 2026-06-30)

| brand | n | MAE | median | ≤90d | ≤1yr | tiers |
|---|--:|--:|--:|--:|--:|---|
| circle-k | 46 | 23d | 6d | 93% | 100% | low:46 |
| coop-food | 35 | 25d | 15d | 97% | 100% | high:18 · low:17 |
| winmart | 26 | 27d | 3d | 92% | 100% | high:12 · low:14 |
| doji | 14 | 68d | 78d | 57% | 100% | high:3 · low:11 |
| sjc | 16 | 320d | 78d | 56% | 75% | low:16 |
| pnj | 36 | 1384d | 142d | 47% | 53% | low:36 |

## Current solution

- **`PerMstDateInterpolator`** (`dkkd/enrich.py`) dispatches Format B → per-MST axis model,
  else → global Id fallback. Built by `build_calibration_model` from masothue `ngay_hd`.
- **`GlobalDateInterpolator` + `build_global_id_date_model`** (the 2026-07-01 P6 fix): when a brand
  has no per-brand calibration, `build_calibration_model(..., global_fallback=…)` uses a single
  cross-brand `Id→date` curve fit on every brand's `enterprise_details.json` founding dates. The DKKD
  `Id` is a national registry clock, so this predicts any chronological brand's registration date to
  days. Two anchor filters keep the curve clean: (a) `_DECOUPLED_SLUGS`={pnj,sjc,precita} brands are
  skipped; (b) any anchor founded before `_REGISTRY_FLOOR_DATE` (2010-01-01) is dropped — a legacy
  back-loaded entity (e.g. a 1993-founded HQ at a ~2010 Id) has its founding decoupled from the Id
  clock and one such point poisons the curve's low-Id segment (this is what made btmc's 1993 HQ wreck
  circle-k-band predictions before the filter). Dates from the curve carry a distinct **`global`**
  confidence tier (national-registry-accurate, *not* founding-validated for decoupled brands — same
  epistemic caveat as `low`, but empirically days-accurate **within the validated 2011–2019 Id band**);
  out-of-anchor-range predictions fall back to `low`. postprocess passes the full curve; `dkkd backtest`
  passes it with the **target brand excluded** so the founding benchmark stays held-out.
  **Validation scope (leave-one-brand-out, 2026-07-01):** each of the 8 brands with founding ground
  truth was predicted by a curve built from the *other* 7 (target excluded — genuinely held-out, no
  data leakage). Post-2010 points fit to **1–5d MAE, 100% ≤1yr** for 7/8 brands (pnj 26d, 96%), across
  convenience/supermarket/gold/ICT and the full 2010–2026 Id band. **Caveat — this number is flattered
  by dense interleaving, not 8 independent validations:** all brands share one national Id axis, so a
  held-out point sits a median ~18k Ids (~13 days) from another brand's anchor — the curve is pinned by
  temporally-adjacent neighbors, so LOBO mostly confirms *the national Id sequence is dense + monotonic*
  (the mechanism). The honest held-out number comes from deleting a whole 1.3M-Id donor block and
  predicting FPT points by spanning the gap: **MAE 71d, max 129d** (still ≤1yr). So expect **days–weeks
  where the Id band is densely covered, up to ~a quarter where sparse**; the 2d headline is best-case.
  Even the decoupled chains (pnj, sjc) fit on their *post-2010* points — decoupling is purely the
  pre-2010 cohort, removed by the floor filter. The ~289 uncalibrated brands have **no ground truth**
  (mechanism, not measurement); a brand that mass-refiles with *post-2010* clustered Ids would still
  earn a false `global` (P2, untested). Tools: `scratch/lobo_validation.py`, `scratch/check_density.py`.

### Global-curve leave-one-brand-out accuracy (held-out, post-2010 points, 2026-07-01)

| brand | decoupled | n | MAE | median | ≤1yr | pre-2010 dropped |
|---|---|--:|--:|--:|--:|--:|
| bao-tin-minh-chau | – | 13 | 1d | 1d | 100% | 1 |
| circle-k | – | 44 | 2d | 1d | 100% | 2 |
| coop-food | – | 35 | 2d | 1d | 100% | 0 |
| doji | – | 14 | 3d | 1d | 100% | 0 |
| fpt-shop | – | 40 | 2d | 1d | 100% | 0 |
| sjc | ✓ | 14 | 1d | 1d | 100% | 2 |
| winmart | – | 26 | 5d | 2d | 100% | 0 |
| pnj | ✓ | 25 | 26d | 2d | 96% | 11 |

Tool: `scratch/lobo_validation.py`.
- **Axis model** (`_build_mst_axis_model`): per-MST LOO axis selection, clamp to
  `[2000-01-01, today]`.
- **Confidence cap (the 2026-06-30 fix):** `PerMstDateInterpolator.confidence` caps any
  **suffix-axis** MST at `low` — suffix selection is the in-data decoupling signature, and
  founding accuracy there is unvalidated/always-wrong. `high` (Id-axis, n≥8, fit_mae≤90d)
  and `medium` (Id-axis, n≥5, fit_mae≤365d) require the founding-validated Id axis.
- **Validation in the report:** `dkkd backtest` emits an **"Activation↔Founding Gap"**
  section (`_build_founding_benchmark_section`) scoring the shipped model vs
  `enterprise_details.json`, stratified by tier, with a "no high/medium store off by
  > 1 year" integrity check.
- **Guarantees:** at quarterly resolution, chronological brands are essentially correct;
  every multi-year error is flagged `low`; no `high`/`medium` store is >1yr off founding.
- **Does NOT:** recover pre-~2010 founding; distinguish a coupled from a decoupled store
  inside a suffix-axis brand; let a consumer programmatically exclude activation-as-
  founding rows in the `exact` tier (see P1).

## Open Problems

| id | problem | status | impact |
|---|---|---|---|
| P1 | `exact` tier ships activation dates; for decoupled brands these are years off founding, and there is no `Date_Basis` column to exclude them (78 PNJ rows on the suffix-axis MST). A `Date_Confidence IN ('exact','high')` filter for "founding" pulls them. | open | consumers reading `exact` as founding |
| P2 | An Id-axis-decoupled brand (mass-refile but Ids chronological with activation) would earn a false `high`. The suffix-axis cap is a proxy; this case is untested — no validated brand of this type exists or rules it out. | open(untested) | silent wrong `high` on a new brand |
| P3 | Pre-~2010 founding is unrecoverable from `Id`/`ngay_hd` (system floor). | unrecoverable | historical cohorts of legacy brands |
| P4 | Non-PNJ brand CSVs are stale vs the current model. Only PNJ and bach-hoa-xanh (2026-07-01, switched to the global curve via `date_calibration_force_global`) have been re-synced; other manually-calibrated brands likely have the same unconditional-`low` issue and haven't been audited. | open (partially fixed for bach-hoa-xanh) | shipped labels lag the model until a `postprocess` refresh |
| P5 | Sparse (<5 anchors) / Format-A stores are always `low` (unvalidated). | wontfix | by design — safe, but no confident date there |
| P6 | **No-calibration brands degenerated to a 2-point linear fallback.** When `masothue_store_statuses.json` is absent and config has no `masothue_parent_url`/`date_calibration_points`, `build_calibration_model` fell to a straight chord `(min_Id, 2010-01-01)→(max_Id, today)` with *fabricated* endpoints. The national `Id→date` curve is **concave** (registry rate accelerates), so the chord predicted interior Ids ~1–3 yr **too early** (FPT: 0% year-acc, MAE 897d). **290/307 brands (94.5%)** were on this fallback. **FIXED 2026-07-01** by the `global` cross-brand `Id→date` curve (see Current solution); FPT held-out dropped to **MAE 2d, 100% ≤1yr**. Residual: the global curve gives a *registration*-date, still not founding for decoupled chains (P1/P3 unchanged); a store extrapolated beyond all anchors stays `low`. | **fixed** | was: every uncalibrated brand's dates skewed early |

## Ruled out / dead ends

- **Changing axis selection to recover PNJ founding** — Gate 2: the Id axis is no better
  than suffix (MAE 2672 vs 2572d; both predict the ~2017 activation era). Founding is not
  in the model's inputs. (`scratch/axis_gate_test.py`)
- **Relabeling the column to "founding"** — chose activation-estimate semantics (user
  decision 2026-06-30); the model cannot deliver founding for decoupled brands, so claiming
  "founding" would over-promise.
- **Fingerprint axis** — ruled out in a prior spike (commit `a7cf21f`).

## Progression Log

- **2026-07-01 (Bach Hoa Xanh switched to the global curve — new `date_calibration_force_global` flag):**
  Root-caused why BHX always shipped `Date_Confidence='low'` despite backtesting well: its
  config used manual `date_calibration_points` (priority 1, highest), and plain
  `DateInterpolator` has no `.confidence()` method at all — `apply_date_interpolation`
  (enrich.py:594) falls back to a hardcoded `'low'` whenever `hasattr(model, 'confidence')`
  is `False`. The `low` was never a computed judgment; it was "this code path can't grade
  itself." Added `date_calibration_force_global: true` (TDD, `build_calibration_model`
  priority 0 — checked before manual/masothue, no-op if no `global_fallback` supplied) and
  set it on BHX, removing the 8 manual points. Result: BHX now builds from the 265-anchor
  national curve, ships **3,139 `global` / 34 `exact` / 12 `low`** (was 3,177 `low` / 8
  `exact`), and the held-out backtest against the same 26 CAPTCHA founding dates (BHX's own
  anchors excluded from the curve, per existing `dkkd backtest` convention) dropped from
  **MAE 45d → MAE 3d, 100% ≤1yr**, correctly labeled `global` throughout. This is now the
  reference case for "manual points that predate the global-curve fix (P6) should probably
  be replaced" — worth auditing other manually-calibrated brands the same way. Tools:
  `tests/test_enrich_date_interpolation.py::TestBuildCalibrationModelGlobalFallback` (3 new
  cases), `brands/F&B/mini_supermarket/bach-hoa-xanh/config.yaml`.
- **2026-07-01 (Bach Hoa Xanh full-timeline backtest — browser-harness/CDP fetch, 26 pts):**
  Rebuilt BHX's model (`dkkd postprocess --brand bach-hoa-xanh`; unchanged — 8 manual
  `date_calibration_points`, a plain `DateInterpolator`, always `low` confidence since no
  per-MST axis model applies), then CAPTCHA-fetched **26 fresh founding-date ground-truth
  points stratified 2-per-year across all 14 populated `Establishment_Year` buckets
  (2012–2026)** via `browser-harness` (Chrome+CDP) rather than the usual Scrapling/Camoufox
  path — confirmed the 🐴 anti-bot flag was present throughout (expected; user solved an
  image challenge per store). Result: **26/26 year-match, MAE 45d, median 18d, max 133d,
  100% ≤1yr, 77% ≤90d** — the manual 8-point calibration (spanning 2010→2026) holds up
  as accurate everywhere tested, including the previously-unvalidated 2019–2024 gap
  between calibration anchors. All predictions are `low` confidence by construction
  (plain `DateInterpolator`, not `PerMstDateInterpolator`) — worth noting the confidence
  label under-claims accuracy here, since `low` is doing much better than its own
  definition promises for this brand. Operational note: `bh_fetch.py` run via
  `browser-harness < script.py` must set `PYTHONUNBUFFERED=1` (or avoid piping through
  `tail`) — otherwise progress prints are fully buffered and look hung. Tools:
  `scratch/bhx_select_targets.py` (stratified sampler), `scratch/bh_fetch.py` (existing
  browser-harness fetch loop, reused as-is with `IDS_FILE=date_backtest_ids.json`). Data:
  `brands/F&B/mini_supermarket/bach-hoa-xanh/output/enterprise_details.json` (26 pts),
  `scratch/bhx_targets.json`.
- **2026-07-01 (cross-brand held-out — 10 brands, the strongest generalization test):** Fetched 1
  fresh store from each of **10 brands the curve has zero ground truth from** (7-eleven, b-s-mart,
  bach-hoa-xanh, cheers, family-mart, gs25, mini-stop, jemmia, mi-hong, phu-quy — convenience/grocery/
  gold, Id 298k–12.4M), each excluded from the curve. **9/10 in-range: MAE 4d, 100% ≤1yr, 9/9
  year-match** — confirms the national-Id-clock generalizes to arbitrary unseen brands, not just FPT.
  The 10th (mi-hong, founded **1994** at Id 298k — below the post-floor anchor range) is the P3 dead
  zone: the curve predicted the 2010 registration era (5633d off founding) but **correctly flagged it
  `low`, not `global`** (extrapolated) — no false confidence on a pre-registry legacy date. Tools:
  `scratch/select_10_brands.py`, `scratch/bh_fetch_cross_brand.py`, `scratch/backtest_cross_brand.py`.
- **2026-07-01 (fresh 10-store held-out test — addresses the density critique):** Fetched **10 NEW
  random FPT stores** (CAPTCHA, never in any prior sample), 2015–2024, and predicted them with the
  FPT-excluded global curve: **MAE 3d, median 2d, 10/10 year-match, 100% ≤90d**. Unlike the original 40
  (median nearest-donor gap ~18k Ids ≈ 13d, i.e. neighbour-pinned), these had **median gap ~97k Ids**,
  with several at 100–240k gaps (e.g. Id 9110218: nearest anchor 239k away → still 2d). So days-accuracy
  holds even where the curve must span months between anchors — graceful degradation: ~18k gap→~2d,
  ~100–240k gap→2–11d, ~1.3M forced gap→71d. Genuinely independent (fresh stores, no leakage). Tool:
  `scratch/backtest_10_new.py` (+ `scratch/select_10_new.py`). FPT ground truth now 50 stores.
- **2026-07-01 (global curve validated n=8, then stress-tested for circularity):** Leave-one-brand-out
  across all 8 ground-truth brands (each held out, predicted by the other 7 — confirmed *not* circular:
  no point seeds its own prediction). Post-2010: **1–5d MAE, 100% ≤1yr for 7/8** (pnj 26d/96%) across 4
  sectors and the full 2010–2026 band. **But density check showed this is flattered:** all brands share
  one Id axis, held-out points sit ~13 days (median) from a neighbouring brand's anchor, so LOBO mostly
  proves the national sequence is dense+monotonic, not 8 independent successes. **Honest held-out
  number** (delete a 1.3M-Id donor block, predict FPT across the gap): **MAE 71d, max 129d**. Revised
  expectation: days–weeks where Id-coverage is dense, ~a quarter where sparse, ≤1yr throughout (barring
  post-2010 mass-refile, P2). Decoupling is purely the pre-2010 cohort (pnj: 11 pre-2010 points the
  curve correctly refuses), removed by the floor filter. Tools: `scratch/lobo_validation.py`,
  `scratch/check_density.py`.
- **2026-07-01 (P6 FIXED — shipped):** Implemented the global cross-brand fallback (TDD; full suite
  329 pass). Added `GlobalDateInterpolator` (own `global` confidence tier) and
  `build_global_id_date_model(brands_dir, exclude_slugs)`; threaded `global_fallback` through
  `build_calibration_model`; wired postprocess (full curve) and `dkkd backtest` (target-excluded,
  held-out). End-to-end: FPT postprocess builds from 172 anchors → CSV is **708 `global` / 40 `exact`
  / 1 `low`** (was 748 `low` @ ~2.5yr bias); held-out FPT backtest reports **MAE 2d, 100% ≤90d/≤1yr**
  (validated on the 2011–2019 Id band only — n=1 brand; rest rests on the national-clock mechanism).
  Two bugs found while hardening: (1) `enrich.py` never imported `json`, so a bare `except Exception`
  in the new scanner masked a `NameError` (narrowed to `(OSError, ValueError)` + added the import);
  (2) a single **pre-registry anchor poisons the curve** — bao-tin-minh-chau's 1993-founded HQ at
  Id 495372 (chronological for its other 13 points) dragged circle-k-band predictions to ~1800d.
  Fixed by the `_REGISTRY_FLOOR_DATE` (2010-01-01) anchor filter rather than a brand blocklist, so
  btmc stays a useful donor. This is why donor quality (not just brand identity) must be checked when
  the anchor pool changes.
- **2026-07-01 (improvement validated):** Tested whether the per-brand 2-pt fallback (P6) can be
  replaced by a **global cross-brand `Id→date` curve**. Built a curve from 121 real founding anchors
  of *donor* brands (circle-k, coop-food, winmart, doji) and predicted **FPT Shop's 40 founding dates
  with FPT contributing nothing** (fully held-out, cross-brand): **MAE 2d, median 1d, 40/40
  year-match, 100% ≤90d** — vs the fabricated chord's 897d / 0/40. Proves the DKKD `Id` is a
  **national registry clock**: Id alone fixes the registration date to days, brand-independently, for
  chronologically-filed brands. The interpolation *method* was never at fault; the defect was feeding
  it a fabricated per-brand line instead of the real national curve, whose anchors already exist in
  the repo (`enterprise_details.json` across brands). Tool: `scratch/test_global_curve.py`. Caveat:
  the global curve predicts *entry/registration* date — for decoupled mass-refile brands (PNJ/SJC) it
  still won't recover pre-entry founding (P1/P3 unchanged); donor set must exclude decoupled chains so
  their 2004–06-founded/high-Id outliers don't bend the curve. **Recommended fix for P6:** persist a
  global curve and use it as the fallback in `build_calibration_model` instead of the 2-pt chord;
  give uncalibrated-but-global-covered stores their own confidence treatment (still not founding-
  validated for decoupled brands). *Not yet implemented — design pending.*
- **2026-07-01 (benchmark audit):** Checked whether the per-brand founding benchmark
  (`_build_founding_benchmark_section`) is circular / in-sample. **It is not.** Calibration anchors
  (masothue *activation*) and test points (DKKD *founding*) are **disjoint store sets — 0% Id
  overlap** for every brand; rebuilding the model with each test point's anchor removed leaves MAE
  unchanged (circle-k/coop-food/winmart 23/25/27d in-sample == held-out). The benchmark math is
  honest and out-of-distribution. The real weakness is **selection bias in the evaluation set**: the
  6-brand table covers only the brands that *have* calibration — i.e. exactly the brands where the
  model works — and silently omits the 94.5% on the broken fallback, overstating overall robustness.
  Tool: `scratch/check_benchmark_leakage.py`.
- **2026-07-01:** Backtested the date model on **FPT Shop** (uncalibrated brand, 40 CAPTCHA-fetched
  ground-truth founding dates) → **0% year-accuracy (0/40), MAE 897d, only 1/40 within 1yr**, every
  real date *later* than predicted. Root cause (P6): FPT Shop has no `masothue_store_statuses.json`
  (Stage 1.5 opt-in sweep was never run) and no config calibration, so `build_calibration_model`
  degenerated to the last-resort **2-point chord** `(383151→2010-01-01)…(12655214→today)` — both
  anchors fabricated (max = `datetime.now()`). Verified: (H1) all 40/40 real points lie *above* the
  chord with a +290→+1035→+665d arc ⇒ the national `Id→date` curve is concave (registry rate
  accelerates), so a constant-rate line undercuts interior Ids; (H2) refitting on 20 real *founding*
  points and testing the other 20 → MAE **3d**, 100% ≤1yr ⇒ the interpolation *method* is sound and
  FPT founding is a smooth function of Id; the defect is missing calibration data. (H2 caveat: it
  trains on founding, while the production Stage-1.5 fix calibrates on *activation* — so the remedy
  reaches this accuracy only where activation≈founding.) Blast radius: **290/307 brands (94.5%)**
  have no calibration file → same fallback. NB the checkpoint store-count drifted (429/499/611)
  across same-file reads during analysis; the 897d headline uses fixed anchors + the 40 fixed truth
  points (`scratch/verify_curve.py`), not the transient run. Tools: `scratch/diagnose_model.py`
  (anchors), `scratch/verify_curve.py` (H1/H2 + headline), `scratch/backtest_model_only.py`.
- **2026-06-30:** Benchmarked the model vs 173 hand-fetched real founding dates. Found the
  `medium` tier (all PNJ suffix-axis) was ~7yr off founding — worse than `low`. Two gates
  (`scratch/axis_gate_test.py`): Gate 1 — every suffix-axis MST is a mass-refile chain (safe
  to demote); Gate 2 — Id axis no better (founding unrecoverable). **Fix:** capped suffix-axis
  confidence at `low`. Result: `medium` tier emptied (n=18→0), `high` unchanged (6d median,
  100%≤1yr), all multi-year errors now `low`. PNJ CSV regenerated (47 medium→low, nothing
  else moved). RULED OUT: changing axis selection (see above).
- **2026-06-30:** Added the "Activation↔Founding Gap" section to `dkkd backtest`
  (`_build_founding_benchmark_section`) so the founding error surfaces in production output,
  not just a scratch script. Reworded after the user settled column = *activation estimate*.

## Links

- Code: `dkkd/enrich.py` (`PerMstDateInterpolator.confidence`, `_build_mst_axis_model`,
  `apply_date_interpolation`, `build_calibration_model`); `dkkd/backtest.py`
  (`_build_founding_benchmark_section`, `_build_date_backtest_section`)
- Tests: `tests/test_enrich_date_interpolation.py` (`test_confidence_suffix_axis_capped_at_low`),
  `tests/test_backtest_founding_benchmark.py`, `tests/test_backtest_date_interpolation.py`
- Data / tools: `scratch/axis_gate_test.py`, `scratch/benchmark_analyze.py`, `scratch/bh_fetch.py`,
  `brands/**/output/enterprise_details.json` (founding ground truth)
- Source docs: `docs/archive/date_model_benchmark_2026-06-30.md` (deep reference)
- Memory slugs: `date-interpolation-axis-selection`, `date-model-benchmark-findings`
- Related pages: [status-resolution](status-resolution.md), [captcha-fetch](captcha-fetch.md)
  (founding ground truth is fetched there)

## Validate / reproduce

- `PYTHONPATH=. python scratch/axis_gate_test.py` — Gate 1 (suffix-axis MSTs) + Gate 2
  (founding error by predictor).
- `python -m dkkd.cli backtest --brand <slug>` — read the "Activation↔Founding Gap" section;
  confirm `high`/`medium` ≤1yr and worst misses all `low`.
- `PYTHONIOENCODING=utf-8 python scratch/benchmark_analyze.py` — per-brand × tier accuracy
  vs founding (note: reads CSV labels, which may be stale per P4).
