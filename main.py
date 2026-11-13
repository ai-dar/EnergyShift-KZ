"""Консольное меню проекта EnergyShift KZ (тема 60 «Global Energy Mix and CO₂ Emissions»).

Запуск:  python main.py            — интерактивное меню
         python main.py --all      — выполнить все шаги без вопросов
         python main.py --step 6   — выполнить один шаг (номер из меню)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from energy_co2 import cleaning, config, database, forecasting, pipeline, timeseries

STATE_FILE = config.RESULTS_DIR / "session_log.json"


# --- Интерактивные операции -------------------------------------------------------

def interactive_forecast() -> dict:
    """Быстрый прогноз для выбранной страны: спрашиваем страну, модель и горизонт."""
    panel = cleaning.load_processed("panel")
    countries = sorted(panel["country"].unique())
    country = input(f"Страна [{config.TARGET_COUNTRY}]: ").strip() or config.TARGET_COUNTRY
    if country not in countries:
        matches = [c for c in countries if country.lower() in c.lower()]
        if not matches:
            raise ValueError(f"Страна «{country}» не найдена в панели")
        country = matches[0]
        print(f"  Использую ближайшее совпадение: {country}")
    models = list(forecasting.MODEL_REGISTRY)
    print("  Модели: " + ", ".join(f"{i + 1} — {m}" for i, m in enumerate(models)))
    choice = input("  Номер модели [6 — ARIMA]: ").strip() or "6"
    model = models[int(choice) - 1]
    horizon = int(input(f"  Горизонт, лет [{config.FUTURE_HORIZON}]: ").strip() or config.FUTURE_HORIZON)
    series = timeseries.annual_series(panel, country, "co2")
    metrics, _ = forecasting.evaluate_holdout(series, config.ANNUAL_HOLDOUT, 1, ["Naive", model], series_name=country)
    future = forecasting.future_forecast(series, model, horizon, 1)
    print("\n  Hold-out (последние %d лет):" % config.ANNUAL_HOLDOUT)
    print(metrics[["model", "MAE", "MAPE", "MASE", "train_time_s"]].to_string(index=False))
    print(f"\n  Прогноз выбросов CO₂ ({model}), млн т:")
    for _, row in future.iterrows():
        print(f"    {row['date'].year}: {row['forecast']:.1f}  [{row['lower']:.1f}; {row['upper']:.1f}]")
    out = config.RESULTS_DIR / f"forecast_custom_{country.replace(' ', '_')}_{model.replace(' ', '_')}.csv"
    future.to_csv(out, index=False)
    print(f"  Сохранено: {out}")
    return {"country": country, "model": model, "horizon": horizon, "file": str(out)}


def interactive_sql() -> dict:
    """Выполнить один из сохранённых SQL-запросов и показать результат."""
    queries = database.list_queries()
    for i, q in enumerate(queries, start=1):
        print(f"  {i:2d}. {q['title']}")
    choice = int(input("  Номер запроса: ").strip())
    if not 1 <= choice <= len(queries):
        raise ValueError(f"Нужен номер от 1 до {len(queries)}")
    q = queries[choice - 1]
    df = database.run_query(q["sql"])
    print(df.head(25).to_string(index=False))
    print(f"  ... всего строк: {len(df)}")
    return {"query": q["name"], "rows": int(len(df))}


def interactive_search() -> dict:
    """Поиск страны по подстроке и вывод ключевых показателей за последний год."""
    panel = cleaning.load_processed("panel")
    text = input("  Фрагмент названия страны: ").strip().lower()
    if not text:
        raise ValueError("Пустой запрос")
    found = sorted(c for c in panel["country"].unique() if text in c.lower())
    if not found:
        print("  Ничего не найдено")
        return {"query": text, "found": []}
    cols = ["country", "year", "co2", "co2_per_capita", "fossil_share_energy", "low_carbon_share_energy", "energy_per_capita"]
    latest = panel[(panel["country"].isin(found)) & (panel["year"] == config.YEAR_MAX)][cols]
    print(latest.round(2).to_string(index=False))
    return {"query": text, "found": found}


def show_status() -> dict:
    """Показать, какие шаги уже выполнены (по наличию файлов результатов)."""
    checks = {
        "исходные данные": all((config.RAW_DIR / m["file"]).exists() for m in config.DATA_SOURCES.values()),
        "обработанные Parquet": (config.PROCESSED_DIR / "panel_annual.parquet").exists(),
        "EDA": (config.RESULTS_DIR / "eda_summary.json").exists(),
        "временные ряды": (config.RESULTS_DIR / "timeseries_summary.json").exists(),
        "база данных SQLite": config.DB_PATH.exists(),
        "прогнозы": (config.RESULTS_DIR / "forecast_summary.json").exists(),
        "бенчмарки": (config.RESULTS_DIR / "benchmark_summary.json").exists(),
        "корреляции": (config.RESULTS_DIR / "correlation_summary.json").exists(),
        "графики": any(config.FIG_DIR.glob("*.html")),
    }
    for name, ok in checks.items():
        print(f"  [{'✓' if ok else ' '}] {name}")
    return checks


def run_frontend() -> dict:
    """Запустить сервер 3D-фронтенда (FastAPI) и открыть его в браузере; Ctrl+C возвращает в меню."""
    server = config.WEB_DIR / "server.py"
    if not server.exists():
        raise FileNotFoundError(f"Не найден файл сервера: {server}")
    print("  Сервер работает, пока вы не нажмёте Ctrl+C.")
    try:
        subprocess.run([sys.executable, str(server)], check=False)
    except KeyboardInterrupt:
        print("\n  Сервер остановлен.")
    return {"url": f"http://{config.WEB_HOST}:{config.WEB_PORT}"}


MENU: list[tuple[str, str, object]] = [
    ("1", "Скачать / проверить исходные данные", pipeline.step_download),
    ("2", "Очистка данных и сохранение в Parquet (чанки, оптимизация типов)", pipeline.step_clean),
    ("3", "EDA: статистика, пропуски, выбросы, проверка временных индексов", pipeline.step_eda),
    ("4", "Временные ряды: resample, скользящие средние, STL, стационарность, ACF/PACF", pipeline.step_timeseries),
    ("5", "База данных SQLite: загрузка, 12 SQL-запросов, ER-диаграмма", pipeline.step_database),
    ("6", "Прогнозирование: baseline vs модели (hold-out + TimeSeriesSplit)", pipeline.step_forecast),
    ("7", "Бенчмарки: CSV vs Parquet, типы данных, Pandas vs SQL", pipeline.step_benchmark),
    ("8", "Корреляции с внешними факторами (цены на нефть, климат, ВВП)", pipeline.step_correlation),
    ("9", "Графики: энергобаланс, сравнение стран, интерактивная карта", pipeline.step_figures),
    ("10", "Выполнить все шаги по порядку", pipeline.run_all),
    ("11", "Быстрый прогноз для выбранной страны", interactive_forecast),
    ("12", "Выполнить SQL-запрос из каталога", interactive_sql),
    ("13", "Поиск страны в панели данных", interactive_search),
    ("14", "Статус проекта (что уже выполнено)", show_status),
    ("15", "Открыть 3D-фронтенд: глобус, энергобаланс, сезонная спираль", run_frontend),
    ("0", "Выход", None),
]


# --- Состояние программы ---------------------------------------------------------------

def load_state() -> dict:
    """Прочитать журнал сессий (JSON); при отсутствии — пустой."""
    try:
        with open(STATE_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"runs": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, default=str)


def run_step(key: str, state: dict) -> bool:
    """Выполнить пункт меню; вернуть False, если выбран выход."""
    actions = {k: (title, fn) for k, title, fn in MENU}
    if key not in actions:
        raise KeyError(f"Нет пункта «{key}»")
    title, fn = actions[key]
    if fn is None:
        return False
    print(f"\n=== {title} ===")
    started = datetime.now()
    try:
        result = fn()
        status = "ok"
    except FileNotFoundError as err:
        print(f"  Ошибка: {err}")
        result, status = None, f"missing file: {err}"
    except (ValueError, KeyError, IndexError) as err:
        print(f"  Ошибка ввода или данных: {err}")
        result, status = None, f"error: {err}"
    state["runs"].append({"step": key, "title": title, "started": started.isoformat(timespec="seconds"),
                          "seconds": round((datetime.now() - started).total_seconds(), 1), "status": status})
    save_state(state)
    if isinstance(result, dict) and len(result) <= 12 and key not in ("10", "14"):
        for k, v in result.items():
            if not isinstance(v, (dict, list)):
                print(f"  {k}: {v}")
    return True


def print_menu() -> None:
    print("\n" + "=" * 72)
    print(" EnergyShift KZ — итоговый проект: Global Energy Mix and CO₂ Emissions (тема 60)")
    print(" Команда: Aidar, Daniyal, Nurzhan — AAI-2604")
    print("=" * 72)
    for key, title, _ in MENU:
        print(f" {key:>2} — {title}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="выполнить все шаги без меню")
    parser.add_argument("--step", help="выполнить один пункт меню (например, 6) и выйти")
    args = parser.parse_args(argv)
    config.ensure_dirs()
    state = load_state()
    if args.all:
        return 0 if run_step("10", state) else 1
    if args.step:
        return 0 if run_step(args.step, state) else 1
    while True:
        print_menu()
        try:
            choice = input("Выберите пункт: ").strip()
            if not run_step(choice, state):
                print("До свидания!")
                return 0
        except KeyError as err:
            print(f"  {err}. Введите номер из списка.")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
