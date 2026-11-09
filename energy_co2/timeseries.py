"""Анализ временных рядов: resample, скользящие средние, STL, стационарность, ACF/PACF."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf


def infer_freq_str(index: pd.Index) -> str | None:
    """Строковая частота индекса (совместимо с будущим поведением pandas, возвращающим offset)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # pandas 3.x предупреждает о будущем возврате offset
            inferred = pd.infer_freq(index)
    except (TypeError, ValueError):
        return None
    return getattr(inferred, "freqstr", inferred)


def annual_series(panel: pd.DataFrame, country: str, column: str = "co2") -> pd.Series:
    """Годовой ряд страны с индексом DatetimeIndex (freq='YS')."""
    sub = panel.loc[panel["country"] == country, ["year", column]].dropna().sort_values("year")
    if sub.empty:
        raise ValueError(f"Нет данных {column} для {country}")
    idx = pd.to_datetime(sub["year"].astype(int).astype(str) + "-01-01")
    series = pd.Series(sub[column].to_numpy(dtype=float), index=idx, name=column)
    series.index.name = "date"
    series = series.asfreq("YS")
    return series.interpolate(limit=2, limit_area="inside")


def resample_series(series: pd.Series, rule: str = "5YS", how: str = "mean") -> pd.Series:
    """Передискретизация ряда (например, год→пятилетки '5YS', месяц→квартал 'QS', месяц→год 'YS')."""
    resampler = series.resample(rule)
    if how not in ("mean", "sum", "last", "max", "min"):
        raise ValueError("how должен быть mean/sum/last/max/min")
    return getattr(resampler, how)()


def rolling_stats(series: pd.Series, windows: tuple[int, ...] = (3, 5, 10)) -> pd.DataFrame:
    """Скользящие средние и скользящее стандартное отклонение для нескольких окон."""
    out = pd.DataFrame({"value": series})
    for w in windows:
        out[f"ma_{w}"] = series.rolling(w, min_periods=max(2, w // 2)).mean()
    out[f"std_{windows[-1]}"] = series.rolling(windows[-1], min_periods=2).std()
    return out


def stl_decompose(series: pd.Series, period: int | None = None, robust: bool = True) -> pd.DataFrame:
    """Сезонная декомпозиция STL. Для годовых рядов period задаётся явно (напр. 5 — бизнес-цикл)."""
    series = series.dropna()
    if period is None:
        freq = infer_freq_str(series.index) or ""
        period = 12 if freq.startswith("M") else 4 if freq.startswith("Q") else 5
    if len(series) < 2 * period:
        raise ValueError(f"Ряд слишком короткий для STL с периодом {period}: {len(series)} наблюдений")
    result = STL(series, period=period, robust=robust).fit()
    out = pd.DataFrame({"observed": series, "trend": result.trend, "seasonal": result.seasonal, "resid": result.resid})
    var_resid, var_deseason = np.var(result.resid), np.var(result.resid + result.seasonal)
    out.attrs["seasonal_strength"] = float(max(0.0, 1 - var_resid / var_deseason)) if var_deseason > 0 else 0.0
    var_detrend = np.var(result.resid + result.trend)
    out.attrs["trend_strength"] = float(max(0.0, 1 - var_resid / var_detrend)) if var_detrend > 0 else 0.0
    out.attrs["period"] = period
    return out


def stationarity_tests(series: pd.Series, alpha: float = 0.05) -> dict:
    """ADF (H0: единичный корень) и KPSS (H0: стационарность) с интерпретацией."""
    x = series.dropna().to_numpy(dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # KPSS предупреждает, если p-value вышло за таблицу
        adf_stat, adf_p, adf_lags, *_ = adfuller(x, autolag="AIC")
        kpss_stat, kpss_p, kpss_lags, _ = kpss(x, regression="c", nlags="auto")
    adf_stationary = adf_p < alpha
    kpss_stationary = kpss_p >= alpha
    if adf_stationary and kpss_stationary:
        verdict = "стационарен"
    elif not adf_stationary and not kpss_stationary:
        verdict = "нестационарен (нужно дифференцирование)"
    elif adf_stationary and not kpss_stationary:
        verdict = "разностно-стационарный / тренд-стационарный (противоречие тестов)"
    else:
        verdict = "недостаточно данных для уверенного вывода"
    return {
        "n": int(len(x)), "adf_stat": round(float(adf_stat), 4), "adf_pvalue": round(float(adf_p), 4),
        "adf_lags": int(adf_lags), "kpss_stat": round(float(kpss_stat), 4), "kpss_pvalue": round(float(kpss_p), 4),
        "adf_stationary": bool(adf_stationary), "kpss_stationary": bool(kpss_stationary), "verdict": verdict,
    }


def difference(series: pd.Series, lag: int = 1, seasonal_lag: int | None = None) -> pd.Series:
    """Обычное и (опционально) сезонное дифференцирование."""
    out = series.diff(lag)
    if seasonal_lag:
        out = out.diff(seasonal_lag)
    return out.dropna()


def acf_pacf(series: pd.Series, nlags: int | None = None, alpha: float = 0.05) -> pd.DataFrame:
    """Значения ACF/PACF с доверительными границами для таблицы и графика."""
    x = series.dropna().to_numpy(dtype=float)
    max_lags = max(1, min(nlags or 20, len(x) // 2 - 1))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        acf_vals, acf_conf = acf(x, nlags=max_lags, alpha=alpha, fft=False)[:2]
        pacf_vals, pacf_conf = pacf(x, nlags=max_lags, alpha=alpha, method="ywm")[:2]
    return pd.DataFrame({
        "lag": np.arange(max_lags + 1), "acf": acf_vals, "pacf": pacf_vals,
        "acf_lower": acf_conf[:, 0] - acf_vals, "acf_upper": acf_conf[:, 1] - acf_vals,
        "pacf_lower": pacf_conf[:, 0] - pacf_vals, "pacf_upper": pacf_conf[:, 1] - pacf_vals,
        "conf_bound": 1.96 / np.sqrt(len(x)),
    })


def ts_summary(series: pd.Series, period: int | None = None) -> dict:
    """Сводка по ряду: длина, частота, стационарность, сила тренда и сезонности."""
    summary = {"name": series.name, "n": int(series.dropna().shape[0]),
               "start": str(series.index.min().date()), "end": str(series.index.max().date()),
               "freq": infer_freq_str(series.index)}
    summary.update({f"level_{k}": v for k, v in stationarity_tests(series).items()})
    diffed = difference(series)
    summary.update({f"diff1_{k}": v for k, v in stationarity_tests(diffed).items() if k in ("adf_pvalue", "kpss_pvalue", "verdict")})
    try:
        stl = stl_decompose(series, period=period)
        summary["seasonal_strength"] = round(stl.attrs["seasonal_strength"], 3)
        summary["trend_strength"] = round(stl.attrs["trend_strength"], 3)
        summary["stl_period"] = stl.attrs["period"]
    except ValueError as err:
        summary["stl_error"] = str(err)
    return summary
