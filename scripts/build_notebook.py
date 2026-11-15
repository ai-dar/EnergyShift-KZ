"""Сборка Final_Project.ipynb из кода и текста (запуск: python scripts/build_notebook.py)."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
nb = nbf.v4.new_notebook()
cells: list = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(text: str) -> None:
    cells.append(nbf.v4.new_code_cell(text.strip()))


md("""
# EnergyShift KZ: Казахстан на карте мирового энергоперехода

**Тема 60:** Global Energy Mix and CO₂ Emissions — итоговый проект

**Дисциплина:** Programming for Data Analysis and Database · **Программа:** Applied Artificial Intelligence (магистратура)
**Команда:** Aidar, Daniyal, Nurzhan · **Группа:** AAI-2604 · **Кластер 10:** Forecasting & Open Data Analytics

**Цель.** Сравнить страны по структуре энергопотребления и выбросам CO₂, изучить энергетический переход, сопоставить
Казахстан со странами-аналогами и построить прогноз выбросов, честно сравнив модели с наивными baseline.

**Данные.** Our World in Data — *Energy* и *CO₂* (годовая панель «страна × год»), Ember — месячная генерация
электроэнергии и выбросы (сезонность), OWID — цены на нефть и температурная аномалия (внешние факторы).

Ноутбук — повествовательная версия проекта: он вызывает функции пакета `energy_co2/` (12 модулей),
а тяжёлые расчёты по всем странам берёт из `outputs/results/`, которые создаёт `python main.py --all`.
Консольное меню — `main.py`, дашборд — `streamlit run app.py`, 3D-фронтенд — `python web/server.py`.
""")

code("""
import json, sys, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.io as pio
from IPython.display import Image, Markdown, display

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.cwd()))
pd.set_option("display.width", 160); pd.set_option("display.max_columns", 24); pd.set_option("display.float_format", "{:,.3f}".format)
pio.renderers.default = "notebook_connected"

from energy_co2 import benchmark, cleaning, config, correlation, database, eda, forecasting, io_utils, metrics, pipeline, timeseries
from energy_co2 import visualization as viz

# После клонирования репозитория базы SQLite ещё нет (она в .gitignore) — создаём её из Parquet за пару секунд.
if not config.DB_PATH.exists():
    pipeline.step_database()

def load_json(name):
    return io_utils.load_json(config.RESULTS_DIR / f"{name}.json", default={})

def load_result(name):
    return io_utils.read_parquet(config.RESULTS_DIR / f"{name}.parquet")

print("Источники данных:")
display(pd.DataFrame([{"источник": k, "файл": v["file"], "описание": v["description"], "размер, МБ": io_utils.file_size_mb(config.RAW_DIR / v["file"])} for k, v in config.DATA_SOURCES.items()]).set_index("источник"))
""")

md("""
## 1. Загрузка и очистка панельных данных

Панель строится функцией `cleaning.build_panel()`: выбор колонок → удаление агрегатов (у `World`, `Asia`, `OECD`
нет ISO-кода) → период 1990–2024 → объединение energy + CO₂ по (country, iso_code, year) → линейная интерполяция
коротких пропусков *внутри* ряда (≤ 2 лет, края не заполняются) → производные показатели (нормализация на душу
населения, CO₂ на единицу энергии, суммы по группам источников) → удаление стран, у которых меньше 20 лет данных.
""")

code("""
energy_raw = cleaning.load_raw("energy")
co2_raw = cleaning.load_raw("co2")
print(f"OWID energy: {energy_raw.shape}, сущностей {energy_raw['country'].nunique()}, годы {energy_raw['year'].min()}–{energy_raw['year'].max()}")
print(f"OWID co2:    {co2_raw.shape}, сущностей {co2_raw['country'].nunique()}, годы {co2_raw['year'].min()}–{co2_raw['year'].max()}")
aggregates = sorted(energy_raw.loc[energy_raw['iso_code'].isna(), 'country'].unique())
print(f"Агрегатов без ISO-кода (удаляются): {len(aggregates)} — например {aggregates[:6]}")

