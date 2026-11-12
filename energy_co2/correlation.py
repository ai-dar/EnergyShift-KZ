"""Корреляционный анализ: структура энергобаланса, экономика и внешние факторы (цены, климат)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

DEFAULT_VARIABLES = [
    "co2", "co2_per_capita", "gdp", "gdp_per_capita", "population", "primary_energy_consumption",
    "energy_per_capita", "fossil_share_energy", "low_carbon_share_energy", "coal_share_energy",
    "carbon_intensity_elec", "oil_price", "temperature_anomaly",
]


def attach_factors(df: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Присоединить годовые внешние факторы (цена нефти, температура) к панели по году."""
    return df.merge(factors, on="year", how="left")


def correlation_matrix(df: pd.DataFrame, variables: list[str] | None = None, method: str = "pearson",
                       differenced: bool = False) -> pd.DataFrame:
    """Матрица корреляций для одной серии (страна × годы).

    `differenced=True` — корреляции первых разностей: убирает общий тренд и
    снижает риск ложной корреляции между растущими рядами.
    """
    variables = [v for v in (variables or DEFAULT_VARIABLES) if v in df.columns]
    data = df.sort_values("year")[variables].astype(float)
    if differenced:
        data = data.diff()
    data = data.dropna(axis=1, how="all")
    return data.corr(method=method).round(3)


def country_correlations(panel: pd.DataFrame, factors: pd.DataFrame, country: str = config.TARGET_COUNTRY,
                         variables: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Корреляции уровней и разностей для выбранной страны."""
    df = attach_factors(panel[panel["country"] == country], factors)
    return {"levels": correlation_matrix(df, variables), "differences": correlation_matrix(df, variables, differenced=True)}


def external_factor_table(df: pd.DataFrame, factors: pd.DataFrame, target: str = "co2",
                          external: tuple[str, ...] = ("oil_price", "temperature_anomaly", "gdp", "population"),
                          max_lag: int = 2) -> pd.DataFrame:
    """Корреляция прироста целевого показателя с внешними факторами при лагах 0..max_lag.

    Для цен и ВВП используются годовые изменения (%), для температуры — разности.
    Положительный лаг k означает: фактор года t−k против выбросов года t.
    """
    data = attach_factors(df, factors).sort_values("year").copy()
    y = data[target].pct_change() * 100
    rows = []
    for name in external:
        if name not in data.columns:
            continue
        x = data[name].diff() if name == "temperature_anomaly" else data[name].pct_change() * 100
        for lag in range(0, max_lag + 1):
            pair = pd.concat([y, x.shift(lag)], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
            if len(pair) < 5:
                continue
            r = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
            r_s = float(pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman"))
            rows.append({"factor": name, "lag": lag, "n": len(pair), "pearson": round(r, 3), "spearman": round(r_s, 3)})
    return pd.DataFrame(rows)


def latest_complete_year(panel: pd.DataFrame, columns: list[str], min_countries: int = 50) -> int:
    """Последний год, в котором все `columns` заполнены хотя бы для `min_countries` стран (ВВП в OWID отстаёт на 2 года)."""
    counts = panel.dropna(subset=columns).groupby("year")["country"].nunique()
    ok = counts[counts >= min_countries]
    return int(ok.index.max()) if not ok.empty else int(panel["year"].max())


def cross_section_correlations(panel: pd.DataFrame, year: int | None = None,
                               variables: list[str] | None = None, min_population: float = 1e6) -> pd.DataFrame:
    """Межстрановые корреляции за один год (страны с населением ≥ min_population)."""
    variables = [v for v in (variables or DEFAULT_VARIABLES) if v in panel.columns and v not in ("oil_price", "temperature_anomaly")]
    year = year or latest_complete_year(panel, ["co2_per_capita", "gdp_per_capita", "fossil_share_energy"])
    sub = panel[(panel["year"] == year) & (panel["population"] >= min_population)][variables].astype(float)
    out = sub.corr(method="spearman").round(3)
    out.attrs["year"] = year
    return out


def energy_mix_vs_emissions(panel: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Связь доли ископаемых источников и углеродоёмкости с душевыми выбросами (для отчёта)."""
    year = year or latest_complete_year(panel, ["co2_per_capita", "gdp_per_capita", "fossil_share_energy"])
    sub = panel[(panel["year"] == year)].dropna(subset=["fossil_share_energy", "co2_per_capita"])
    rows = []
    for col in ("fossil_share_energy", "coal_share_energy", "low_carbon_share_energy", "energy_per_capita", "gdp_per_capita", "carbon_intensity_elec"):
        if col in sub:
            pair = sub[[col, "co2_per_capita"]].dropna()
            rows.append({"variable": col, "n_countries": len(pair),
                         "pearson": round(float(pair[col].corr(pair["co2_per_capita"])), 3),
                         "spearman": round(float(pair[col].corr(pair["co2_per_capita"], method="spearman")), 3)})
    out = pd.DataFrame(rows)
    out.insert(0, "year", year)
    return out
