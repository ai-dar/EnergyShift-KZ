"""Очистка панельных данных OWID/Ember и построение аналитических таблиц."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config, io_utils

KEY_COLUMNS = ["country", "iso_code", "year"]


# --- Чтение исходных данных -----------------------------------------------------

def load_raw(name: str, usecols: list[str] | None = None) -> pd.DataFrame:
    """Прочитать исходный CSV по имени источника (при отсутствии — скачать).

    Отсутствие файла после попытки загрузки приводит к `FileNotFoundError`
    с понятным сообщением — его перехватывает консольное меню.
    """
    path = io_utils.raw_path(name)
    if not path.exists():
        io_utils.download_sources(names=[name])
    if not path.exists():
        raise FileNotFoundError(f"Файл данных не найден: {path}. Скачайте его: {config.DATA_SOURCES[name]['url']}")
    return pd.read_csv(path, usecols=usecols)


# --- Панельная очистка ----------------------------------------------------------

def drop_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """Оставить только страны: у агрегатов (World, Asia, OECD…) нет ISO-кода."""
    mask = df["iso_code"].notna() & (df["iso_code"].astype(str).str.len() == 3)
    return df.loc[mask].copy()


def restrict_years(df: pd.DataFrame, year_min: int = config.YEAR_MIN, year_max: int = config.YEAR_MAX) -> pd.DataFrame:
    """Ограничить период анализа."""
    return df.loc[df["year"].between(year_min, year_max)].copy()


def select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Выбрать ключевые колонки + те из `columns`, что есть в таблице."""
    present = [c for c in columns if c in df.columns]
    return df[KEY_COLUMNS + present].copy()


def fill_gaps(df: pd.DataFrame, columns: list[str], group: str = "country", limit: int = 2) -> pd.DataFrame:
    """Заполнить короткие пропуски внутри страны линейной интерполяцией (только внутри ряда).

    Пропуски длиннее `limit` и на краях ряда не заполняются — так мы не выдумываем данные.
    """
    out = df.sort_values([group, "year"]).copy()
    present = [c for c in columns if c in out.columns]
    out[present] = (
        out.groupby(group, observed=True)[present]
        .transform(lambda s: s.interpolate(limit=limit, limit_area="inside"))
    )
    return out


def drop_sparse_countries(df: pd.DataFrame, required: list[str], min_years: int = 20) -> pd.DataFrame:
    """Убрать страны, у которых меньше `min_years` лет с заполненными обязательными колонками."""
    present = [c for c in required if c in df.columns]
    complete = df.dropna(subset=present)
    counts = complete.groupby("country", observed=True)["year"].nunique()
    keep = counts[counts >= min_years].index
    return df[df["country"].isin(keep)].copy()


