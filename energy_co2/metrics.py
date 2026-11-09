"""Метрики качества прогноза: MAE, RMSE, MAPE, sMAPE, MASE."""

from __future__ import annotations

import numpy as np
import pandas as pd

ArrayLike = "np.ndarray | pd.Series | list[float]"


def _to_array(x) -> np.ndarray:
    return np.asarray(x, dtype=float).ravel()


def mae(y_true, y_pred) -> float:
    """Средняя абсолютная ошибка."""
    y_true, y_pred = _to_array(y_true), _to_array(y_pred)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> float:
    """Корень из средней квадратичной ошибки."""
    y_true, y_pred = _to_array(y_true), _to_array(y_pred)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true, y_pred, eps: float = 1e-9) -> float:
    """Средняя абсолютная процентная ошибка, %. Нули в y_true исключаются."""
    y_true, y_pred = _to_array(y_true), _to_array(y_pred)
    mask = np.abs(y_true) > eps
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def smape(y_true, y_pred, eps: float = 1e-9) -> float:
    """Симметричная MAPE, % (0..200)."""
    y_true, y_pred = _to_array(y_true), _to_array(y_pred)
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2
    mask = denom > eps
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs(y_true[mask] - y_pred[mask]) / denom[mask]) * 100)


def mase(y_true, y_pred, y_train, m: int = 1) -> float:
    """MASE: MAE прогноза / MAE наивного (сезонно-наивного) прогноза in-sample с шагом m.

    MASE < 1 означает, что модель лучше наивного baseline на обучающей выборке.
    """
    y_true, y_pred, y_train = _to_array(y_true), _to_array(y_pred), _to_array(y_train)
    if len(y_train) <= m:
        return float("nan")
    scale = np.mean(np.abs(y_train[m:] - y_train[:-m]))
    if scale == 0:
        return float("nan")
    return float(mae(y_true, y_pred) / scale)


def evaluate(y_true, y_pred, y_train=None, m: int = 1) -> dict[str, float]:
    """Все метрики в одном словаре (MASE только если передан y_train)."""
    result = {
        "MAE": mae(y_true, y_pred), "RMSE": rmse(y_true, y_pred),
        "MAPE": mape(y_true, y_pred), "sMAPE": smape(y_true, y_pred),
    }
    if y_train is not None:
        result["MASE"] = mase(y_true, y_pred, y_train, m)
    return {k: round(v, 4) for k, v in result.items()}


def errors_by_period(y_true: pd.Series, y_pred: pd.Series) -> pd.DataFrame:
    """Ошибки по каждому периоду горизонта (для анализа ошибок по периодам)."""
    df = pd.DataFrame({"y_true": y_true, "y_pred": y_pred})
    df["error"] = df["y_pred"] - df["y_true"]
    df["abs_error"] = df["error"].abs()
    df["ape"] = (df["abs_error"] / df["y_true"].abs().replace(0, np.nan)) * 100
    df["horizon"] = np.arange(1, len(df) + 1)
    return df
