import pandas as pd

from dkkd.backtest import _build_registration_curve_section


def test_returns_empty_when_csv_missing(tmp_path):
    brands_root = tmp_path / 'brands'
    (brands_root / 'no-csv-brand').mkdir(parents=True)
    section = _build_registration_curve_section('no-csv-brand', brands_root)
    assert section == ''


def test_returns_empty_when_column_missing(tmp_path):
    brands_root = tmp_path / 'brands'
    brand_dir = brands_root / 'no-col-brand'
    out_dir = brand_dir / 'output'
    out_dir.mkdir(parents=True)
    pd.DataFrame([{'Id': 1, 'Name': 'x'}]).to_csv(
        out_dir / 'no-col-brand.csv', index=False)
    section = _build_registration_curve_section('no-col-brand', brands_root)
    assert section == ''


def test_flags_low_median_gap_year_as_burst(tmp_path):
    brands_root = tmp_path / 'brands'
    brand_dir = brands_root / 'burst-brand'
    out_dir = brand_dir / 'output'
    out_dir.mkdir(parents=True)
    rows = [
        {'Id': 1000, 'Establishment_Year': 2020},
        {'Id': 1001, 'Establishment_Year': 2020},
        {'Id': 1002, 'Establishment_Year': 2020},
        {'Id': 50000, 'Establishment_Year': 2021},
        {'Id': 90000, 'Establishment_Year': 2021},
    ]
    pd.DataFrame(rows).to_csv(out_dir / 'burst-brand.csv', index=False)

    section = _build_registration_curve_section('burst-brand', brands_root)

    assert '2020' in section
    assert '2021' in section
    assert '| 2020 | 3 | 1 |' in section
    assert '| 2021 | 2 | 40,000 |' in section