def add_derived_variables(df: pd.DataFrame) -> pd.DataFrame:
    """Нормализация на душу населения и производные показатели.

    co2_per_capita_calc — т CO₂/чел (co2 в млн т, население в чел.);
    energy_per_capita_calc — кВт·ч/чел (энергия в ТВт·ч);
    co2_per_energy — т CO₂ на МВт·ч первичной энергии;
    fossil_consumption / low_carbon_consumption — суммы по группам источников, ТВт·ч.
    """
    out = df.copy()
    pop = out["population"].where(out["population"] > 0)
    if "co2" in out:
        out["co2_per_capita_calc"] = out["co2"] * 1e6 / pop
    if "primary_energy_consumption" in out:
        out["energy_per_capita_calc"] = out["primary_energy_consumption"] * 1e9 / pop
        energy = out["primary_energy_consumption"].where(out["primary_energy_consumption"] > 0)
        if "co2" in out:
            out["co2_per_energy"] = out["co2"] * 1e6 / (energy * 1e6)   # т CO₂ / МВт·ч
    if "gdp" in out:
        out["gdp_per_capita"] = out["gdp"] / pop
    fossil_cols = [config.ENERGY_SOURCES[s]["column"] for s in config.FOSSIL_SOURCES if config.ENERGY_SOURCES[s]["column"] in out]
    low_cols = [config.ENERGY_SOURCES[s]["column"] for s in config.LOW_CARBON_SOURCES if config.ENERGY_SOURCES[s]["column"] in out]
    if fossil_cols:
        out["fossil_consumption"] = out[fossil_cols].sum(axis=1, min_count=1)
    if low_cols:
        out["low_carbon_consumption"] = out[low_cols].sum(axis=1, min_count=1)
    out["decade"] = (out["year"] // 10 * 10).astype(int)
    return out


def build_panel(energy: pd.DataFrame | None = None, co2: pd.DataFrame | None = None,
                year_min: int = config.YEAR_MIN, year_max: int = config.YEAR_MAX) -> pd.DataFrame:
    """Собрать очищенную годовую панель «страна × год» из OWID energy и OWID co2.

    Шаги: выбор колонок → удаление агрегатов → период → объединение → интерполяция
    коротких пропусков → производные показатели → удаление стран с редкими данными.
    """
    energy = load_raw("energy") if energy is None else energy
    co2 = load_raw("co2") if co2 is None else co2
    e = restrict_years(drop_aggregates(select_columns(energy, config.ENERGY_COLUMNS)), year_min, year_max)
    c = restrict_years(drop_aggregates(select_columns(co2, config.CO2_COLUMNS)), year_min, year_max)
    panel = e.merge(c, on=KEY_COLUMNS, how="outer", validate="one_to_one")
    panel = panel.drop_duplicates(subset=KEY_COLUMNS).sort_values(["country", "year"]).reset_index(drop=True)
    numeric = [c for c in panel.columns if c not in KEY_COLUMNS]
    panel = fill_gaps(panel, numeric)
    panel = add_derived_variables(panel)
    panel = drop_sparse_countries(panel, required=["co2", "population"], min_years=20)
    return panel.reset_index(drop=True)


# --- Длинный формат (демонстрация чанков и Parquet) -------------------------------

def _to_long(chunk: pd.DataFrame) -> pd.DataFrame:
    """Перевести чанк широкой таблицы в длинный формат (country, year, variable, value)."""
    value_cols = [c for c in chunk.columns if c not in KEY_COLUMNS]
    long = chunk.melt(id_vars=KEY_COLUMNS, value_vars=value_cols, var_name="variable", value_name="value")
    return long.dropna(subset=["value"])


def build_long_format(chunksize: int = 5_000) -> tuple[pd.DataFrame, dict]:
    """Собрать длинную таблицу из обоих OWID-файлов чанками и сохранить в Parquet.

    Полученный набор содержит > 2 млн строк — на нём демонстрируется чанковая
    загрузка, оптимизация типов, Parquet и замер памяти.
    """
    frames, stats = [], []
    for name in ("energy", "co2"):
        df, st = io_utils.read_csv_chunked(io_utils.raw_path(name), chunksize=chunksize, transform=_to_long)
        df["source"] = name
        frames.append(df)
        stats.append(st)
    long = pd.concat(frames, ignore_index=True)
    long = io_utils.optimize_dtypes(long)
    path = io_utils.write_parquet(long, config.PROCESSED_DIR / "owid_long.parquet")
    summary = {
        "rows": int(len(long)),
        "memory_mb": io_utils.memory_usage_mb(long),
        "parquet_mb": io_utils.file_size_mb(path),
        "chunk_stats": stats,
    }
    return long, summary


# --- Месячные данные Ember ---------------------------------------------------------

EMBER_RENAME = {
    "Area": "country", "ISO 3 code": "iso_code", "Date": "date", "Area type": "area_type",
    "Electricity source": "source", "Generation (TWh)": "generation_twh",
    "Share of generation (%)": "share_pct", "Emissions (MtCO2e)": "emissions_mtco2",
    "Emissions intensity (gCO2e/kWh)": "intensity_gco2_kwh", "Continent": "continent",
    "Ember region": "region", "EU member": "eu", "OECD member": "oecd", "G20 member": "g20",
}


def clean_monthly(ember: pd.DataFrame | None = None, start: str = config.MONTHLY_START,
                  end: str = config.MONTHLY_END) -> pd.DataFrame:
    """Привести месячные данные Ember к аккуратной таблице стран.

    Оставляем только страны (не регионы), период `start`..`end`, переименовываем
    колонки и приводим дату к началу месяца.
    """
    ember = load_raw("ember_monthly") if ember is None else ember
    df = ember.rename(columns=EMBER_RENAME)
    df = df[df["area_type"] == "Country or economy"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
    keep = ["country", "iso_code", "date", "source", "generation_twh", "share_pct",
            "emissions_mtco2", "intensity_gco2_kwh", "continent", "region", "eu", "oecd", "g20"]
    df = df[keep].drop_duplicates(subset=["country", "date", "source"])
    return df.sort_values(["country", "source", "date"]).reset_index(drop=True)


def monthly_series(monthly: pd.DataFrame, country: str, value: str = "emissions_mtco2",
                   source: str = "Total generation") -> pd.Series:
    """Извлечь месячный ряд страны с регулярным индексом (freq='MS')."""
    sub = monthly[(monthly["country"] == country) & (monthly["source"] == source)]
    series = sub.set_index("date")[value].sort_index().astype(float)
    if series.empty:
        raise ValueError(f"Нет месячных данных для {country} / {source}")
    full_index = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    series = series.reindex(full_index).interpolate(limit=2, limit_area="inside")
    series.index.name = "date"
    series.name = value
    return series


def country_metadata(monthly: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Справочник стран: ISO, континент, регион и членство в объединениях (из Ember)."""
    meta = (monthly.groupby(["country", "iso_code"], as_index=False)
            .agg(continent=("continent", "first"), region=("region", "first"),
                 eu=("eu", "max"), oecd=("oecd", "max"), g20=("g20", "max")))
    all_countries = panel[["country", "iso_code"]].drop_duplicates()
    out = all_countries.merge(meta.drop(columns=["country"]), on="iso_code", how="left")
    # Континент для стран, которых нет в Ember, берём из справочника OWID.
    owid = load_raw("continents").rename(columns={"code": "iso_code", "owid_region": "continent_owid"})
    out = out.merge(owid[["iso_code", "continent_owid"]].drop_duplicates("iso_code"), on="iso_code", how="left")
    out["continent"] = out["continent"].fillna(out["continent_owid"]).fillna("Unknown")
    out["region"] = out["region"].fillna(out["continent"])
    out = out.drop(columns=["continent_owid"])
    for flag in ("eu", "oecd", "g20"):
        out[flag] = out[flag].fillna(False).astype(bool)
    return out.sort_values("country").reset_index(drop=True)


def world_annual(year_min: int = config.YEAR_MIN, year_max: int = config.YEAR_MAX) -> pd.DataFrame:
    """Мировые агрегаты OWID (строки `World`) по годам — для корреляций с глобальными факторами."""
    energy = load_raw("energy")
    co2 = load_raw("co2")
    e = energy[energy["country"] == "World"][["year"] + [c for c in config.ENERGY_COLUMNS if c in energy.columns]]
    c = co2[co2["country"] == "World"][["year"] + [c for c in config.CO2_COLUMNS if c in co2.columns]]
    world = e.merge(c, on="year", how="outer", suffixes=("", "_co2")).sort_values("year")
    world = world[world["year"].between(year_min, year_max)].reset_index(drop=True)
    world.insert(0, "country", "World")
    world.insert(1, "iso_code", "WLD")
    return add_derived_variables(world)


# --- Внешние факторы ---------------------------------------------------------------

def load_external_factors() -> pd.DataFrame:
    """Годовая таблица внешних факторов: цена нефти ($/баррель) и температурная аномалия (°C)."""
    oil = load_raw("oil_price")
    oil = oil[oil["entity"] == "World"][["year", "oil_price_crude_current_dollars_per_m3"]].copy()
    # OWID хранит цену за кубометр нефти; 1 баррель = 0.158987 м³
    oil["oil_price"] = oil["oil_price_crude_current_dollars_per_m3"] * 0.158987
    temp = load_raw("temperature")
    temp = temp[temp["entity"] == "World"][["year", "near_surface_temperature_anomaly"]]
    temp = temp.rename(columns={"near_surface_temperature_anomaly": "temperature_anomaly"})
    out = oil[["year", "oil_price"]].merge(temp, on="year", how="outer").sort_values("year")
    return out.reset_index(drop=True)


# --- Сохранение обработанных данных ------------------------------------------------

def save_processed(panel: pd.DataFrame, monthly: pd.DataFrame, factors: pd.DataFrame,
                   countries: pd.DataFrame) -> dict[str, Path]:
    """Сохранить обработанные таблицы в Parquet (`data/processed`)."""
    config.ensure_dirs()
    return {
        "panel": io_utils.write_parquet(panel, config.PROCESSED_DIR / "panel_annual.parquet"),
        "monthly": io_utils.write_parquet(monthly, config.PROCESSED_DIR / "electricity_monthly.parquet"),
        "factors": io_utils.write_parquet(factors, config.PROCESSED_DIR / "external_factors.parquet"),
        "countries": io_utils.write_parquet(countries, config.PROCESSED_DIR / "countries.parquet"),
    }


def load_processed(name: str) -> pd.DataFrame:
    """Прочитать обработанную таблицу (`panel`, `monthly`, `factors`, `countries`)."""
    files = {
        "panel": "panel_annual.parquet", "monthly": "electricity_monthly.parquet",
        "factors": "external_factors.parquet", "countries": "countries.parquet",
    }
    path = config.PROCESSED_DIR / files[name]
    if not path.exists():
        raise FileNotFoundError(f"Нет обработанных данных {path}. Сначала выполните шаг очистки (меню, пункт 2).")
    return io_utils.read_parquet(path)
