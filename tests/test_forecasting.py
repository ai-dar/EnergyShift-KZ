import numpy as np
import pandas as pd
import pytest

from energy_co2 import forecasting


@pytest.fixture
def trend_series():
    idx = pd.date_range("1990-01-01", periods=30, freq="YS")
    return pd.Series(100 + 3 * np.arange(30) + np.sin(np.arange(30)), index=idx, name="y")


@pytest.fixture
def seasonal_series():
    idx = pd.date_range("2015-01-01", periods=96, freq="MS")
    t = np.arange(96)
    return pd.Series(10 + 0.02 * t + 2 * np.sin(2 * np.pi * t / 12), index=idx, name="y")


def test_naive_and_seasonal_naive(seasonal_series):
    train = seasonal_series.iloc[:-12]
    assert np.all(forecasting.naive(train, 3) == train.iloc[-1])
    sn = forecasting.seasonal_naive(train, 12, m=12)
    assert np.allclose(sn, train.iloc[-12:].to_numpy())
    assert np.allclose(forecasting.seasonal_naive(train, 3, m=1), forecasting.naive(train, 3))


def test_drift_and_linear_trend_extrapolate(trend_series):
    train = trend_series.iloc[:-5]
    assert forecasting.drift(train, 5)[-1] > train.iloc[-1]
    lt = forecasting.linear_trend(train, 5)
    assert lt[-1] == pytest.approx(100 + 3 * 29, abs=2)


def test_registry_contains_all_models():
    for name in forecasting.BASELINES + forecasting.MODELS:
        assert name in forecasting.MODEL_REGISTRY


def test_holdout_split_is_chronological(trend_series):
    train, test = forecasting.holdout_split(trend_series, 5)
    assert train.index.max() < test.index.min()
    assert len(test) == 5
    with pytest.raises(ValueError):
        forecasting.holdout_split(trend_series.iloc[:8], 5)


def test_evaluate_holdout_all_models(trend_series):
    metrics, forecasts = forecasting.evaluate_holdout(trend_series, 5, m=1, series_name="t")
    assert set(metrics["model"]) == set(forecasting.BASELINES + forecasting.MODELS)
    assert metrics["error"].isna().all()
    assert len(forecasts) == 5 * len(metrics)
    # на линейном тренде trend-модели должны бить naive
    by = metrics.set_index("model")["MASE"]
    assert by["Linear trend"] < by["Naive"]


def test_models_beat_naive_on_seasonal_series(seasonal_series):
    metrics, _ = forecasting.evaluate_holdout(seasonal_series, 12, m=12, models=["Naive", "Seasonal naive", "ETS", "Lag LR"])
    by = metrics.set_index("model")["MASE"]
    assert by["Seasonal naive"] < by["Naive"]
    assert by["ETS"] < by["Naive"]


def test_rolling_cv_no_shuffle(trend_series):
    cv = forecasting.rolling_cv(trend_series, n_splits=3, test_size=3, models=["Naive", "Drift"])
    assert cv["fold"].nunique() == 3
    assert cv.groupby("fold")["train_end"].first().is_monotonic_increasing
    summary = forecasting.summarize_cv(cv)
    assert {"Naive", "Drift"} == set(summary.index)


def test_future_forecast_shape(trend_series):
    fut = forecasting.future_forecast(trend_series, "Drift", 4, m=1)
    assert list(fut.columns) == ["date", "forecast", "lower", "upper"]
    assert len(fut) == 4 and (fut["upper"] >= fut["lower"]).all()
    assert fut["date"].iloc[0].year == trend_series.index[-1].year + 1


def test_select_model_excludes_baselines(trend_series):
    metrics, _ = forecasting.evaluate_holdout(trend_series, 5, m=1, models=["Naive", "Drift", "Linear trend", "ETS"])
    cv = forecasting.summarize_cv(forecasting.rolling_cv(trend_series, 2, 3, models=["Naive", "Drift", "Linear trend", "ETS"]))
    assert forecasting.select_model(metrics, cv) in ("Linear trend", "ETS")
