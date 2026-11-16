"""Данные для 3D-фронтенда: всё, что рисует браузер, считается здесь, на Python.

Функции возвращают обычные словари и списки (JSON-совместимые): панель для глобуса,
энергобаланс и месячный ряд страны, прогноз с метриками, результаты SQL-запросов.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pandas as pd

from . import cleaning, config, database, forecasting, io_utils, timeseries

FAST_MONTHLY_MODELS = ["Naive", "Seasonal naive", "Linear trend", "ETS", "Lag LR", "Lag GBM"]   # без перебора SARIMA
MAX_SQL_ROWS = 300


def _num(value, digits: int = 3):
    """Число для JSON: NaN/inf → None, остальное округляется."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return round(value, digits)


def _series(values, digits: int = 3) -> list:
    return [_num(v, digits) for v in values]


@lru_cache(maxsize=1)
def _panel() -> pd.DataFrame:
    return cleaning.load_processed("panel")


@lru_cache(maxsize=1)
def _monthly() -> pd.DataFrame:
    return cleaning.load_processed("monthly")


@lru_cache(maxsize=1)
def _countries() -> pd.DataFrame:
    return cleaning.load_processed("countries")


def _name_by_iso(iso: str) -> str:
    meta = _countries()
    match = meta.loc[meta["iso_code"] == iso.upper(), "country"]
    if match.empty:
        raise KeyError(f"Страна с кодом {iso} не найдена")
    return str(match.iloc[0])


def display_name(country: str) -> str:
    """Название страны для интерфейса: русское для стран-аналогов, иначе как в данных."""
    return config.COUNTRY_NAMES_RU.get(country, country)


# --- Стартовый пакет: панель для глобуса -------------------------------------------------

@lru_cache(maxsize=1)
def bootstrap() -> dict:
    """Всё, что нужно глобусу и шкале времени: страны, годы, показатели по годам, группы аналогов."""
    panel, meta = _panel(), _countries()
    years = list(range(int(panel["year"].min()), int(panel["year"].max()) + 1))
    iso_by_name = dict(zip(meta["country"], meta["iso_code"]))
    monthly_countries = set(_monthly()["country"].unique())
    mix_col = config.ENERGY_SOURCES["coal"]["column"]
    has_mix = set(panel.loc[panel[mix_col].notna(), "country"].unique())

    keys = [m["key"] for m in config.WEB_METRICS] + ["population"]
    values: dict[str, dict[str, list]] = {k: {} for k in keys}
    for country, group in panel.groupby("country", observed=True):
        iso = iso_by_name.get(country)
        if iso is None:
            continue
        g = group.set_index("year").reindex(years)
        for k in keys:
            digits = 0 if k == "population" else 3
            values[k][iso] = _series(g[k].to_numpy(), digits)

    countries = [
        {"iso": r.iso_code, "name": r.country, "label": display_name(r.country), "continent": r.continent,
         "has_mix": r.country in has_mix, "has_monthly": r.country in monthly_countries}
        for r in meta.itertuples()
    ]
    return {
        "project": {"name": "EnergyShift KZ", "topic": "Global Energy Mix and CO₂ Emissions",
                    "team": "Aidar, Daniyal, Nurzhan", "group": "AAI-2604"},
        "target": iso_by_name[config.TARGET_COUNTRY],
        "years": years,
        "metrics": config.WEB_METRICS,
        "countries": countries,
        "values": values,
        "peer_groups": {name: [iso_by_name[c] for c in members if c in iso_by_name] for name, members in config.PEER_GROUPS.items()},
        "sources": [{"key": k, "label": v["label"]} for k, v in config.ENERGY_SOURCES.items()],
    }


# --- Страна: энергобаланс и месячный ряд -------------------------------------------------

@lru_cache(maxsize=64)
def country_detail(iso: str) -> dict:
    """Энергобаланс по годам (ТВт·ч по 9 источникам) и месячные выбросы электроэнергетики, если они есть."""
    name = _name_by_iso(iso)
    panel = _panel()
    sub = panel[panel["country"] == name].sort_values("year")
    mix = None
    cols = {k: v["column"] for k, v in config.ENERGY_SOURCES.items()}
    have = sub.dropna(subset=[cols["coal"]])
    if not have.empty:
        mix = {"years": [int(y) for y in have["year"]],
               "sources": {k: _series(have[c].fillna(0).to_numpy(), 2) for k, c in cols.items()}}
    monthly = None
    try:
        s = cleaning.monthly_series(_monthly(), name, "emissions_mtco2")
        monthly = {"dates": [d.strftime("%Y-%m") for d in s.index], "emissions": _series(s.to_numpy(), 3)}
    except ValueError:
        pass
    return {"iso": iso.upper(), "name": name, "label": display_name(name), "mix": mix, "monthly": monthly}


# --- Прогноз -----------------------------------------------------------------------------

