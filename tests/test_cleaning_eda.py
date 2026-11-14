import numpy as np
import pandas as pd
import pytest

from energy_co2 import cleaning, eda, io_utils, timeseries


@pytest.fixture
def toy_panel():
    rows = []
    for country, iso in (("Aland", "ALA"), ("Borland", "BOR"), ("World", None)):
        for year in range(1990, 2000):
            rows.append({"country": country, "iso_code": iso, "year": year, "population": 1_000_000 + year,
                         "co2": float(year - 1980) if not (country == "Aland" and year == 1995) else np.nan,
                         "primary_energy_consumption": 10.0})
    return pd.DataFrame(rows)


def test_drop_aggregates_removes_rows_without_iso(toy_panel):
    out = cleaning.drop_aggregates(toy_panel)
    assert "World" not in set(out["country"])
    assert len(out) == 20


def test_fill_gaps_interpolates_inside_only(toy_panel):
    out = cleaning.fill_gaps(toy_panel, ["co2"], limit=2)
    val = out[(out["country"] == "Aland") & (out["year"] == 1995)]["co2"].iloc[0]
    assert val == pytest.approx(15.0)


def test_add_derived_per_capita(toy_panel):
    out = cleaning.add_derived_variables(toy_panel.dropna())
    row = out.iloc[0]
    assert row["co2_per_capita_calc"] == pytest.approx(row["co2"] * 1e6 / row["population"])
    assert row["energy_per_capita_calc"] == pytest.approx(10.0 * 1e9 / row["population"])
    assert "decade" in out


def test_check_time_index_detects_gaps(toy_panel):
    broken = toy_panel[~((toy_panel["country"] == "Borland") & (toy_panel["year"] == 1994))]
    report = eda.check_time_index(broken)
    assert report.set_index("country").loc["Borland", "n_gaps"] == 1
    assert bool(report.set_index("country").loc["Aland", "regular"])


def test_detect_outliers_flags_jump(toy_panel):
    df = toy_panel.dropna().copy()
    df.loc[(df["country"] == "Borland") & (df["year"] == 1997), "co2"] = 500.0
    out = eda.detect_outliers(df, "co2", "iqr")
    assert out[(out["country"] == "Borland") & (out["year"] == 1997)]["is_outlier"].iloc[0]


def test_optimize_dtypes_reduces_memory():
    df = pd.DataFrame({"a": np.random.rand(10_000), "b": np.arange(10_000), "c": ["x", "y"] * 5_000})
    out = io_utils.optimize_dtypes(df)
    assert io_utils.memory_usage_mb(out) < io_utils.memory_usage_mb(df)
    assert str(out["a"].dtype) == "float32" and str(out["c"].dtype) == "category"


def test_stationarity_and_stl_on_synthetic():
    idx = pd.date_range("2015-01-01", periods=72, freq="MS")
    t = np.arange(72)
    s = pd.Series(5 + 2 * np.sin(2 * np.pi * t / 12) + np.random.default_rng(0).normal(0, 0.1, 72), index=idx)
    stl = timeseries.stl_decompose(s, period=12)
    assert stl.attrs["seasonal_strength"] > 0.9
    res = timeseries.stationarity_tests(s)
    assert {"adf_pvalue", "kpss_pvalue", "verdict"} <= set(res)
    acf = timeseries.acf_pacf(s, 24)
    assert acf.loc[12, "acf"] > 0.5