panel = cleaning.build_panel(energy_raw, co2_raw)
print(f"\\nОчищенная панель: {panel.shape[0]} строк × {panel.shape[1]} колонок, стран {panel['country'].nunique()}, период {panel['year'].min()}–{panel['year'].max()}")
panel[panel['country'] == 'Kazakhstan'][['year', 'co2', 'co2_per_capita', 'co2_per_capita_calc', 'energy_per_capita', 'fossil_share_energy', 'low_carbon_share_energy', 'co2_per_energy']].tail(5)
""")

md("""
**Проверка нормализации на душу населения.** Колонка `co2_per_capita_calc` рассчитана нами как `co2 · 10⁶ / population`
и совпадает с `co2_per_capita` из OWID с точностью до округления — значит, единицы измерения поняты правильно
(CO₂ в млн т, энергия в ТВт·ч, душевые показатели в т/чел и кВт·ч/чел).
""")

code("""
monthly = cleaning.clean_monthly()
factors = cleaning.load_external_factors()
countries_meta = cleaning.country_metadata(monthly, panel)
print(f"Ember месячные: {monthly.shape[0]} строк, {monthly['country'].nunique()} стран, {monthly['date'].min().date()} – {monthly['date'].max().date()}")
print(f"Внешние факторы: {factors.dropna().shape[0]} лет с ценой нефти и температурной аномалией")
display(monthly[(monthly['country'] == 'Kazakhstan') & (monthly['source'] == 'Total generation')].tail(3))
display(factors.tail(3))
""")

md("""
### Чанковая загрузка, оптимизация типов и Parquet

Тема 60 входит в список исключений по объёму, но приёмы работы с большими данными всё равно демонстрируются:
оба файла OWID читаются чанками по 5 000 строк и переводятся в «длинный» формат (country, year, variable, value) —
получается **2,7 млн строк**. Типы оптимизируются (float64 → float32, строки → category), результат хранится в Parquet.
""")

code("""
summary_clean = load_json("clean_summary")
long_stats = summary_clean.get("long_format", {})
print(f"Длинный формат: {long_stats.get('rows', 0):,} строк, {long_stats.get('memory_mb')} МБ в памяти, {long_stats.get('parquet_mb')} МБ в Parquet")
display(pd.DataFrame(long_stats.get("chunk_stats", [])))
display(benchmark.benchmark_dtypes(energy_raw).drop(columns=["dtypes"]))
display(benchmark.chunked_vs_whole(io_utils.raw_path("co2")))
""")

md("""
## 2. EDA: описательная статистика, пропуски, выбросы, временные индексы
""")

code("""
key_vars = ["co2", "co2_per_capita", "primary_energy_consumption", "energy_per_capita", "fossil_share_energy", "low_carbon_share_energy", "gdp", "population", "carbon_intensity_elec"]
display(eda.describe_panel(panel, key_vars)[["count", "mean", "50%", "std", "min", "max", "missing_pct", "n_countries"]])
display(eda.missing_report(panel, "column").head(8))
display(Image(filename=str(config.FIG_DIR / "eda_missing_by_year.png"), width=900))
""")

md("""
Пропуски сосредоточены в детализации энергобаланса: OWID публикует потребление по источникам (данные Energy Institute)
только для ~80 крупных экономик, поэтому `*_consumption` и доли источников отсутствуют у 61 % строк панели.
Показатели выбросов (`co2`, `co2_per_capita`) и население заполнены почти полностью; ВВП отстаёт на два года.
""")

code("""
idx = eda.check_time_index(panel)
print(f"Годовых рядов: {len(idx)}; регулярных (шаг 1 год, без дубликатов): {idx['regular'].sum()}; с пропусками периодов: {(idx['n_gaps'] > 0).sum()}")
midx = eda.check_monthly_index(monthly)
print(f"Месячных рядов: {len(midx)}; полных (freq=MS без пропусков): {(midx['n_obs'] == midx['n_expected']).sum()}; с пропусками: {(midx['n_gaps'] > 0).sum()}")
display(midx[midx['country'].isin(['Kazakhstan', 'Russia', 'China'])])
""")

code("""
outliers = eda.outlier_summary(panel, "co2")
print(f"Годовых изменений CO₂: {outliers['n_changes']}; границы IQR: {outliers['iqr_bounds_pct']} %; выбросов по IQR: {outliers['n_outliers_iqr']}, по z-score: {outliers['n_outliers_zscore']}")
display(pd.DataFrame(outliers["top_outliers"]))
""")

md("""
Выбросы ищутся в **годовых изменениях** показателя, а не в уровнях — иначе «выбросами» оказались бы просто большие страны.
Экстремальные значения относятся к малым экономикам и особым событиям (Кувейт 1991 — восстановление после войны,
Экваториальная Гвинея — старт нефтедобычи). Это реальные события, а не ошибки данных, поэтому они не удаляются;
для устойчивости далее используются ранги и медианы.
""")

code("""
peers = eda.kazakhstan_vs_peers(panel, config.YEAR_MAX)
display(peers[peers["group"] == "Центральная Азия и СНГ"].set_index("country"))
display(peers[peers["country"] == "Kazakhstan"][["group", "co2_per_capita", "rank_co2_per_capita"]].set_index("group"))
""")

md("""
## 3. Анализ временных рядов

