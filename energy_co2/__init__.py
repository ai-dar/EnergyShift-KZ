"""Пакет итогового проекта «Global Energy Mix and CO₂ Emissions» (тема 60).

Модули:
    config        — пути, константы, группы стран, словари переменных
    io_utils      — загрузка/сохранение данных (CSV, Parquet, JSON), чанки, память
    cleaning      — очистка панельных данных, нормализация на душу населения
    eda           — описательная статистика, пропуски, выбросы, проверка индексов
    timeseries    — resample, скользящие средние, STL, стационарность, ACF/PACF
    metrics       — MAE, RMSE, MAPE, sMAPE, MASE
    forecasting   — baseline и модели прогноза, hold-out и TimeSeriesSplit
    correlation   — корреляции с внешними факторами
    benchmark     — CSV vs Parquet, Pandas vs SQL
    database      — SQLite: схема, загрузка, SQL-запросы, ER-диаграмма
    visualization — графики matplotlib и Plotly
    pipeline      — шаги проекта, используемые меню и дашбордом
"""

__version__ = "1.0.0"
__all__ = [
    "config", "io_utils", "cleaning", "eda", "timeseries", "metrics",
    "forecasting", "correlation", "benchmark", "database", "visualization", "pipeline",
]