def _precomputed(name: str, freq: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Метрики и прогнозы на hold-out, сохранённые пайплайном (есть для стран-аналогов)."""
    met_path = config.RESULTS_DIR / f"forecast_{freq}_metrics.parquet"
    fc_path = config.RESULTS_DIR / f"forecast_{freq}_predictions.parquet"
    if not (met_path.exists() and fc_path.exists()):
        return None
    met, fc = io_utils.read_parquet(met_path), io_utils.read_parquet(fc_path)
    met, fc = met[met["series"] == name], fc[fc["series"] == name]
    if met.empty or fc.empty:
        return None
    return met, fc


def _saved_future(name: str, freq: str) -> pd.DataFrame | None:
    """Прогноз в будущее, сохранённый пайплайном (только для целевой страны)."""
    path = config.RESULTS_DIR / f"forecast_future_{freq}.parquet"
    if name != config.TARGET_COUNTRY or not path.exists():
        return None
    return io_utils.read_parquet(path)


@lru_cache(maxsize=128)
def forecast(iso: str, freq: str = "annual") -> dict:
    """Hold-out прогнозы всех моделей, метрики и прогноз в будущее для страны.

    Для стран-аналогов берутся сохранённые результаты пайплайна, для остальных модели
    обучаются на лету (для месячных данных — без перебора SARIMA, чтобы ответ был быстрым).
    """
    if freq not in ("annual", "monthly"):
        raise ValueError("freq должен быть 'annual' или 'monthly'")
    name = _name_by_iso(iso)
    if freq == "annual":
        series = timeseries.annual_series(_panel(), name, "co2")
        h, m, unit, horizon = config.ANNUAL_HOLDOUT, 1, "млн т CO₂", config.FUTURE_HORIZON
        live_models = forecasting.BASELINES + forecasting.MODELS
        stamp = "%Y"
    else:
        series = cleaning.monthly_series(_monthly(), name, "emissions_mtco2")
        h, m, unit, horizon = config.MONTHLY_HOLDOUT, config.MONTHLY_SEASON, "Мт CO₂ в месяц", 12
        live_models = FAST_MONTHLY_MODELS
        stamp = "%Y-%m"

    saved = _precomputed(name, freq)
    if saved is not None:
        metrics, predictions, source = saved[0], saved[1], "pipeline"
    else:
        metrics, predictions = forecasting.evaluate_holdout(series, h, m, live_models, series_name=name)
        source = "live"
    metrics = metrics.dropna(subset=["MASE"]).sort_values("MASE")

    future = _saved_future(name, freq)
    if future is None:
        candidates = metrics[~metrics["is_baseline"]]
        if freq == "monthly":
            candidates = candidates[candidates["model"] != "ARIMA"]   # перебор SARIMA занимает до 30 с
        best = str((candidates if not candidates.empty else metrics)["model"].iloc[0])
        future = forecasting.future_forecast(series, best, horizon, m).assign(model=best)

    hold_dates = sorted(pd.to_datetime(predictions["date"]).unique())
    by_model = {
        model: _series(g.sort_values("date")["y_pred"].to_numpy())
        for model, g in predictions.assign(date=pd.to_datetime(predictions["date"])).groupby("model")
    }
    truth = predictions[predictions["model"] == predictions["model"].iloc[0]].sort_values("date")
    return {
        "iso": iso.upper(), "name": name, "label": display_name(name), "freq": freq, "unit": unit, "source": source,
        "season": m, "holdout_size": h,
        "history": {"x": [d.strftime(stamp) for d in series.index], "y": _series(series.to_numpy())},
        "holdout": {"x": [pd.Timestamp(d).strftime(stamp) for d in hold_dates],
                    "y_true": _series(truth["y_true"].to_numpy()), "models": by_model},
        "metrics": [
            {"model": r.model, "is_baseline": bool(r.is_baseline), "MAE": _num(r.MAE), "RMSE": _num(r.RMSE),
             "MAPE": _num(r.MAPE, 2), "sMAPE": _num(r.sMAPE, 2), "MASE": _num(r.MASE), "train_time_s": _num(r.train_time_s, 4)}
            for r in metrics.itertuples()
        ],
        "future": {"model": str(future["model"].iloc[0]),
                   "x": [pd.Timestamp(d).strftime(stamp) for d in future["date"]],
                   "y": _series(future["forecast"].to_numpy()), "lower": _series(future["lower"].to_numpy()),
                   "upper": _series(future["upper"].to_numpy())},
    }


# --- SQL -----------------------------------------------------------------------------------

def sql_catalog() -> list[dict]:
    """Список сохранённых SQL-запросов (имя и заголовок)."""
    return [{"name": q["name"], "title": q["title"]} for q in database.list_queries()]


def sql_run(name: str) -> dict:
    """Выполнить сохранённый запрос по имени и вернуть текст, колонки и строки."""
    queries = {q["name"]: q for q in database.list_queries()}
    if name not in queries:
        raise KeyError(f"Запрос {name} не найден")
    q = queries[name]
    df = database.run_query(q["sql"])
    body = "\n".join(line for line in q["sql"].splitlines() if not line.startswith("-- title:")).strip()
    rows = [[(_num(v, 3) if isinstance(v, (int, float, np.integer, np.floating)) else (None if pd.isna(v) else str(v))) for v in row]
            for row in df.head(MAX_SQL_ROWS).itertuples(index=False, name=None)]
    return {"name": name, "title": q["title"], "sql": body, "columns": list(df.columns), "rows": rows, "total": int(len(df))}


def ensure_ready() -> None:
    """Проверить, что обработанные данные есть, и создать базу SQLite, если её ещё нет."""
    cleaning.load_processed("panel")          # FileNotFoundError с понятным текстом, если шаг очистки не выполнен
    if not config.DB_PATH.exists():
        from . import pipeline
        pipeline.step_database()
