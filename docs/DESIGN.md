# Design: Global Energy Mix and CO₂ Emissions (topic 60)

Дата: 2026-11-07. Команда: Aidar, Daniyal, Nurzhan (AAI-2604).
Дисциплина: Programming for Data Analysis and Database (Applied AI, магистратура).

## Цель
Сравнить страны по структуре энергопотребления и выбросам CO₂, изучить энергетический
переход (доля ископаемых / низкоуглеродных источников), сопоставить Казахстан с
странами-аналогами и построить прогноз выбросов, сравнив его с наивными baseline.

## Источники данных
| Набор | Файл | Частота | Назначение |
|---|---|---|---|
| OWID Energy | `data/raw/owid-energy-data.csv` | год | энергобаланс, душевые показатели, доли источников |
| OWID CO₂ | `data/raw/owid-co2-data.csv` | год | выбросы CO₂ по видам топлива, ПГ, душевые |
| Ember monthly | `data/raw/ember_monthly_generation.csv` | месяц | сезонность, STL, seasonal naive, прогноз по месяцам |
| OWID crude oil prices | `data/raw/crude-oil-prices.csv` | год | внешний фактор «цены» |
| OWID temperature anomaly | `data/raw/temperature-anomaly.csv` | год | внешний фактор «погода/климат» |

Тема 60 входит в список исключений по объёму данных, но чанковая загрузка, оптимизация
типов и Parquet демонстрируются на «длинном» формате (country, year, variable, value) ≈ 2 млн строк.

## Архитектура
```
main.py            консольное меню (10 пунктов) + режим --all
app.py             Streamlit-дашборд (фильтры: период, регион/страна, серия; прогноз)
config.py          пути, константы, группы стран, словари переменных
src/energy_co2/    пакет: io_utils, cleaning, eda, timeseries, forecasting, metrics,
                   benchmark, database, correlation, visualization, pipeline
sql/schema.sql     схема SQLite (6 таблиц), sql/queries/*.sql — 10 запросов
notebooks/         final_project.ipynb — повествовательный анализ с выполненными ячейками
docs/              REPORT (md/docx/pdf), presentation (pptx/pdf), ER-диаграмма
outputs/           figures (png/html), results (parquet/csv/json)
```

## Решения
- Период панели: 1990–2024 (постсоветские страны имеют данные с 1985/1990).
- Целевые ряды: годовой CO₂ (млн т) и CO₂ на душу; месячные выбросы электроэнергетики (Ember).
- Hold-out: годовой — последние 8 лет (2017–2024); месячный — последние 12 месяцев.
- Скользящая CV: `TimeSeriesSplit` без перемешивания.
- Baseline: Naive, Seasonal naive (m=12 для месяцев; для годовых m=1 ≡ naive, поэтому добавлен Drift).
- Модели: ETS (Holt / Holt-Winters), ARIMA/SARIMA, линейная регрессия на лагах + тренд,
  градиентный бустинг на лагах (HistGradientBoosting).
- Метрики: MAE, RMSE, MAPE, sMAPE, MASE + время обучения; ошибки по горизонту и по сериям.
- Сравнение подходов: CSV vs Parquet (время, размер, память), Pandas vs SQL (время), модели vs baseline.
- Группы-аналоги Казахстана: Центральная Азия/СНГ, ресурсные экономики, крупнейшие эмитенты.
