"""Шаги проекта. Каждая функция — самостоятельный шаг, который вызывается из меню, ноутбука или дашборда.

Результаты сохраняются в `outputs/results` (Parquet/CSV/JSON), графики — в `outputs/figures`,
база данных — в `data/energy_co2.db`.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from . import benchmark, cleaning, config, correlation, database, eda, forecasting, io_utils, metrics, timeseries
from . import visualization as viz

KEY_VARIABLES = ["co2", "co2_per_capita", "primary_energy_consumption", "energy_per_capita",
                 "fossil_share_energy", "low_carbon_share_energy", "gdp", "population", "carbon_intensity_elec"]


def _log(message: str) -> None:
    print(f"  · {message}")


# 1. Данные ---------------------------------------------------------------------

def step_download(force: bool = False) -> dict[str, str]:
    """Скачать исходные данные (если их ещё нет) и показать размеры файлов."""
    paths = io_utils.download_sources(force=force)
    info = {name: f"{io_utils.file_size_mb(p)} МБ" for name, p in paths.items()}
    for name, size in info.items():
        _log(f"{name}: {size}")
    return info


def step_clean(chunksize: int = 5_000) -> dict:
    """Очистка панели, месячных данных, внешних факторов; длинный формат чанками; сохранение в Parquet."""
    config.ensure_dirs()
    t0 = time.perf_counter()
    panel = cleaning.build_panel()
    monthly = cleaning.clean_monthly()
    factors = cleaning.load_external_factors()
    countries = cleaning.country_metadata(monthly, panel)
    paths = cleaning.save_processed(panel, monthly, factors, countries)
    _log(f"панель: {panel.shape[0]} строк × {panel.shape[1]} колонок, {panel['country'].nunique()} стран")
    _log(f"месячные данные: {monthly.shape[0]} строк, {monthly['country'].nunique()} стран")
    _, long_summary = cleaning.build_long_format(chunksize=chunksize)
    _log(f"длинный формат: {long_summary['rows']:,} строк, {long_summary['memory_mb']} МБ в памяти, "
         f"{long_summary['parquet_mb']} МБ в Parquet")
    summary = {
        "panel": eda.coverage_summary(panel),
        "monthly": {"rows": int(len(monthly)), "countries": int(monthly["country"].nunique()),
                    "start": str(monthly["date"].min().date()), "end": str(monthly["date"].max().date())},
        "long_format": long_summary,
        "processed_files": {k: str(v) for k, v in paths.items()},
        "seconds": round(time.perf_counter() - t0, 1),
    }
    io_utils.save_json(summary, config.RESULTS_DIR / "clean_summary.json")
    return summary


# 2. EDA ---------------------------------------------------------------------------

def step_eda() -> dict:
    """Описательная статистика, пропуски, выбросы, проверка временных индексов."""
    panel = cleaning.load_processed("panel")
    monthly = cleaning.load_processed("monthly")
    describe = eda.describe_panel(panel, KEY_VARIABLES)
    missing_cols = eda.missing_report(panel, "column")
    missing_years = eda.missing_report(panel, "year")
    index_check = eda.check_time_index(panel)
    monthly_check = eda.check_monthly_index(monthly)
    outliers = eda.outlier_summary(panel, "co2")
    peers = eda.kazakhstan_vs_peers(panel)
    io_utils.save_dataframe(describe.reset_index().rename(columns={"index": "variable"}), "eda_describe")
    io_utils.save_dataframe(missing_cols, "eda_missing_by_column")
    io_utils.save_dataframe(missing_years, "eda_missing_by_year")
    io_utils.save_dataframe(index_check, "eda_time_index_check")
    io_utils.save_dataframe(monthly_check, "eda_monthly_index_check")
    io_utils.save_dataframe(peers, "kazakhstan_vs_peers")
    io_utils.save_json(outliers, config.RESULTS_DIR / "eda_outliers_co2.json")
    viz.save_mpl(viz.plot_missing_mpl(missing_years, KEY_VARIABLES), "eda_missing_by_year")
    summary = {
        "coverage": eda.coverage_summary(panel),
        "irregular_annual_series": int((~index_check["regular"]).sum()),
        "annual_series_with_gaps": int((index_check["n_gaps"] > 0).sum()),
        "monthly_series_with_gaps": int((monthly_check["n_gaps"] > 0).sum()),
        "monthly_series_full": int((monthly_check["n_obs"] == monthly_check["n_expected"]).sum()),
        "outliers": {k: v for k, v in outliers.items() if k != "top_outliers"},
        "top_outliers": outliers["top_outliers"][:5],
        "most_missing": missing_cols.head(5).to_dict(orient="records"),
    }
    _log(f"стран: {summary['coverage']['countries']}, пропусков в среднем: {summary['coverage']['missing_pct_total']}%")
    _log(f"нерегулярных годовых рядов: {summary['irregular_annual_series']}, выбросов (IQR): {outliers['n_outliers_iqr']}")
    io_utils.save_json(summary, config.RESULTS_DIR / "eda_summary.json")
    return summary


# 3. Временные ряды --------------------------------------------------------------

def step_timeseries(country: str = config.TARGET_COUNTRY) -> dict:
    """Resample, скользящие средние, STL, стационарность, ACF/PACF для годового и месячного рядов."""
    panel = cleaning.load_processed("panel")
    monthly = cleaning.load_processed("monthly")
    annual = timeseries.annual_series(panel, country, "co2")
    monthly_s = cleaning.monthly_series(monthly, country, "emissions_mtco2")

    five_year = timeseries.resample_series(annual, "5YS", "mean")
    quarterly = timeseries.resample_series(monthly_s, "QS", "sum")
    yearly_from_monthly = timeseries.resample_series(monthly_s, "YS", "sum")
    rolling_annual = timeseries.rolling_stats(annual, (3, 5, 10))
    rolling_monthly = timeseries.rolling_stats(monthly_s, (3, 6, 12))
    stl_monthly = timeseries.stl_decompose(monthly_s, period=12)
    stl_annual = timeseries.stl_decompose(annual, period=5)
    acf_annual = timeseries.acf_pacf(annual, 12)
    acf_monthly = timeseries.acf_pacf(monthly_s, 24)
    acf_monthly_diff = timeseries.acf_pacf(timeseries.difference(monthly_s, 1, 12), 24)

    summary = {
        "annual": timeseries.ts_summary(annual, period=5),
        "monthly": timeseries.ts_summary(monthly_s, period=12),
        "annual_5y_means": {str(k.year): round(v, 1) for k, v in five_year.items()},
        "monthly_yearly_sums": {str(k.year): round(v, 2) for k, v in yearly_from_monthly.items()},
        "monthly_quarterly_last": {str(k.date()): round(v, 2) for k, v in quarterly.tail(4).items()},
    }
    for name, df in (("ts_rolling_annual", rolling_annual), ("ts_rolling_monthly", rolling_monthly),
                     ("ts_stl_monthly", stl_monthly), ("ts_stl_annual", stl_annual),
                     ("ts_acf_annual", acf_annual), ("ts_acf_monthly", acf_monthly), ("ts_acf_monthly_diff", acf_monthly_diff)):
        io_utils.save_dataframe(df.reset_index(), name)
    viz.save_mpl(viz.plot_rolling_mpl(rolling_annual, f"{country}: выбросы CO₂ и скользящие средние (годовые данные)", "млн т"), "ts_rolling_annual")
    viz.save_mpl(viz.plot_rolling_mpl(rolling_monthly, f"{country}: выбросы электроэнергетики и скользящие средние (месячные данные)", "Мт CO₂"), "ts_rolling_monthly")
    viz.save_mpl(viz.plot_stl_mpl(stl_monthly, f"STL-декомпозиция: {country}, выбросы электроэнергетики по месяцам"), "ts_stl_monthly")
    viz.save_mpl(viz.plot_stl_mpl(stl_annual, f"STL-декомпозиция: {country}, годовые выбросы CO₂ (период 5)"), "ts_stl_annual")
    viz.save_mpl(viz.plot_acf_pacf_mpl(acf_annual, f"{country}, годовой CO₂"), "ts_acf_annual")
    viz.save_mpl(viz.plot_acf_pacf_mpl(acf_monthly, f"{country}, месячные выбросы"), "ts_acf_monthly")
    viz.save_mpl(viz.plot_acf_pacf_mpl(acf_monthly_diff, f"{country}, месячные выбросы после разностей (1, 12)"), "ts_acf_monthly_diff")
    _log(f"годовой ряд: {summary['annual']['level_verdict']}; месячный: сила сезонности {summary['monthly'].get('seasonal_strength')}")
    io_utils.save_json(summary, config.RESULTS_DIR / "timeseries_summary.json")
    return summary


# 4. Прогнозирование --------------------------------------------------------------

def _monthly_countries(monthly: pd.DataFrame, candidates: list[str]) -> list[str]:
    """Страны из списка, для которых есть полный месячный ряд."""
    check = eda.check_monthly_index(monthly)
    full = set(check.loc[check["n_obs"] == check["n_expected"], "country"])
    return [c for c in candidates if c in full]


def step_forecast(countries: list[str] | None = None, save_db: bool = True) -> dict:
    """Hold-out и скользящая CV для годовых и месячных рядов; метрики, анализ ошибок, графики, SQLite."""
    panel = cleaning.load_processed("panel")
    monthly = cleaning.load_processed("monthly")
    countries = countries or config.FORECAST_COUNTRIES
    t0 = time.perf_counter()

    # --- годовой CO₂ по странам-аналогам
    annual_series = {}
    for c in countries:
        try:
            annual_series[c] = timeseries.annual_series(panel, c, "co2")
        except ValueError as err:
            _log(f"{c}: {err}")
    annual_metrics, annual_forecasts = forecasting.forecast_battery(annual_series, config.ANNUAL_HOLDOUT, m=1)
    annual_cv = forecasting.rolling_cv(annual_series[config.TARGET_COUNTRY], config.ANNUAL_CV_SPLITS,
                                       config.ANNUAL_CV_TEST_SIZE, m=1, series_name=config.TARGET_COUNTRY)
    annual_cv_summary = forecasting.summarize_cv(annual_cv)
    annual_rank = forecasting.rank_models(annual_metrics)
    _log(f"годовой hold-out: {len(annual_series)} стран × {annual_metrics['model'].nunique()} моделей за {time.perf_counter() - t0:.1f} с")

    # --- месячные выбросы электроэнергетики
    t1 = time.perf_counter()
    monthly_countries = _monthly_countries(monthly, countries)
    monthly_series = {c: cleaning.monthly_series(monthly, c, "emissions_mtco2") for c in monthly_countries}
    monthly_metrics, monthly_forecasts = forecasting.forecast_battery(monthly_series, config.MONTHLY_HOLDOUT, m=config.MONTHLY_SEASON)
    monthly_cv = forecasting.rolling_cv(monthly_series[config.TARGET_COUNTRY], config.MONTHLY_CV_SPLITS,
                                        config.MONTHLY_CV_TEST_SIZE, m=config.MONTHLY_SEASON, series_name=config.TARGET_COUNTRY)
    monthly_cv_summary = forecasting.summarize_cv(monthly_cv)
    monthly_rank = forecasting.rank_models(monthly_metrics)
    _log(f"месячный hold-out: {len(monthly_series)} стран за {time.perf_counter() - t1:.1f} с")

    # --- прогноз в будущее для Казахстана лучшей (по CV) небазовой моделью и baseline
    kz_annual = annual_series[config.TARGET_COUNTRY]
    best_annual = forecasting.select_model(annual_metrics[annual_metrics["series"] == config.TARGET_COUNTRY], annual_cv_summary)
    future_annual = forecasting.future_forecast(kz_annual, best_annual, config.FUTURE_HORIZON, m=1)
    future_naive = forecasting.future_forecast(kz_annual, "Naive", config.FUTURE_HORIZON, m=1)
    kz_monthly = monthly_series[config.TARGET_COUNTRY]
    best_monthly = forecasting.select_model(monthly_metrics[monthly_metrics["series"] == config.TARGET_COUNTRY], monthly_cv_summary)
    future_monthly = forecasting.future_forecast(kz_monthly, best_monthly, 12, m=config.MONTHLY_SEASON)

    # --- сохранение результатов
    for name, df in (("forecast_annual_metrics", annual_metrics), ("forecast_annual_predictions", annual_forecasts),
                     ("forecast_annual_cv", annual_cv), ("forecast_annual_cv_summary", annual_cv_summary.reset_index()),
                     ("forecast_annual_rank", annual_rank.reset_index()),
                     ("forecast_monthly_metrics", monthly_metrics), ("forecast_monthly_predictions", monthly_forecasts),
                     ("forecast_monthly_cv", monthly_cv), ("forecast_monthly_cv_summary", monthly_cv_summary.reset_index()),
                     ("forecast_monthly_rank", monthly_rank.reset_index()),
                     ("forecast_future_annual", future_annual.assign(model=best_annual)),
                     ("forecast_future_annual_naive", future_naive.assign(model="Naive")),
                     ("forecast_future_monthly", future_monthly.assign(model=best_monthly))):
        io_utils.save_dataframe(df, name)
    db_counts = {}
    if save_db and config.DB_PATH.exists():
        db_counts["annual"] = database.save_forecast_results(annual_metrics, annual_forecasts, "co2", "annual")
        db_counts["monthly"] = database.save_forecast_results(monthly_metrics, monthly_forecasts, "co2", "monthly")

    # --- графики
    kz_metrics = annual_metrics[annual_metrics["series"] == config.TARGET_COUNTRY]
    kz_fc = annual_forecasts[annual_forecasts["series"] == config.TARGET_COUNTRY]
    viz.save_plotly(viz.plot_forecast_plotly(kz_annual, kz_fc, title=f"Казахстан: прогноз годовых выбросов CO₂ (hold-out {config.ANNUAL_HOLDOUT} лет) и прогноз до {config.YEAR_MAX + config.FUTURE_HORIZON} ({best_annual})",
                                             ylabel="млн т CO₂", future=future_annual), "forecast_annual_kazakhstan")
    kzm_fc = monthly_forecasts[monthly_forecasts["series"] == config.TARGET_COUNTRY]
    viz.save_plotly(viz.plot_forecast_plotly(kz_monthly, kzm_fc, title=f"Казахстан: прогноз месячных выбросов электроэнергетики (hold-out 12 мес.) и прогноз на 2026 ({best_monthly})",
                                             ylabel="Мт CO₂", future=future_monthly), "forecast_monthly_kazakhstan")
    viz.save_mpl(viz.plot_model_comparison_mpl(kz_metrics, "Казахстан, годовой CO₂: качество и время обучения"), "forecast_annual_model_comparison")
    viz.save_mpl(viz.plot_model_comparison_mpl(monthly_metrics[monthly_metrics["series"] == config.TARGET_COUNTRY], "Казахстан, месячные выбросы: качество и время обучения"), "forecast_monthly_model_comparison")
    viz.save_mpl(viz.plot_error_heatmap_mpl(kz_fc, "Казахстан, годовой CO₂: |ошибка| по годам горизонта, %"), "forecast_annual_errors_by_year")
    viz.save_mpl(viz.plot_error_heatmap_mpl(annual_forecasts, "Годовой CO₂: средняя |ошибка| по странам, %", by="series"), "forecast_annual_errors_by_country")
    viz.save_mpl(viz.plot_error_heatmap_mpl(kzm_fc, "Казахстан, месячные выбросы: |ошибка| по месяцам горизонта, %"), "forecast_monthly_errors_by_month")
    viz.save_mpl(viz.plot_series_errors_mpl(annual_rank, "Годовой CO₂: средний ранг моделей по странам"), "forecast_annual_rank")
    viz.save_mpl(viz.plot_series_errors_mpl(monthly_rank, "Месячные выбросы: средний ранг моделей по странам"), "forecast_monthly_rank")

    summary = {
        "annual": {
            "countries": list(annual_series), "holdout_years": config.ANNUAL_HOLDOUT,
            "kazakhstan_holdout": kz_metrics.drop(columns=["series", "error"]).round(4).to_dict(orient="records"),
            "kazakhstan_cv": annual_cv_summary.reset_index().to_dict(orient="records"),
            "rank_all_countries": annual_rank.reset_index().to_dict(orient="records"),
            "selected_model": best_annual,
            "future": future_annual.assign(date=future_annual["date"].dt.year).round(1).to_dict(orient="records"),
            "future_naive_value": round(float(future_naive["forecast"].iloc[0]), 1),
        },
        "monthly": {
            "countries": monthly_countries, "holdout_months": config.MONTHLY_HOLDOUT,
            "kazakhstan_holdout": monthly_metrics[monthly_metrics["series"] == config.TARGET_COUNTRY].drop(columns=["series", "error"]).round(4).to_dict(orient="records"),
            "kazakhstan_cv": monthly_cv_summary.reset_index().to_dict(orient="records"),
            "rank_all_countries": monthly_rank.reset_index().to_dict(orient="records"),
            "selected_model": best_monthly,
            "future_2026_total": round(float(future_monthly["forecast"].sum()), 2),
        },
        "db_saved": db_counts,
        "seconds": round(time.perf_counter() - t0, 1),
    }
    io_utils.save_json(summary, config.RESULTS_DIR / "forecast_summary.json")
    _log(f"выбранная модель (hold-out + CV): годовой — {best_annual}, месячный — {best_monthly}; всего {summary['seconds']} с")
    return summary


# 5. База данных ---------------------------------------------------------------------

def step_database() -> dict:
    """Создать SQLite, загрузить таблицы, выполнить все SQL-запросы, нарисовать ER-диаграмму."""
    panel = cleaning.load_processed("panel")
    monthly = cleaning.load_processed("monthly")
    factors = cleaning.load_processed("factors")
    countries = cleaning.load_processed("countries")
    counts = database.load_database(panel, monthly, factors, countries)
    # Если метрики прогноза уже посчитаны — заполняем таблицы результатов.
    metrics_path = config.RESULTS_DIR / "forecast_annual_metrics.parquet"
    if metrics_path.exists():
        for freq in ("annual", "monthly"):
            met = io_utils.read_parquet(config.RESULTS_DIR / f"forecast_{freq}_metrics.parquet")
            fc = io_utils.read_parquet(config.RESULTS_DIR / f"forecast_{freq}_predictions.parquet")
            database.save_forecast_results(met, fc, "co2", freq)
    results = database.run_all_queries()
    er_path = database.draw_er_diagram()
    with database.connect() as conn:
        counts = database.table_counts(conn)   # уже с метриками и прогнозами, если они были
    _log("таблицы: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    summary = {"tables": counts, "db_size_mb": io_utils.file_size_mb(config.DB_PATH),
               "queries": {name: {"rows": int(len(df)), "columns": list(df.columns)[:8]} for name, df in results.items()},
               "er_diagram": str(er_path)}
    _log(f"выполнено запросов: {len(results)}, база {summary['db_size_mb']} МБ")
    io_utils.save_json(summary, config.RESULTS_DIR / "database_summary.json")
    return summary


# 6. Бенчмарки ----------------------------------------------------------------------

def step_benchmark() -> dict:
    """CSV vs Parquet, оптимизация типов, Pandas vs SQL, чтение целиком vs чанками."""
    long_path = config.PROCESSED_DIR / "owid_long.parquet"
    long = io_utils.read_parquet(long_path)
    formats = benchmark.benchmark_formats(long)
    dtypes = benchmark.benchmark_dtypes(pd.read_csv(io_utils.raw_path("energy")))
    chunked = benchmark.chunked_vs_whole(io_utils.raw_path("co2"))
    panel = cleaning.load_processed("panel")
    pandas_sql = benchmark.benchmark_pandas_vs_sql(panel)
    io_utils.save_dataframe(formats, "benchmark_formats")
    io_utils.save_dataframe(dtypes.drop(columns=["dtypes"]), "benchmark_dtypes")
    io_utils.save_dataframe(chunked, "benchmark_chunked")
    io_utils.save_dataframe(pandas_sql, "benchmark_pandas_vs_sql")
    viz.save_mpl(viz.plot_benchmark_mpl(formats, pandas_sql), "benchmark")
    summary = {"formats": formats.to_dict(orient="records"), "dtypes": dtypes.drop(columns=["dtypes"]).to_dict(orient="records"),
               "chunked": chunked.to_dict(orient="records"), "pandas_vs_sql": pandas_sql.to_dict(orient="records")}
    _log(f"Parquet (snappy) меньше CSV в {1 / formats.loc[1, 'size_vs_csv']:.1f} раз, чтение быстрее в {formats.loc[0, 'read_s_mean'] / formats.loc[1, 'read_s_mean']:.1f} раз")
    io_utils.save_json(summary, config.RESULTS_DIR / "benchmark_summary.json")
    return summary


# 7. Корреляции ------------------------------------------------------------------------

def step_correlation(country: str = config.TARGET_COUNTRY) -> dict:
    """Корреляции уровней/разностей, внешние факторы, межстрановой срез, графики."""
    panel = cleaning.load_processed("panel")
    factors = cleaning.load_processed("factors")
    corr = correlation.country_correlations(panel, factors, country)
    ext_kz = correlation.external_factor_table(panel[panel["country"] == country], factors)
    world = cleaning.world_annual()
    ext_world = correlation.external_factor_table(world, factors)
    cross = correlation.cross_section_correlations(panel)
    mix = correlation.energy_mix_vs_emissions(panel)
    year = cross.attrs["year"]
    io_utils.save_dataframe(corr["levels"].reset_index().rename(columns={"index": "variable"}), "corr_kazakhstan_levels")
    io_utils.save_dataframe(corr["differences"].reset_index().rename(columns={"index": "variable"}), "corr_kazakhstan_differences")
    io_utils.save_dataframe(ext_kz.assign(series=country), "corr_external_factors_kazakhstan")
    io_utils.save_dataframe(ext_world.assign(series="World"), "corr_external_factors_world")
    io_utils.save_dataframe(cross.reset_index().rename(columns={"index": "variable"}), "corr_cross_section")
    io_utils.save_dataframe(mix, "corr_energy_mix_vs_emissions")
    viz.save_mpl(viz.plot_corr_heatmap(corr["levels"], f"{country}: корреляции уровней, {config.YEAR_MIN}–{config.YEAR_MAX}"), "corr_kazakhstan_levels")
    viz.save_mpl(viz.plot_corr_heatmap(corr["differences"], f"{country}: корреляции годовых разностей"), "corr_kazakhstan_differences")
    viz.save_mpl(viz.plot_corr_heatmap(cross, f"Межстрановые корреляции (Spearman), {year} г."), "corr_cross_section")
    viz.save_plotly(viz.plot_scatter_cross_section(panel, year), "scatter_gdp_co2")
    summary = {
        "country": country, "cross_section_year": year,
        "co2_levels": corr["levels"].loc["co2"].round(3).to_dict(),
        "co2_differences": corr["differences"].loc["co2"].round(3).to_dict(),
        "external_kazakhstan": ext_kz.to_dict(orient="records"),
        "external_world": ext_world.to_dict(orient="records"),
        "energy_mix_vs_emissions": mix.to_dict(orient="records"),
    }
    io_utils.save_json(summary, config.RESULTS_DIR / "correlation_summary.json")
    _log(f"корреляция приростов CO₂ Казахстана с ВВП (лаг 0): {ext_kz.loc[(ext_kz.factor == 'gdp') & (ext_kz.lag == 0), 'pearson'].iloc[0]}")
    return summary


# 8. Основные графики ---------------------------------------------------------------------

def step_figures() -> dict[str, str]:
    """Энергобаланс, сравнение с аналогами, энергопереход, интерактивная карта."""
    panel = cleaning.load_processed("panel")
    saved = {}
    saved["energy_mix_kazakhstan"] = str(viz.save_plotly(viz.plot_energy_mix_plotly(panel), "energy_mix_kazakhstan")["html"])
    saved["energy_mix_kazakhstan_share"] = str(viz.save_plotly(viz.plot_energy_mix_plotly(panel, share=True), "energy_mix_kazakhstan_share")["html"])
    saved["energy_mix_kazakhstan_png"] = str(viz.save_mpl(viz.plot_energy_mix_mpl(panel), "energy_mix_kazakhstan_mpl"))
    saved["co2_per_capita_peers"] = str(viz.save_plotly(viz.plot_country_lines(panel, config.PEER_COUNTRIES, "co2_per_capita"), "co2_per_capita_peers")["html"])
    saved["co2_per_capita_peer_groups_png"] = str(viz.save_mpl(viz.plot_peer_groups_mpl(panel, "co2_per_capita"), "co2_per_capita_peer_groups"))
    saved["energy_per_capita_peer_groups_png"] = str(viz.save_mpl(viz.plot_peer_groups_mpl(panel, "energy_per_capita"), "energy_per_capita_peer_groups"))
    saved["energy_transition_png"] = str(viz.save_mpl(viz.plot_transition_mpl(panel, config.PEER_GROUPS["Центральная Азия и СНГ"] + ["China", "Poland", "Norway"]), "energy_transition"))
    saved["map_co2_per_capita"] = str(viz.save_plotly(viz.plot_choropleth(panel, "co2_per_capita"), "map_co2_per_capita")["html"])
    saved["map_fossil_share"] = str(viz.save_plotly(viz.plot_choropleth(panel, "fossil_share_energy", title="Доля ископаемых источников в энергопотреблении, % (ползунок — год)"), "map_fossil_share", png=False)["html"])
    _log(f"сохранено графиков: {len(saved)}")
    return saved


# 9. Всё сразу ---------------------------------------------------------------------------

STEPS = [
    ("Загрузка данных", step_download),
    ("Очистка и Parquet", step_clean),
    ("EDA", step_eda),
    ("Временные ряды", step_timeseries),
    ("База данных и SQL", step_database),
    ("Прогнозирование", step_forecast),
    ("Бенчмарки", step_benchmark),
    ("Корреляции", step_correlation),
    ("Графики", step_figures),
]


def run_all() -> dict[str, float]:
    """Выполнить все шаги по порядку; вернуть время каждого шага."""
    timings: dict[str, float] = {}
    for title, step in STEPS:
        print(f"\n=== {title} ===")
        t0 = time.perf_counter()
        step()
        timings[title] = round(time.perf_counter() - t0, 1)
        print(f"  готово за {timings[title]} с")
    # После прогноза перезаписываем SQL-результаты, зависящие от model_metrics.
    database.run_all_queries()
    io_utils.save_json(timings, config.RESULTS_DIR / "pipeline_timings.json")
    return timings