Годовой ряд выбросов CO₂ Казахстана (1990–2024) и месячный ряд выбросов электроэнергетики (Ember, 2018–2025).
Для каждого: передискретизация, скользящие средние, STL-декомпозиция, тесты стационарности ADF/KPSS, ACF/PACF.
""")

code("""
annual = timeseries.annual_series(panel, "Kazakhstan", "co2")
monthly_kz = cleaning.monthly_series(monthly, "Kazakhstan", "emissions_mtco2")
print("Пятилетние средние, млн т:", {k.year: round(v, 1) for k, v in timeseries.resample_series(annual, "5YS", "mean").items()})
print("Годовые суммы из месячных данных, Мт:", {k.year: round(v, 1) for k, v in timeseries.resample_series(monthly_kz, "YS", "sum").items()})
display(timeseries.rolling_stats(annual, (3, 5, 10)).tail(4))
display(Image(filename=str(config.FIG_DIR / "ts_rolling_annual.png"), width=900))
""")

code("""
stl_m = timeseries.stl_decompose(monthly_kz, period=12)
print(f"STL месячного ряда: сила сезонности {stl_m.attrs['seasonal_strength']:.3f}, сила тренда {stl_m.attrs['trend_strength']:.3f}")
display(Image(filename=str(config.FIG_DIR / "ts_stl_monthly.png"), width=900))
stl_a = timeseries.stl_decompose(annual, period=5)
print(f"STL годового ряда (период 5 — условный деловой цикл): сила «сезонности» {stl_a.attrs['seasonal_strength']:.3f}, сила тренда {stl_a.attrs['trend_strength']:.3f}")
""")

code("""
tests = pd.DataFrame({
    "годовой CO₂ (уровни)": timeseries.stationarity_tests(annual),
    "годовой CO₂ (разности)": timeseries.stationarity_tests(timeseries.difference(annual)),
    "месячные выбросы (уровни)": timeseries.stationarity_tests(monthly_kz),
    "месячные выбросы (разности 1 и 12)": timeseries.stationarity_tests(timeseries.difference(monthly_kz, 1, 12)),
}).T
display(tests[["n", "adf_stat", "adf_pvalue", "kpss_stat", "kpss_pvalue", "verdict"]])
display(Image(filename=str(config.FIG_DIR / "ts_acf_monthly.png"), width=900))
display(Image(filename=str(config.FIG_DIR / "ts_acf_monthly_diff.png"), width=900))
""")

md("""
**Выводы по рядам.** Годовой ряд нестационарен (ADF не отвергает единичный корень, KPSS отвергает стационарность) —
модели ARIMA строятся на первых разностях. Месячный ряд имеет выраженную сезонность (сила 0.94: зимний максимум
отопительного сезона, летний минимум) и восходящий тренд с 2023 г.; пик ACF на лаге 12 подтверждает годовой период,
после разностей (1, 12) ряд становится стационарным.
""")

md("""
## 4. Прогнозирование: baseline против моделей

