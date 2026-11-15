"""Streamlit-дашборд: фильтры (период, регион/страна, серия) и прогноз выбросов CO₂.

Запуск: streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from energy_co2 import cleaning, config, database, forecasting, io_utils, timeseries  # noqa: E402
from energy_co2 import visualization as viz  # noqa: E402

st.set_page_config(page_title="EnergyShift KZ", page_icon="🌍", layout="wide")


# --- Данные (кэшируются) ------------------------------------------------------------

@st.cache_data(show_spinner="Загрузка панели данных…")
def load_panel() -> pd.DataFrame:
    return cleaning.load_processed("panel")


@st.cache_data(show_spinner="Загрузка месячных данных…")
def load_monthly() -> pd.DataFrame:
    return cleaning.load_processed("monthly")


@st.cache_data
def load_countries() -> pd.DataFrame:
    return cleaning.load_processed("countries")


@st.cache_data
def load_result(name: str) -> pd.DataFrame | None:
    path = config.RESULTS_DIR / f"{name}.parquet"
    return io_utils.read_parquet(path) if path.exists() else None


def require_processed() -> bool:
    if not (config.PROCESSED_DIR / "panel_annual.parquet").exists():
        st.error("Нет обработанных данных. Выполните в консоли `python main.py --step 2` (или `python main.py --all`).")
        return False
    return True


# --- Боковая панель: фильтры ------------------------------------------------------------

def sidebar_filters(panel: pd.DataFrame, countries_meta: pd.DataFrame) -> dict:
    st.sidebar.title("Фильтры")
    years = st.sidebar.slider("Период (годы)", int(panel["year"].min()), int(panel["year"].max()),
                              (2000, int(panel["year"].max())))
    continents = ["Все"] + sorted(countries_meta["continent"].dropna().unique())
    continent = st.sidebar.selectbox("Регион (континент)", continents)
    group = st.sidebar.selectbox("Группа стран-аналогов", ["— своя выборка —"] + list(config.PEER_GROUPS))
    available = countries_meta if continent == "Все" else countries_meta[countries_meta["continent"] == continent]
    options = sorted(available["country"])
    default = config.PEER_GROUPS[group] if group != "— своя выборка —" else [config.TARGET_COUNTRY, "Russia", "Uzbekistan", "China", "Norway"]
    default = [c for c in default if c in options] or options[:5]
    selected = st.sidebar.multiselect("Страны", options, default=default)
    series_options = ["co2", "co2_per_capita", "co2_per_gdp", "primary_energy_consumption", "energy_per_capita",
                      "fossil_share_energy", "low_carbon_share_energy", "renewables_share_energy", "carbon_intensity_elec"]
    series = st.sidebar.selectbox("Серия (показатель)", series_options, format_func=viz.label)
    st.sidebar.caption("Данные: Our World in Data (Energy, CO₂), Ember (месячная генерация).")
    return {"years": years, "continent": continent, "countries": selected, "series": series}


# --- Вкладки ---------------------------------------------------------------------------

def tab_overview(panel: pd.DataFrame, f: dict) -> None:
    year = f["years"][1]
    kz = panel[(panel["country"] == config.TARGET_COUNTRY) & (panel["year"] == year)]
    if kz.empty:
        st.warning("Нет данных Казахстана за выбранный год")
        return
    row = kz.iloc[0]
    world_year = panel[panel["year"] == year]
    rank = int((world_year["co2_per_capita"] > row["co2_per_capita"]).sum() + 1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"CO₂ Казахстана, {year}", f"{row['co2']:.0f} млн т")
    c2.metric("CO₂ на душу", f"{row['co2_per_capita']:.1f} т/чел", help=f"{rank}-е место из {world_year['co2_per_capita'].notna().sum()} стран")
    c3.metric("Доля ископаемых источников", f"{row['fossil_share_energy']:.1f} %" if pd.notna(row["fossil_share_energy"]) else "—")
    c4.metric("Доля низкоуглеродных", f"{row['low_carbon_share_energy']:.1f} %" if pd.notna(row["low_carbon_share_energy"]) else "—")
    share = st.toggle("Показать доли, %", value=False)
    sub = panel[panel["year"].between(*f["years"])]
    st.plotly_chart(viz.plot_energy_mix_plotly(sub, config.TARGET_COUNTRY, share=share), width="stretch")
    st.plotly_chart(viz.plot_country_lines(sub, f["countries"] or [config.TARGET_COUNTRY], f["series"]), width="stretch")


def tab_compare(panel: pd.DataFrame, f: dict) -> None:
    sub = panel[panel["year"].between(*f["years"])]
    year = f["years"][1]
    col1, col2 = st.columns([3, 2])
    with col1:
        years = list(range(f["years"][0], f["years"][1] + 1, max(1, (f["years"][1] - f["years"][0]) // 12 or 1))) + [year]
        st.plotly_chart(viz.plot_choropleth(sub, f["series"], years=sorted(set(years))), width="stretch")
    with col2:
        table = sub[(sub["year"] == year) & (sub["country"].isin(f["countries"]))]
        cols = ["country", "co2", "co2_per_capita", "fossil_share_energy", "low_carbon_share_energy", "energy_per_capita"]
        st.markdown(f"**Страны-аналоги, {year} г.**")
        st.dataframe(table[cols].set_index("country").round(2).rename(columns=viz.label), width="stretch")
        peers = load_result("kazakhstan_vs_peers")
        if peers is not None:
            st.markdown("**Ранг Казахстана по CO₂ на душу внутри групп (2024)**")
            st.dataframe(peers[peers["country"] == config.TARGET_COUNTRY][["group", "rank_co2_per_capita"]].set_index("group"), width="stretch")
    st.plotly_chart(viz.plot_scatter_cross_section(panel, min(year, 2022)), width="stretch")


def tab_forecast(panel: pd.DataFrame, monthly: pd.DataFrame, f: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    freq = c1.radio("Частота", ["Годовые данные (OWID)", "Месячные данные (Ember)"], horizontal=False)
    is_monthly = freq.startswith("Месячные")
    available = sorted(monthly["country"].unique()) if is_monthly else sorted(panel["country"].unique())
    default_c = config.TARGET_COUNTRY if config.TARGET_COUNTRY in available else available[0]
    country = c2.selectbox("Страна", available, index=available.index(default_c))
    all_models = list(forecasting.MODEL_REGISTRY)
    models = c3.multiselect("Модели", all_models, default=["Naive", "Seasonal naive", "ETS", "ARIMA", "Lag LR"] if is_monthly else ["Naive", "Drift", "Linear trend", "ETS", "ARIMA", "Lag LR"])
    horizon = c4.slider("Горизонт прогноза в будущее", 1, 24 if is_monthly else 10, 12 if is_monthly else config.FUTURE_HORIZON)
    if not models:
        st.info("Выберите хотя бы одну модель")
        return
    try:
        if is_monthly:
            series = cleaning.monthly_series(monthly, country, "emissions_mtco2")
            m, h = config.MONTHLY_SEASON, config.MONTHLY_HOLDOUT
            ylabel = "Мт CO₂ (электроэнергетика)"
        else:
            series = timeseries.annual_series(panel, country, "co2")
            m, h = 1, config.ANNUAL_HOLDOUT
            ylabel = "млн т CO₂"
        with st.spinner("Обучение моделей…"):
            metrics, forecasts = forecasting.evaluate_holdout(series, h, m, models, series_name=country)
            scored = metrics.dropna(subset=["MASE"])
            best = scored.loc[~scored["is_baseline"]].sort_values("MASE")["model"].iloc[0] if (~scored["is_baseline"]).any() else scored.sort_values("MASE")["model"].iloc[0]
            future = forecasting.future_forecast(series, best, horizon, m)
    except ValueError as err:
        st.error(f"Не удалось построить прогноз: {err}")
        return
    st.plotly_chart(viz.plot_forecast_plotly(series, forecasts, models, title=f"{country}: hold-out {h} периодов и прогноз ({best})", ylabel=ylabel, future=future), width="stretch")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("**Метрики на hold-out** (MASE < 1 — лучше наивного in-sample)")
        st.dataframe(metrics[["model", "MAE", "RMSE", "MAPE", "sMAPE", "MASE", "train_time_s"]].set_index("model").round(3), width="stretch")
    with col2:
        st.markdown(f"**Прогноз в будущее: {best}**")
        st.caption("Модель — лучшая небазовая по MASE на hold-out среди выбранных; интервал ±1.96·σ·√k.")
        show = future.copy()
        show["date"] = show["date"].dt.strftime("%Y-%m" if is_monthly else "%Y")
        st.dataframe(show.set_index("date").round(2), width="stretch")
        if st.button("Сохранить прогноз в Parquet и SQLite"):
            name = f"dashboard_forecast_{country.replace(' ', '_')}_{'monthly' if is_monthly else 'annual'}"
            paths = io_utils.save_dataframe(future.assign(country=country, model=best), name, formats=("parquet", "csv"))
            msg = f"Сохранено: {paths['parquet'].name}"
            if config.DB_PATH.exists():
                counts = database.save_forecast_results(metrics, forecasts, "co2", "monthly" if is_monthly else "annual")
                msg += f"; в SQLite записано строк: {counts}"
            st.success(msg)


def tab_sql() -> None:
    if not config.DB_PATH.exists():
        st.error("База данных не создана. Выполните `python main.py --step 5`.")
        return
    queries = database.list_queries()
    titles = [q["title"] for q in queries]
    choice = st.selectbox("Запрос", range(len(queries)), format_func=lambda i: f"{i + 1}. {titles[i]}")
    q = queries[choice]
    with st.expander("Текст SQL", expanded=False):
        st.code(q["sql"], language="sql")
    custom = st.text_area("Или введите свой SQL (только SELECT)", height=90, placeholder="SELECT name, continent FROM countries LIMIT 10")
    sql = custom.strip() or q["sql"]
    if not sql.lstrip().lower().startswith(("select", "with", "--")):
        st.warning("Разрешены только запросы на чтение (SELECT / WITH).")
        return
    try:
        df = database.run_query(sql)
    except Exception as err:  # pandas.errors.DatabaseError / sqlite3.Error
        st.error(f"Ошибка SQL: {err}")
        return
    st.dataframe(df, width="stretch", height=420)
    st.download_button("Скачать CSV", df.to_csv(index=False).encode("utf-8"), f"{q['name']}.csv", "text/csv")


def tab_results() -> None:
    st.markdown("### Сравнение подходов")
    for name, title in (("benchmark_formats", "CSV vs Parquet"), ("benchmark_dtypes", "Оптимизация типов данных"),
                        ("benchmark_chunked", "Чтение целиком vs чанками"), ("benchmark_pandas_vs_sql", "Pandas vs SQLite")):
        df = load_result(name)
        if df is not None:
            st.markdown(f"**{title}**")
            st.dataframe(df, width="stretch")
    st.markdown("### Рейтинг моделей по странам (hold-out)")
    for name, title in (("forecast_annual_rank", "Годовой CO₂ (19 стран)"), ("forecast_monthly_rank", "Месячные выбросы электроэнергетики")):
        df = load_result(name)
        if df is not None:
            st.markdown(f"**{title}**")
            st.dataframe(df.set_index("model"), width="stretch")
    st.markdown("### Корреляции приростов CO₂ с внешними факторами")
    for name in ("corr_external_factors_kazakhstan", "corr_external_factors_world"):
        df = load_result(name)
        if df is not None:
            st.dataframe(df, width="stretch")


def main() -> None:
    st.title("🌍 EnergyShift KZ")
    st.caption("Global Energy Mix and CO₂ Emissions · итоговый проект по Programming for Data Analysis and Database · Aidar, Daniyal, Nurzhan (AAI-2604)")
    if not require_processed():
        return
    panel, monthly, countries_meta = load_panel(), load_monthly(), load_countries()
    f = sidebar_filters(panel, countries_meta)
    tabs = st.tabs(["Обзор", "Сравнение стран и карта", "Прогноз", "SQL", "Результаты и бенчмарки"])
    with tabs[0]:
        tab_overview(panel, f)
    with tabs[1]:
        tab_compare(panel, f)
    with tabs[2]:
        tab_forecast(panel, monthly, f)
    with tabs[3]:
        tab_sql()
    with tabs[4]:
        tab_results()


main()
