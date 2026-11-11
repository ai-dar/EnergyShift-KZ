"""Сравнение подходов: CSV vs Parquet, оптимизация типов, Pandas vs SQL (время, память, размер)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pandas as pd

from . import config, io_utils


def benchmark_formats(df: pd.DataFrame, directory: Path | None = None, repeats: int = 3) -> pd.DataFrame:
    """Запись/чтение одной таблицы в CSV, Parquet (snappy, gzip): время, размер, память при чтении."""
    directory = Path(directory or config.PROCESSED_DIR / "bench")
    directory.mkdir(parents=True, exist_ok=True)
    cases = {
        "CSV": (lambda p: df.to_csv(p, index=False), lambda p: pd.read_csv(p), "bench.csv"),
        "Parquet (snappy)": (lambda p: df.to_parquet(p, index=False, compression="snappy"), lambda p: pd.read_parquet(p), "bench_snappy.parquet"),
        "Parquet (gzip)": (lambda p: df.to_parquet(p, index=False, compression="gzip"), lambda p: pd.read_parquet(p), "bench_gzip.parquet"),
    }
    rows = []
    for name, (writer, reader, filename) in cases.items():
        path = directory / filename
        t0 = time.perf_counter()
        writer(path)
        write_s = time.perf_counter() - t0
        read_times, peak = [], 0.0
        for _ in range(repeats):
            with io_utils.measure() as st:
                loaded = reader(path)
            read_times.append(st["seconds"])
            peak = max(peak, st["peak_mb"])
        rows.append({"format": name, "rows": len(df), "write_s": round(write_s, 3),
                     "read_s_mean": round(sum(read_times) / len(read_times), 3), "size_mb": io_utils.file_size_mb(path),
                     "read_peak_mb": round(peak, 2), "loaded_memory_mb": io_utils.memory_usage_mb(loaded)})
    out = pd.DataFrame(rows)
    base = out.loc[out["format"] == "CSV", "size_mb"].iloc[0]
    out["size_vs_csv"] = (out["size_mb"] / base).round(3)
    return out


def benchmark_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Память до и после оптимизации типов (float32, downcast, category)."""
    before = io_utils.memory_usage_mb(df)
    t0 = time.perf_counter()
    optimized = io_utils.optimize_dtypes(df)
    seconds = time.perf_counter() - t0
    after = io_utils.memory_usage_mb(optimized)
    return pd.DataFrame([
        {"variant": "исходные типы", "memory_mb": before, "dtypes": str(df.dtypes.value_counts().to_dict())},
        {"variant": "оптимизированные типы", "memory_mb": after, "dtypes": str(optimized.dtypes.value_counts().to_dict()),
         "optimize_s": round(seconds, 3), "saving_pct": round((1 - after / before) * 100, 1) if before else 0.0},
    ])


def benchmark_pandas_vs_sql(panel: pd.DataFrame, db_path: Path | None = None, repeats: int = 5) -> pd.DataFrame:
    """Одни и те же аналитические задачи в Pandas и в SQLite: среднее время выполнения.

    Задачи: (1) среднее CO₂ на душу по странам за 2010–2024; (2) топ-10 стран по CO₂ в последнем году;
    (3) годовой прирост CO₂ (оконная функция LAG vs groupby().diff()).
    """
    db_path = Path(db_path or config.DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError(f"База данных не найдена: {db_path}. Сначала создайте её (меню, пункт 6).")
    conn = sqlite3.connect(db_path)
    year = int(panel["year"].max())
    tasks = {
        "avg co2_per_capita by country 2010–2024": (
            lambda: panel[panel["year"].between(2010, year)].groupby("country", observed=True)["co2_per_capita"].mean().sort_values(ascending=False),
            f"""SELECT c.name, AVG(e.co2_per_capita) AS avg_pc FROM emissions_annual e
                JOIN countries c ON c.country_id = e.country_id
                WHERE e.year BETWEEN 2010 AND {year} GROUP BY c.name ORDER BY avg_pc DESC""",
        ),
        f"top-10 countries by co2 in {year}": (
            lambda: panel[panel["year"] == year].nlargest(10, "co2")[["country", "co2"]],
            f"""SELECT c.name, e.co2 FROM emissions_annual e JOIN countries c ON c.country_id = e.country_id
                WHERE e.year = {year} ORDER BY e.co2 DESC LIMIT 10""",
        ),
        "YoY change of co2 (LAG vs diff)": (
            lambda: panel.sort_values(["country", "year"]).assign(delta=lambda d: d.groupby("country", observed=True)["co2"].diff())[["country", "year", "delta"]],
            """SELECT country_id, year, co2 - LAG(co2) OVER (PARTITION BY country_id ORDER BY year) AS delta
               FROM emissions_annual""",
        ),
    }
    rows = []
    for task, (pandas_fn, sql) in tasks.items():
        for approach, runner in (("Pandas", pandas_fn), ("SQLite", lambda s=sql: pd.read_sql_query(s, conn))):
            times = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                result = runner()
                times.append(time.perf_counter() - t0)
            rows.append({"task": task, "approach": approach, "mean_ms": round(1000 * sum(times) / len(times), 2),
                         "min_ms": round(1000 * min(times), 2), "result_rows": len(result)})
    conn.close()
    return pd.DataFrame(rows)


def chunked_vs_whole(path: Path | str, chunksize: int = 5_000) -> pd.DataFrame:
    """Чтение файла целиком и чанками: время и пиковая память (для раздела про ограничения памяти)."""
    with io_utils.measure("whole") as whole:
        df_whole = pd.read_csv(path)
    _, chunk_stats = io_utils.read_csv_chunked(path, chunksize=chunksize, optimize=True)
    return pd.DataFrame([
        {"approach": "read_csv целиком", "seconds": whole["seconds"], "peak_mb": whole["peak_mb"],
         "memory_mb": io_utils.memory_usage_mb(df_whole), "rows": len(df_whole)},
        {"approach": f"чанки по {chunksize} + оптимизация типов", "seconds": chunk_stats["seconds"],
         "peak_mb": chunk_stats["peak_mb"], "memory_mb": chunk_stats["memory_mb"], "rows": chunk_stats["rows"]},
    ])
