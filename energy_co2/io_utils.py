"""Работа с файлами: загрузка источников, CSV/Parquet/JSON, чанки, замер памяти и времени."""

from __future__ import annotations

import json
import time
import tracemalloc
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np
import pandas as pd

from . import config


# --- Загрузка источников ------------------------------------------------------

def download_sources(force: bool = False, names: list[str] | None = None) -> dict[str, Path]:
    """Скачать исходные файлы из `config.DATA_SOURCES`, если их ещё нет.

    Возвращает словарь имя -> путь. Ошибки сети перехватываются: отсутствующий
    файл просто пропускается, а сообщение выводится в консоль.
    """
    config.ensure_dirs()
    paths: dict[str, Path] = {}
    for name, meta in config.DATA_SOURCES.items():
        if names is not None and name not in names:
            continue
        target = config.RAW_DIR / meta["file"]
        if target.exists() and not force:
            paths[name] = target
            continue
        try:
            print(f"[download] {name}: {meta['url']}")
            request = urllib.request.Request(meta["url"], headers={"User-Agent": "energy-co2-final-project"})
            with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as handle:
                handle.write(response.read())
            paths[name] = target
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            print(f"[download] не удалось скачать {name}: {err}")
    return paths


def raw_path(name: str) -> Path:
    """Путь к исходному файлу по имени источника."""
    if name not in config.DATA_SOURCES:
        raise KeyError(f"Неизвестный источник данных: {name}")
    return config.RAW_DIR / config.DATA_SOURCES[name]["file"]


# --- Размер, память, время ------------------------------------------------------

def file_size_mb(path: Path | str) -> float:
    """Размер файла в мегабайтах (0, если файла нет)."""
    path = Path(path)
    return round(path.stat().st_size / 1024 ** 2, 3) if path.exists() else 0.0


def memory_usage_mb(df: pd.DataFrame) -> float:
    """Объём DataFrame в памяти (deep) в мегабайтах."""
    return round(float(df.memory_usage(deep=True).sum()) / 1024 ** 2, 3)


@contextmanager
def measure(label: str = "") -> Iterator[dict[str, Any]]:
    """Контекстный менеджер: время выполнения и пиковая память (tracemalloc).

    >>> with measure("read csv") as stats:
    ...     df = pd.read_csv(path)
    >>> stats["seconds"], stats["peak_mb"]
    """
    stats: dict[str, Any] = {"label": label}
    tracemalloc.start()
    start = time.perf_counter()
    try:
        yield stats
    finally:
        stats["seconds"] = round(time.perf_counter() - start, 4)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        stats["peak_mb"] = round(peak / 1024 ** 2, 3)


# --- Оптимизация типов и чанковая загрузка -------------------------------------

def optimize_dtypes(df: pd.DataFrame, float_dtype: str = "float32", category_threshold: float = 0.5,
                    categories: bool = True) -> pd.DataFrame:
    """Уменьшить потребление памяти: float64→float32, целые→минимальный тип, строки→category."""
    out = df.copy()
    for col in out.columns:
        series = out[col]
        if pd.api.types.is_float_dtype(series):
            out[col] = series.astype(float_dtype)
        elif pd.api.types.is_integer_dtype(series):
            out[col] = pd.to_numeric(series, downcast="integer")
        elif categories and (pd.api.types.is_string_dtype(series) or series.dtype == object):
            n_unique = series.nunique(dropna=True)
            if len(series) and n_unique / len(series) < category_threshold:
                out[col] = series.astype("category")
    return out


def read_csv_chunked(
    path: Path | str,
    chunksize: int = 5_000,
    usecols: list[str] | None = None,
    transform: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    optimize: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Прочитать CSV чанками, применить `transform` к каждому чанку и собрать результат.

    Возвращает (DataFrame, статистика): число чанков, строки, время, пиковая память.
    Используется для демонстрации обработки с учётом ограничений памяти.
    """
    parts: list[pd.DataFrame] = []
    n_rows = 0
    with measure(f"chunked read {Path(path).name}") as stats:
        for i, chunk in enumerate(pd.read_csv(path, chunksize=chunksize, usecols=usecols)):
            if transform is not None:
                chunk = transform(chunk)
            if optimize:
                chunk = optimize_dtypes(chunk, categories=False)   # числа сжимаем сразу в каждом чанке
            n_rows += len(chunk)
            parts.append(chunk)
        df = pd.concat(parts, ignore_index=True)
        if optimize:
            df = optimize_dtypes(df)   # строки → category один раз, после сборки
    stats.update({"chunks": len(parts), "rows": n_rows, "chunksize": chunksize, "memory_mb": memory_usage_mb(df)})
    return df, stats


# --- Parquet / CSV / JSON -------------------------------------------------------

def write_parquet(df: pd.DataFrame, path: Path | str, compression: str = "snappy") -> Path:
    """Сохранить DataFrame в Parquet (pyarrow)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression=compression, engine="pyarrow")
    return path


def read_parquet(path: Path | str, columns: list[str] | None = None) -> pd.DataFrame:
    """Прочитать Parquet (с возможностью выбрать колонки — column pruning)."""
    return pd.read_parquet(path, columns=columns, engine="pyarrow")


def save_dataframe(df: pd.DataFrame, name: str, directory: Path | None = None,
                   formats: tuple[str, ...] = ("parquet", "csv")) -> dict[str, Path]:
    """Сохранить результат анализа в нескольких форматах в `outputs/results`."""
    directory = Path(directory or config.RESULTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "parquet":
            saved[fmt] = write_parquet(df, directory / f"{name}.parquet")
        elif fmt == "csv":
            path = directory / f"{name}.csv"
            df.to_csv(path, index=False)
            saved[fmt] = path
        elif fmt == "json":
            path = directory / f"{name}.json"
            df.to_json(path, orient="records", indent=2, force_ascii=False)
            saved[fmt] = path
        else:
            raise ValueError(f"Неизвестный формат: {fmt}")
    return saved


def save_json(obj: Any, path: Path | str) -> Path:
    """Сохранить объект в JSON (numpy-типы приводятся к встроенным)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(value: Any) -> Any:
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (np.ndarray,)):
            return value.tolist()
        if isinstance(value, (pd.Timestamp,)):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return str(value)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, default=_default)
    return path


def load_json(path: Path | str, default: Any = None) -> Any:
    """Прочитать JSON; при отсутствии файла или ошибке разбора вернуть `default`."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as err:
        print(f"[load_json] повреждённый файл {path}: {err}")
        return default