Единый интерфейс `model(train, h, m)`; все оценки строго хронологические (`holdout_split`, `TimeSeriesSplit`).
*Baseline*: Naive, Seasonal naive (при m = 1 совпадает с Naive, поэтому для годовых данных добавлен Drift).
*Модели*: Linear trend, ETS (Holt с затуханием / Holt-Winters), ARIMA/SARIMA (выбор порядка по AIC),
Lag LR (гребневая регрессия на лагах + тренд), Lag GBM (градиентный бустинг на лагах приростов).
*Метрики*: MAE, RMSE, MAPE, sMAPE, MASE и время обучения.
""")

code("""
hold_metrics, hold_fc = forecasting.evaluate_holdout(annual, config.ANNUAL_HOLDOUT, m=1, series_name="Kazakhstan")
display(hold_metrics.drop(columns=["series", "error"]).set_index("model"))
cv = forecasting.rolling_cv(annual, config.ANNUAL_CV_SPLITS, config.ANNUAL_CV_TEST_SIZE, m=1, series_name="Kazakhstan")
print("Скользящая кросс-валидация TimeSeriesSplit (4 блока по 3 года), средние метрики:")
cv_summary = forecasting.summarize_cv(cv)
display(cv_summary)
selected = forecasting.select_model(hold_metrics, cv_summary)
print("Модель для прогноза в будущее (сумма рангов hold-out и CV, без baseline):", selected)
""")

code("""
future = forecasting.future_forecast(annual, selected, config.FUTURE_HORIZON, m=1)
viz.plot_forecast_plotly(annual, hold_fc, title=f"Казахстан: годовой CO₂ — hold-out {config.ANNUAL_HOLDOUT} лет и прогноз до {config.YEAR_MAX + config.FUTURE_HORIZON} ({selected})", ylabel="млн т CO₂", future=future).show()
display(Image(filename=str(config.FIG_DIR / "forecast_annual_model_comparison.png"), width=1000))
display(Image(filename=str(config.FIG_DIR / "forecast_annual_errors_by_year.png"), width=900))
""")

code("""
mh_metrics, mh_fc = forecasting.evaluate_holdout(monthly_kz, config.MONTHLY_HOLDOUT, m=config.MONTHLY_SEASON, series_name="Kazakhstan")
display(mh_metrics.drop(columns=["series", "error"]).set_index("model"))
future_m = forecasting.future_forecast(monthly_kz, load_json("forecast_summary").get("monthly", {}).get("selected_model", "ARIMA"), 12, m=12)
viz.plot_forecast_plotly(monthly_kz, mh_fc, title="Казахстан: месячные выбросы электроэнергетики — hold-out 12 мес. и прогноз на 2026", ylabel="Мт CO₂", future=future_m).show()
display(Image(filename=str(config.FIG_DIR / "forecast_monthly_errors_by_month.png"), width=900))
""")

md("""
### Анализ ошибок по сериям: 19 стран (годовые) и 16 стран (месячные)

Результаты «батареи» прогнозов (`pipeline.step_forecast`) загружаются из `outputs/results/`. Так как масштабы стран
различаются на порядки, модели сравниваются по **среднему рангу MASE** по странам, а не по средней ошибке.
""")

code("""
rank_a = load_result("forecast_annual_rank").set_index("model")
rank_m = load_result("forecast_monthly_rank").set_index("model")
display(pd.concat({"годовой CO₂": rank_a, "месячные выбросы": rank_m}, axis=1))
display(Image(filename=str(config.FIG_DIR / "forecast_annual_errors_by_country.png"), width=1100))
""")

md("""
**Выводы по прогнозу.**
* На **годовых** данных baseline трудно превзойти: выбросы Казахстана после 2017 г. вышли на плато, поэтому модели с
  трендом (Lag LR, Lag GBM, ETS), обученные на росте 2000–2016, систематически завышают прогноз. По 19 странам лучший
  средний ранг у Lag GBM и Naive; ARIMA и ETS выигрывают у Naive лишь в части стран. Это главный практический вывод:
  **для годовых национальных выбросов наивный прогноз — сильный ориентир, и любой «тренд» нужно сравнивать с ним**.
