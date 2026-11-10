"""SQLite: создание схемы, загрузка таблиц, выполнение SQL-запросов, ER-диаграмма."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config

ENERGY_DB_COLUMNS = [
    "population", "gdp", "primary_energy_consumption", "energy_per_capita",
    "coal_consumption", "oil_consumption", "gas_consumption", "nuclear_consumption", "hydro_consumption",
    "wind_consumption", "solar_consumption", "biofuel_consumption", "other_renewable_consumption",
    "fossil_share_energy", "renewables_share_energy", "low_carbon_share_energy", "coal_share_energy",
    "electricity_generation", "carbon_intensity_elec",
]
EMISSIONS_DB_COLUMNS = [
    "co2", "co2_per_capita", "co2_per_gdp", "coal_co2", "oil_co2", "gas_co2", "cement_co2", "flaring_co2",
    "consumption_co2", "total_ghg", "methane", "nitrous_oxide", "share_global_co2", "cumulative_co2",
]


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Открыть соединение с SQLite (создаёт файл при отсутствии)."""
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Выполнить DDL из `sql/schema.sql`."""
    path = Path(schema_path or config.SQL_DIR / "schema.sql")
    with open(path, encoding="utf-8") as handle:
        conn.executescript(handle.read())
    conn.commit()


def load_database(panel: pd.DataFrame, monthly: pd.DataFrame, factors: pd.DataFrame,
                  countries: pd.DataFrame, db_path: Path | None = None) -> dict[str, int]:
    """Создать схему и загрузить обработанные таблицы; вернуть число строк по таблицам."""
    conn = connect(db_path)
    create_schema(conn)
    countries_db = countries.rename(columns={"country": "name"}).copy()
    countries_db.insert(0, "country_id", range(1, len(countries_db) + 1))
    for flag in ("eu", "oecd", "g20"):
        countries_db[flag] = countries_db[flag].astype(int)
    countries_db[["country_id", "name", "iso_code", "continent", "region", "eu", "oecd", "g20"]].to_sql(
        "countries", conn, if_exists="append", index=False)
    id_map = dict(zip(countries_db["name"], countries_db["country_id"]))

    annual = panel[panel["country"].isin(id_map)].copy()
    annual["country_id"] = annual["country"].map(id_map).astype(int)
    energy_cols = [c for c in ENERGY_DB_COLUMNS if c in annual.columns]
    annual[["country_id", "year"] + energy_cols].to_sql("energy_annual", conn, if_exists="append", index=False)
    emissions_cols = [c for c in EMISSIONS_DB_COLUMNS if c in annual.columns]
    annual[["country_id", "year"] + emissions_cols].to_sql("emissions_annual", conn, if_exists="append", index=False)

    m = monthly[monthly["country"].isin(id_map)].copy()
    m["country_id"] = m["country"].map(id_map).astype(int)
    m["date"] = m["date"].dt.strftime("%Y-%m-%d")
    m[["country_id", "date", "source", "generation_twh", "share_pct", "emissions_mtco2", "intensity_gco2_kwh"]].to_sql(
        "electricity_monthly", conn, if_exists="append", index=False)

    factors[["year", "oil_price", "temperature_anomaly"]].dropna(how="all", subset=["oil_price", "temperature_anomaly"]).to_sql(
        "external_factors", conn, if_exists="append", index=False)
    conn.commit()
    counts = table_counts(conn)
    conn.close()
    return counts


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Число строк в каждой таблице базы."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def save_forecast_results(metrics: pd.DataFrame, forecasts: pd.DataFrame, target: str, frequency: str,
                          db_path: Path | None = None) -> dict[str, int]:
    """Сохранить метрики моделей и прогнозы в таблицы model_metrics / forecast_results."""
    conn = connect(db_path)
    id_map = dict(conn.execute("SELECT name, country_id FROM countries").fetchall())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("DELETE FROM model_metrics WHERE target = ? AND frequency = ?", (target, frequency))
    conn.execute("DELETE FROM forecast_results WHERE target = ? AND frequency = ?", (target, frequency))
    met = metrics[metrics["series"].isin(id_map)].copy()
    met["country_id"] = met["series"].map(id_map).astype(int)
    met = met.assign(target=target, frequency=frequency, created_at=now, is_baseline=met["is_baseline"].astype(int))
    met = met.rename(columns={"MAE": "mae", "RMSE": "rmse", "MAPE": "mape", "sMAPE": "smape", "MASE": "mase"})
    met[["country_id", "target", "frequency", "model", "is_baseline", "mae", "rmse", "mape", "smape", "mase",
         "train_time_s", "created_at"]].to_sql("model_metrics", conn, if_exists="append", index=False)
    fc = forecasts[forecasts["series"].isin(id_map)].copy()
    fc["country_id"] = fc["series"].map(id_map).astype(int)
    fc["date"] = pd.to_datetime(fc["date"]).dt.strftime("%Y-%m-%d")
    fc = fc.assign(target=target, frequency=frequency, created_at=now)
    fc[["country_id", "target", "frequency", "model", "date", "y_true", "y_pred", "created_at"]].to_sql(
        "forecast_results", conn, if_exists="append", index=False)
    conn.commit()
    counts = {"model_metrics": len(met), "forecast_results": len(fc)}
    conn.close()
    return counts


def run_query(sql: str, params: tuple = (), db_path: Path | None = None) -> pd.DataFrame:
    """Выполнить SQL и вернуть результат как DataFrame."""
    conn = connect(db_path)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def list_queries(directory: Path | None = None) -> list[dict[str, str]]:
    """Список сохранённых SQL-запросов: имя файла, заголовок (из `-- title:`), текст."""
    directory = Path(directory or config.QUERIES_DIR)
    queries = []
    for path in sorted(directory.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"--\s*title:\s*(.+)", text)
        queries.append({"name": path.stem, "title": match.group(1).strip() if match else path.stem, "sql": text})
    return queries


def run_all_queries(db_path: Path | None = None, save: bool = True) -> dict[str, pd.DataFrame]:
    """Выполнить все запросы из `sql/queries` и (опционально) сохранить результаты в CSV."""
    results: dict[str, pd.DataFrame] = {}
    out_dir = config.RESULTS_DIR / "sql"
    for q in list_queries():
        try:
            df = run_query(q["sql"], db_path=db_path)
        except (sqlite3.Error, pd.errors.DatabaseError) as err:
            print(f"[sql] {q['name']}: {err}")
            df = pd.DataFrame({"error": [str(err)]})
        results[q["name"]] = df
        if save:
            out_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_dir / f"{q['name']}.csv", index=False)
    return results


# --- ER-диаграмма -----------------------------------------------------------------

ER_TABLES: dict[str, list[str]] = {
    "countries": ["country_id PK", "name", "iso_code", "continent", "region", "eu / oecd / g20"],
    "energy_annual": ["country_id FK", "year", "population, gdp", "primary_energy_consumption", "<source>_consumption ×9", "fossil/renewables/low_carbon share", "electricity_generation", "carbon_intensity_elec"],
    "emissions_annual": ["country_id FK", "year", "co2, co2_per_capita", "coal/oil/gas/cement/flaring_co2", "consumption_co2", "total_ghg, methane, nitrous_oxide", "share_global_co2", "cumulative_co2"],
    "electricity_monthly": ["country_id FK", "date", "source", "generation_twh", "share_pct", "emissions_mtco2", "intensity_gco2_kwh"],
    "external_factors": ["year PK", "oil_price", "temperature_anomaly"],
    "model_metrics": ["metric_id PK", "country_id FK", "target, frequency", "model, is_baseline", "mae, rmse, mape, smape, mase", "train_time_s", "created_at"],
    "forecast_results": ["forecast_id PK", "country_id FK", "target, frequency", "model", "date", "y_true, y_pred", "created_at"],
}


def draw_er_diagram(path: Path | None = None):
    """Нарисовать ER-диаграмму схемы базы (matplotlib) и сохранить в PNG."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    path = Path(path or config.DOCS_DIR / "er_diagram.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    positions = {
        "countries": (5.0, 4.9), "energy_annual": (1.2, 8.6), "emissions_annual": (5.0, 9.3),
        "electricity_monthly": (8.8, 8.6), "external_factors": (9.2, 3.2),
        "model_metrics": (1.2, 1.2), "forecast_results": (5.0, 1.0),
    }
    fig, ax = plt.subplots(figsize=(14, 10.5))
    ax.set_xlim(-0.5, 11.5)
    ax.set_ylim(-1.0, 12.0)
    ax.axis("off")
    boxes = {}
    for table, (x, y) in positions.items():
        fields = ER_TABLES[table]
        height = 0.38 * (len(fields) + 1) + 0.25
        width = 2.9
        box = FancyBboxPatch((x - width / 2, y - height / 2), width, height, boxstyle="round,pad=0.02",
                             linewidth=1.5, edgecolor="#1f3b63", facecolor="#eef3fa")
        ax.add_patch(box)
        ax.add_patch(FancyBboxPatch((x - width / 2, y + height / 2 - 0.45), width, 0.45, boxstyle="square,pad=0",
                                    linewidth=0, facecolor="#1f3b63"))
        ax.text(x, y + height / 2 - 0.22, table, ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        for i, field in enumerate(fields):
            weight = "bold" if ("PK" in field or "FK" in field) else "normal"
            ax.text(x - width / 2 + 0.15, y + height / 2 - 0.45 - 0.38 * (i + 0.7), field, ha="left", va="center",
                    fontsize=9, fontweight=weight, color="#1f1f1f")
        boxes[table] = (x, y, width, height)

    def edge(src: str, dst: str, label: str = "1 : N") -> None:
        x1, y1, w1, h1 = boxes[src]
        x2, y2, w2, h2 = boxes[dst]
        ax.annotate("", xy=(x2, y2 + (h2 / 2 if y2 < y1 else -h2 / 2)), xytext=(x1, y1 + (h1 / 2 if y2 > y1 else -h1 / 2)),
                    arrowprops=dict(arrowstyle="-|>", color="#4a4a4a", lw=1.4))
        ax.text((x1 + x2) / 2 + 0.15, (y1 + y2) / 2, label, fontsize=9, color="#4a4a4a", ha="left", va="center",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none"))

    for child in ("energy_annual", "emissions_annual", "electricity_monthly", "model_metrics", "forecast_results"):
        edge("countries", child)
    # external_factors связана с годовыми таблицами по году (логическая связь)
    x1, y1, w1, h1 = boxes["external_factors"]
    x2, y2, w2, h2 = boxes["emissions_annual"]
    ax.annotate("", xy=(x2 + w2 / 2, y2 - h2 / 2 + 0.3), xytext=(x1, y1 + h1 / 2),
                arrowprops=dict(arrowstyle="-", linestyle="--", color="#888", lw=1.2))
    ax.text(8.55, 6.3, "по year\n(логическая связь)", fontsize=8.5, color="#666", ha="center",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none"))
    ax.set_title("ER-диаграмма базы данных energy_co2.db (SQLite)", fontsize=14, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path
