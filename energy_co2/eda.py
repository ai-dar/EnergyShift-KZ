"""Разведочный анализ: описательная статистика, пропуски, выбросы, проверка временных индексов."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, timeseries

KEY = ["country", "iso_code", "year"]


def describe_panel(panel: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Описательная статистика числовых колонок (с медианой и долей пропусков)."""
    cols = columns or [c for c in panel.columns if c not in KEY and pd.api.types.is_numeric_dtype(panel[c])]
    desc = panel[cols].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).T
    desc["missing_pct"] = (panel[cols].isna().mean() * 100).round(1)
    desc["n_countries"] = [panel.loc[panel[c].notna(), "country"].nunique() for c in cols]
    return desc.round(3)


def missing_report(panel: pd.DataFrame, by: str = "column") -> pd.DataFrame:
    """Отчёт о пропусках: по колонкам (`column`) или по годам (`year`)."""
    numeric = [c for c in panel.columns if c not in KEY]
    if by == "column":
        out = pd.DataFrame({
            "missing": panel[numeric].isna().sum(),
            "missing_pct": (panel[numeric].isna().mean() * 100).round(1),
        }).sort_values("missing_pct", ascending=False)
        out.index.name = "variable"
        return out.reset_index()
    if by == "year":
        out = panel.groupby("year")[numeric].apply(lambda g: g.isna().mean() * 100).round(1)
        return out.reset_index()
    if by == "country":
        out = (panel.groupby("country", observed=True)[numeric].apply(lambda g: g.isna().mean() * 100)
               .mean(axis=1).round(1).sort_values(ascending=False))
        return out.rename("missing_pct").reset_index()
    raise ValueError("by должен быть 'column', 'year' или 'country'")


def check_time_index(panel: pd.DataFrame, group: str = "country", time_col: str = "year", step: int = 1) -> pd.DataFrame:
    """Проверить частоту и непрерывность временного индекса для каждой серии.

    Для каждой страны: первый/последний год, число наблюдений, ожидаемое число,
    число пропущенных периодов (gaps) и дубликатов.
    """
    rows = []
    for name, g in panel.groupby(group, observed=True):
        t = g[time_col].sort_values()
        expected = int((t.iloc[-1] - t.iloc[0]) / step) + 1 if len(t) else 0
        diffs = np.diff(t.values) if len(t) > 1 else np.array([])
        rows.append({
            group: name, "start": t.iloc[0], "end": t.iloc[-1], "n_obs": len(t),
            "n_expected": expected, "n_gaps": int(expected - t.nunique()),
            "n_duplicates": int(t.duplicated().sum()),
            "regular": bool(len(diffs) == 0 or np.all(diffs == step)),
        })
    return pd.DataFrame(rows)


def check_monthly_index(monthly: pd.DataFrame, source: str = "Total generation") -> pd.DataFrame:
    """Проверка непрерывности месячного индекса (freq=MS) для каждой страны."""
    rows = []
    sub = monthly[monthly["source"] == source]
    for country, g in sub.groupby("country", observed=True):
        dates = g["date"].sort_values()
        full = pd.date_range(dates.min(), dates.max(), freq="MS")
        inferred = timeseries.infer_freq_str(pd.DatetimeIndex(dates)) if len(dates) >= 3 else None
        rows.append({"country": country, "start": dates.min().date(), "end": dates.max().date(),
                     "n_obs": len(dates), "n_expected": len(full), "n_gaps": len(full) - dates.nunique(),
                     "inferred_freq": inferred, "n_duplicates": int(dates.duplicated().sum())})
    return pd.DataFrame(rows)


def detect_outliers(panel: pd.DataFrame, column: str = "co2", method: str = "iqr",
                    k: float = 1.5, z: float = 3.0) -> pd.DataFrame:
    """Выбросы в годовых изменениях показателя (%), чтобы не ловить «большие страны».

    method='iqr' — за пределами [Q1 − k·IQR, Q3 + k·IQR]; method='zscore' — |z| > z.
    Возвращает таблицу страна/год/значение/изменение/флаг.
    """
    df = panel[["country", "year", column]].dropna().sort_values(["country", "year"]).copy()
    df["pct_change"] = df.groupby("country", observed=True)[column].pct_change() * 100
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["pct_change"])
    x = df["pct_change"]
    if method == "iqr":
        q1, q3 = x.quantile(0.25), x.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - k * iqr, q3 + k * iqr
        df["is_outlier"] = (x < lower) | (x > upper)
        df.attrs["bounds"] = (float(lower), float(upper))
    elif method == "zscore":
        score = (x - x.mean()) / x.std(ddof=0)
        df["is_outlier"] = score.abs() > z
    else:
        raise ValueError("method должен быть 'iqr' или 'zscore'")
    return df


def outlier_summary(panel: pd.DataFrame, column: str = "co2") -> dict:
    """Краткая сводка выбросов по IQR и z-score для отчёта."""
    iqr = detect_outliers(panel, column, "iqr")
    zs = detect_outliers(panel, column, "zscore")
    flagged = iqr[iqr["is_outlier"]].copy()
    top = flagged.loc[flagged["pct_change"].abs().sort_values(ascending=False).index].head(10)
    return {
        "column": column,
        "n_changes": int(len(iqr)),
        "iqr_bounds_pct": [round(b, 2) for b in iqr.attrs["bounds"]],
        "n_outliers_iqr": int(iqr["is_outlier"].sum()),
        "n_outliers_zscore": int(zs["is_outlier"].sum()),
        "top_outliers": top[["country", "year", column, "pct_change"]].round(2).to_dict(orient="records"),
    }


def coverage_summary(panel: pd.DataFrame) -> dict:
    """Краткое описание набора данных для отчёта."""
    return {
        "rows": int(len(panel)), "columns": int(panel.shape[1]),
        "countries": int(panel["country"].nunique()),
        "years": [int(panel["year"].min()), int(panel["year"].max())],
        "memory_mb": round(float(panel.memory_usage(deep=True).sum()) / 1024 ** 2, 2),
        "missing_pct_total": round(float(panel.isna().mean().mean() * 100), 2),
    }


def kazakhstan_vs_peers(panel: pd.DataFrame, year: int = config.YEAR_MAX,
                        variables: list[str] | None = None) -> pd.DataFrame:
    """Таблица сравнения Казахстана со странами-аналогами за выбранный год."""
    variables = variables or ["co2", "co2_per_capita", "co2_per_gdp", "energy_per_capita",
                              "fossil_share_energy", "low_carbon_share_energy", "carbon_intensity_elec"]
    rows = []
    for group, members in config.PEER_GROUPS.items():
        sub = panel[(panel["year"] == year) & (panel["country"].isin(members))]
        for _, r in sub.iterrows():
            rows.append({"group": group, "country": r["country"], **{v: r.get(v) for v in variables}})
    out = pd.DataFrame(rows)
    # Ранг Казахстана внутри каждой группы по душевым выбросам.
    out["rank_co2_per_capita"] = out.groupby("group")["co2_per_capita"].rank(ascending=False).astype("Int64")
    return out.round(3)
