"""Прогнозирование временных рядов: baseline и модели, hold-out и скользящая кросс-валидация.

Все модели имеют единый интерфейс ``model(train: pd.Series, h: int, m: int) -> np.ndarray``
и регистрируются в ``MODEL_REGISTRY``. Baseline: Naive, Seasonal naive, Drift.
Модели: Linear trend, ETS (Holt / Holt-Winters), ARIMA/SARIMA, Lag LR, Lag GBM.
"""

from __future__ import annotations

import itertools
import time
import warnings
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from . import config, metrics, timeseries

ModelFn = Callable[[pd.Series, int, int], np.ndarray]
MODEL_REGISTRY: dict[str, ModelFn] = {}
BASELINES = ["Naive", "Seasonal naive", "Drift"]
MODELS = ["Linear trend", "ETS", "ARIMA", "Lag LR", "Lag GBM"]


def register(name: str) -> Callable[[ModelFn], ModelFn]:
    """Декоратор регистрации модели в реестре."""
    def wrap(fn: ModelFn) -> ModelFn:
        MODEL_REGISTRY[name] = fn
        return fn
    return wrap


# --- Baseline --------------------------------------------------------------------

@register("Naive")
def naive(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Наивный прогноз: последнее наблюдение повторяется h раз."""
    return np.repeat(float(train.iloc[-1]), h)


@register("Seasonal naive")
def seasonal_naive(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Сезонно-наивный прогноз: значение того же периода прошлого сезона (при m=1 ≡ Naive)."""
    if m <= 1 or len(train) < m:
        return naive(train, h, m)
    last_season = train.iloc[-m:].to_numpy(dtype=float)
    return np.array([last_season[i % m] for i in range(h)])


@register("Drift")
def drift(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Наивный прогноз с дрейфом: последнее значение + средний исторический прирост."""
    y = train.to_numpy(dtype=float)
    slope = (y[-1] - y[0]) / (len(y) - 1) if len(y) > 1 else 0.0
    return y[-1] + slope * np.arange(1, h + 1)


# --- Модели ------------------------------------------------------------------------

@register("Linear trend")
def linear_trend(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Линейный тренд по времени (МНК): «трендовый прогноз» из постановки темы."""
    y = train.to_numpy(dtype=float)
    t = np.arange(len(y))
    slope, intercept = np.polyfit(t, y, deg=1)
    return intercept + slope * np.arange(len(y), len(y) + h)


@register("ETS")
def ets(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Экспоненциальное сглаживание: Holt с затухающим трендом; Holt-Winters при m>1."""
    seasonal = "add" if (m > 1 and len(train) >= 2 * m) else None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", FutureWarning)
        model = ExponentialSmoothing(
            train.to_numpy(dtype=float), trend="add", damped_trend=True,
            seasonal=seasonal, seasonal_periods=m if seasonal else None,
            initialization_method="estimated",
        ).fit(optimized=True)
    return np.asarray(model.forecast(h), dtype=float)


def _arima_orders(m: int) -> list[tuple[tuple[int, int, int], tuple[int, int, int, int]]]:
    """Небольшая сетка порядков ARIMA/SARIMA для выбора по AIC."""
    orders = []
    seasonal_orders = [(0, 1, 1, m), (1, 1, 0, m)] if m > 1 else [(0, 0, 0, 0)]
    for p, q in itertools.product(range(0, 3), range(0, 3)):
        for so in seasonal_orders:
            orders.append(((p, 1, q), so))
    return orders


@register("ARIMA")
def arima(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """ARIMA(p,1,q) (SARIMA при m>1); порядок выбирается по AIC из небольшой сетки."""
    y = train.to_numpy(dtype=float)
    best_aic, best_fit = np.inf, None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order, sorder in _arima_orders(m):
            try:
                fit = ARIMA(y, order=order, seasonal_order=sorder, trend="t" if m == 1 else None).fit()
            except (ValueError, np.linalg.LinAlgError):
                continue
            if np.isfinite(fit.aic) and fit.aic < best_aic:
                best_aic, best_fit = fit.aic, fit
    if best_fit is None:
        return drift(train, h, m)
    return np.asarray(best_fit.forecast(h), dtype=float)


def make_lag_features(y: np.ndarray, n_lags: int, m: int = 1, start_index: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Матрица признаков из лагов 1..n_lags, индекса времени и (при m>1) номера сезона.

    Возвращает (X, y_target) для обучающих строк, где все лаги определены.
    """
    rows, targets = [], []
    for t in range(n_lags, len(y)):
        features = [y[t - k] for k in range(1, n_lags + 1)] + [t + start_index]
        if m > 1:
            features.append((t + start_index) % m)
        rows.append(features)
        targets.append(y[t])
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _recursive_forecast(predict: Callable[[np.ndarray], float], history: np.ndarray,
                        n_lags: int, h: int, m: int) -> np.ndarray:
    """Рекурсивный многошаговый прогноз: предсказанное значение становится лагом следующего шага."""
    hist = list(history)
    preds = []
    for step in range(h):
        t = len(hist)
        features = [hist[t - k] for k in range(1, n_lags + 1)] + [t]
        if m > 1:
            features.append(t % m)
        value = float(predict(np.asarray([features], dtype=float)))
        preds.append(value)
        hist.append(value)
    return np.asarray(preds)


@register("Lag LR")
def lag_lr(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Гребневая линейная регрессия на лагах + линейный тренд (+ сезон для m>1)."""
    y = train.to_numpy(dtype=float)
    n_lags = max(3, m) if len(y) > 2 * max(3, m) + 2 else max(1, len(y) // 4)
    X, target = make_lag_features(y, n_lags, m)
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(X, target)
    return _recursive_forecast(lambda f: model.predict(f)[0], y, n_lags, h, m)


@register("Lag GBM")
def lag_gbm(train: pd.Series, h: int, m: int = 1) -> np.ndarray:
    """Градиентный бустинг (HistGradientBoosting) на лагах приростов.

    Деревья не экстраполируют уровень, поэтому модель учится на разностях
    y_t − y_{t−1}, а прогноз восстанавливается накопленной суммой.
    """
    y = train.to_numpy(dtype=float)
    d = np.diff(y)
    n_lags = max(3, m) if len(d) > 2 * max(3, m) + 2 else max(1, len(d) // 4)
    X, target = make_lag_features(d, n_lags, m, start_index=1)
    model = HistGradientBoostingRegressor(
        max_iter=150, learning_rate=0.05, max_depth=2, l2_regularization=1.0,
        min_samples_leaf=max(3, len(target) // 8), random_state=config.RANDOM_SEED,
    ).fit(X, target)
    deltas = _recursive_forecast(lambda f: model.predict(f)[0], d, n_lags, h, m)
    # сдвиг индексов на 1 из-за дифференцирования учтён в start_index при обучении
    return y[-1] + np.cumsum(deltas)


# --- Оценка -----------------------------------------------------------------------

def holdout_split(series: pd.Series, h: int) -> tuple[pd.Series, pd.Series]:
    """Хронологический hold-out: последние h наблюдений — тест, без перемешивания."""
    series = series.dropna()
    if len(series) <= h + 5:
        raise ValueError(f"Ряд слишком короткий ({len(series)}) для hold-out {h}")
    return series.iloc[:-h], series.iloc[-h:]


def run_model(name: str, train: pd.Series, h: int, m: int) -> tuple[np.ndarray, float, str | None]:
    """Запустить модель с замером времени; при ошибке вернуть NaN-прогноз и текст ошибки."""
    fn = MODEL_REGISTRY[name]
    start = time.perf_counter()
    try:
        pred = fn(train, h, m)
        error = None
    except (ValueError, np.linalg.LinAlgError, RuntimeError) as err:
        pred, error = np.full(h, np.nan), f"{type(err).__name__}: {err}"
    elapsed = time.perf_counter() - start
    return pred, elapsed, error


def evaluate_holdout(series: pd.Series, h: int, m: int = 1, models: list[str] | None = None,
                     series_name: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Оценить все модели на hold-out: таблица метрик и длинная таблица прогнозов."""
    models = models or (BASELINES + MODELS)
    train, test = holdout_split(series, h)
    metric_rows, forecast_rows = [], []
    for name in models:
        pred, elapsed, error = run_model(name, train, h, m)
        row = {"series": series_name, "model": name, "is_baseline": name in BASELINES,
               "n_train": len(train), "n_test": len(test), "train_time_s": round(elapsed, 4), "error": error}
        if error is None:
            row.update(metrics.evaluate(test.to_numpy(), pred, train.to_numpy(), m))
        metric_rows.append(row)
        for date, y_true, y_pred in zip(test.index, test.to_numpy(), pred):
            forecast_rows.append({"series": series_name, "model": name, "date": date,
                                  "y_true": float(y_true), "y_pred": float(y_pred)})
    return pd.DataFrame(metric_rows), pd.DataFrame(forecast_rows)


def rolling_cv(series: pd.Series, n_splits: int = 4, test_size: int = 3, m: int = 1,
               models: list[str] | None = None, series_name: str = "") -> pd.DataFrame:
    """Скользящая кросс-валидация TimeSeriesSplit (без перемешивания): метрики по блокам и моделям."""
    models = models or (BASELINES + MODELS)
    y = series.dropna()
    splitter = TimeSeriesSplit(n_splits=n_splits, test_size=test_size)
    rows = []
    for fold, (train_idx, test_idx) in enumerate(splitter.split(y.to_numpy()), start=1):
        train, test = y.iloc[train_idx], y.iloc[test_idx]
        for name in models:
            pred, elapsed, error = run_model(name, train, len(test), m)
            row = {"series": series_name, "fold": fold, "model": name, "is_baseline": name in BASELINES,
                   "train_end": train.index[-1], "n_train": len(train), "train_time_s": round(elapsed, 4)}
            if error is None:
                row.update(metrics.evaluate(test.to_numpy(), pred, train.to_numpy(), m))
            rows.append(row)
    return pd.DataFrame(rows)


def summarize_cv(cv: pd.DataFrame) -> pd.DataFrame:
    """Средние метрики по блокам CV для каждой модели (сортировка по MASE)."""
    cols = [c for c in ("MAE", "RMSE", "MAPE", "sMAPE", "MASE", "train_time_s") if c in cv.columns]
    out = cv.groupby("model")[cols].mean().round(4)
    out["is_baseline"] = out.index.isin(BASELINES)
    return out.sort_values("MASE" if "MASE" in out else "MAE")


def forecast_battery(series_dict: dict[str, pd.Series], h: int, m: int = 1,
                     models: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold-out оценка по многим сериям (странам) — для анализа ошибок по сериям."""
    all_metrics, all_forecasts = [], []
    for name, series in series_dict.items():
        try:
            met, fc = evaluate_holdout(series, h, m, models, series_name=name)
        except ValueError as err:
            print(f"[forecast_battery] {name}: {err}")
            continue
        all_metrics.append(met)
        all_forecasts.append(fc)
    if not all_metrics:
        return pd.DataFrame(), pd.DataFrame()
    return pd.concat(all_metrics, ignore_index=True), pd.concat(all_forecasts, ignore_index=True)


def future_forecast(series: pd.Series, model_name: str, h: int, m: int = 1) -> pd.DataFrame:
    """Прогноз «в будущее» на h периодов с простым эмпирическим интервалом.

    Интервал: ±1.96·σ·√k, где σ — ст. отклонение наивных (при m>1 — сезонно-наивных)
    одношаговых ошибок, k — число шагов (сезонов) вперёд.
    """
    y = series.dropna()
    pred, _, error = run_model(model_name, y, h, m)
    if error:
        raise ValueError(error)
    freq = timeseries.infer_freq_str(y.index) or ("MS" if m == 12 else "YS")
    future_index = pd.date_range(y.index[-1], periods=h + 1, freq=freq)[1:]
    values = y.to_numpy(dtype=float)
    lag = m if (m > 1 and len(values) > 2 * m) else 1
    sigma = float(np.std(values[lag:] - values[:-lag]))
    k = np.ceil(np.arange(1, h + 1) / lag)
    return pd.DataFrame({"date": future_index, "forecast": pred,
                         "lower": pred - 1.96 * sigma * np.sqrt(k), "upper": pred + 1.96 * sigma * np.sqrt(k)})


def select_model(holdout_metrics: pd.DataFrame, cv_summary: pd.DataFrame, by: str = "MASE",
                 exclude_baselines: bool = True) -> str:
    """Выбрать модель для прогноза в будущее по сумме рангов на hold-out и в скользящей CV."""
    hold = holdout_metrics.set_index("model")[by].rank()
    cv = cv_summary[by].rank()
    total = (hold + cv).dropna().sort_values()
    if exclude_baselines:
        total = total[~total.index.isin(BASELINES)]
    return str(total.index[0])


def rank_models(holdout_metrics: pd.DataFrame, by: str = "MASE") -> pd.DataFrame:
    """Средний ранг моделей по сериям (устойчивее средней ошибки, т.к. масштабы стран разные)."""
    df = holdout_metrics.dropna(subset=[by]).copy()
    df["rank"] = df.groupby("series")[by].rank(method="min")
    out = df.groupby("model").agg(mean_rank=("rank", "mean"), median_metric=(by, "median"),
                                  mean_train_time_s=("train_time_s", "mean"), n_series=("series", "nunique"))
    out["is_baseline"] = out.index.isin(BASELINES)
    return out.sort_values("mean_rank").round(4)