* На **месячных** данных сезонность делает Seasonal naive сильным baseline (MASE ≈ 1.2), а SARIMA, ETS (Holt-Winters)
  и Lag LR заметно точнее простого Naive (MASE 3.6) и чуть точнее Seasonal naive; SARIMA — самая точная, но в ~100 раз
  медленнее ETS.
* Время обучения: baseline — мгновенно, ETS/Lag LR — сотые доли секунды, Lag GBM — ~0.15 с, ARIMA с перебором порядков — 0.3–8 с.
""")

md("""
## 5. Корреляционный анализ с внешними факторами

Корреляции считаются двумя способами: по уровням (1990–2024) и по **годовым разностям/приростам** — второй способ
убирает общий тренд и защищает от ложных корреляций. Внешние факторы: мировая цена нефти, температурная аномалия, ВВП и население.
""")

code("""
corr = correlation.country_correlations(panel, factors, "Kazakhstan")
display(Image(filename=str(config.FIG_DIR / "corr_kazakhstan_levels.png"), width=800))
print("Корреляции разностей с CO₂ Казахстана:")
display(corr["differences"].loc["co2"].to_frame("r (разности)").join(corr["levels"].loc["co2"].to_frame("r (уровни)")))
ext = correlation.external_factor_table(panel[panel["country"] == "Kazakhstan"], factors)
display(ext.pivot(index="factor", columns="lag", values="pearson"))
world = cleaning.world_annual()
print("Мир: корреляция прироста CO₂ с внешними факторами (лаг 0..2):")
display(correlation.external_factor_table(world, factors).pivot(index="factor", columns="lag", values="pearson"))
""")

code("""
year_cs = correlation.latest_complete_year(panel, ["co2_per_capita", "gdp_per_capita", "fossil_share_energy"])
display(correlation.energy_mix_vs_emissions(panel, year_cs).set_index("variable"))
viz.plot_scatter_cross_section(panel, year_cs).show()
""")

md("""
**Выводы.** По уровням CO₂ Казахстана сильно коррелирует со всем, что растёт (ВВП 0.84, цена нефти 0.57, температура 0.66) —
классическая ложная корреляция трендов. По разностям остаётся только экономика: прирост ВВП (r ≈ 0.57 при лаге 0),
население и энергопотребление; цена нефти влияет слабо и с лагом в год (r ≈ 0.31), температура — не влияет.
Для мира в целом годовой прирост выбросов синхронен с изменением цены нефти (r ≈ 0.7 при лаге 0 — оба отражают деловой цикл).
Межстрановой срез: душевые выбросы определяются прежде всего энергопотреблением на душу (ρ = 0.90) и ВВП на душу (ρ = 0.65),
а не долей угля — углеродоёмкость и объём потребления действуют вместе.
""")

md("""
## 6. База данных SQLite и SQL-запросы

Схема из 7 таблиц (`sql/schema.sql`): справочник стран, годовые энергобаланс и выбросы, месячная электроэнергетика,
внешние факторы, метрики моделей и прогнозы. Все 12 запросов лежат в `sql/queries/` и используют JOIN, GROUP BY/HAVING,
подзапросы, CTE и оконные функции (RANK, LAG, SUM OVER, FIRST_VALUE, ROW_NUMBER); результаты загружаются в Pandas.
""")

code("""
with database.connect() as conn:
    display(pd.Series(database.table_counts(conn), name="строк").to_frame())
