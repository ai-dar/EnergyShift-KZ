"""Сервер 3D-фронтенда EnergyShift KZ (FastAPI). Запуск: python web/server.py

Браузер только рисует: данные, прогнозы и SQL-запросы приходят из пакета energy_co2 через /api/*.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from energy_co2 import config, webdata  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="EnergyShift KZ", docs_url="/api/docs", redoc_url=None)


def _guard(fn, *args):
    """Перевести ошибки данных в понятные HTTP-ответы."""
    try:
        return fn(*args)
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err).strip("'\"")) from err
    except (ValueError, FileNotFoundError) as err:
        raise HTTPException(status_code=422, detail=str(err)) from err


@app.get("/api/bootstrap")
def api_bootstrap() -> dict:
    return _guard(webdata.bootstrap)


@app.get("/api/country/{iso}")
def api_country(iso: str) -> dict:
    return _guard(webdata.country_detail, iso.upper())


@app.get("/api/forecast/{iso}")
def api_forecast(iso: str, freq: str = "annual") -> dict:
    return _guard(webdata.forecast, iso.upper(), freq)


@app.get("/api/sql")
def api_sql_catalog() -> list[dict]:
    return _guard(webdata.sql_catalog)


@app.get("/api/sql/{name}")
def api_sql_run(name: str) -> dict:
    return _guard(webdata.sql_run, name)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")


def main(open_browser: bool = True, host: str = config.WEB_HOST, port: int = config.WEB_PORT) -> None:
    import uvicorn

    try:
        webdata.ensure_ready()
    except FileNotFoundError as err:
        print(f"Ошибка: {err}")
        return
    url = f"http://{host}:{port}"
    print(f"EnergyShift KZ: 3D-фронтенд на {url} (Ctrl+C — остановить)")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main(open_browser="--no-browser" not in sys.argv)