display(Image(filename=str(config.DOCS_DIR / "er_diagram.png"), width=1000))
""")

code("""
for q in database.list_queries():
    df = database.run_query(q["sql"])
    display(Markdown(f"**{q['name']}** — {q['title']} · строк: {len(df)}"))
    display(df.head(8))
""")

md("""
## 7. Сравнение подходов: CSV vs Parquet, Pandas vs SQL, модели vs baseline
""")

code("""
display(load_result("benchmark_formats").set_index("format"))
display(benchmark.benchmark_pandas_vs_sql(panel).pivot(index="task", columns="approach", values="mean_ms"))
display(Image(filename=str(config.FIG_DIR / "benchmark.png"), width=1000))
""")

md("""
**Выводы.** Parquet (snappy) в 18 раз компактнее CSV и читается в 2–3 раза быстрее при в 6 раз меньшем потреблении
памяти (category + float32). SQLite быстрее Pandas на выборках «топ-N с сортировкой» благодаря индексам, но проигрывает
на оконных вычислениях по всей таблице (LAG по 7 140 строкам): векторизованный `groupby().diff()` выполняется за ~2 мс
против ~14 мс в SQLite. Вывод: хранение и фильтрация — в SQL/Parquet, аналитика по всей таблице — в Pandas.
""")

md("""
## 8. Визуализации: энергобаланс, Казахстан и аналоги, интерактивная карта
""")

code("""
viz.plot_energy_mix_plotly(panel, "Kazakhstan", share=True).show()
viz.plot_country_lines(panel, config.PEER_GROUPS["Центральная Азия и СНГ"] + ["China", "Norway"], "co2_per_capita").show()
display(Image(filename=str(config.FIG_DIR / "energy_transition.png"), width=1000))
viz.plot_choropleth(panel, "co2_per_capita", years=list(range(1990, 2025, 2)) + [2024]).show()
""")

md("""
## 9. Выводы

1. **Энергобаланс Казахстана** почти не изменился за 35 лет: ископаемые источники дают ~95 % первичной энергии,
   уголь — около половины; доля низкоуглеродных источников выросла лишь с 2–3 % до 5 % (ветер и солнце с 2019 г.).
2. **Выбросы**: после спада 1990-х (−50 % к 1999 г.) рост до 2017 г., затем плато ~280–300 млн т. По душевым выбросам
   (13.9 т/чел) Казахстан — первый в Центральной Азии и СНГ, на уровне Австралии/Канады и выше Китая и Германии.
3. **Прогноз**: на годовом горизонте 8 лет наивная модель оказалась конкурентоспособной (MAPE 8.3 %); лучшая модель по
   сумме рангов hold-out и CV используется для прогноза до 2030 г. с интервалом неопределённости. На месячных данных
   SARIMA/ETS дают MAPE 4–6 % и превосходят Naive в 3 раза.
4. **Инженерия**: Parquet + оптимизация типов экономят 95 % места и 50 % памяти; SQLite с 12 запросами обеспечивает
   воспроизводимую аналитику; результаты (метрики, прогнозы) сохраняются в Parquet/CSV/JSON и в таблицы базы.

### Вклад участников

| Участник | Зона ответственности |
|---|---|
| Aidar | архитектура пакета, загрузка и очистка данных, прогнозирование и метрики, консольное меню, дашборд Streamlit, сервер API для 3D-фронтенда |
| Daniyal | EDA, анализ временных рядов (STL, стационарность, ACF/PACF), корреляции с внешними факторами, визуализации, 3D-фронтенд |
| Nurzhan | схема SQLite и ER-диаграмма, 12 SQL-запросов, Parquet и бенчмарки CSV/Parquet и Pandas/SQL, отчёт и презентация |
""")

nb["cells"] = cells
nb["metadata"] = {"kernelspec": {"name": "python3", "display_name": "Python 3 (.venv)", "language": "python"},
                  "language_info": {"name": "python"}}
out = ROOT / "Final_Project.ipynb"
nbf.write(nb, out)
print("written", out, len(cells), "cells")
