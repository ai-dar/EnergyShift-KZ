"""Тесты Python-сервера 3D-фронтенда: данные для глобуса, страны, прогноз, SQL, раздача статики."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from energy_co2 import config, webdata  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (config.PROCESSED_DIR / "panel_annual.parquet").exists(), reason="нет обработанных данных"
)


@pytest.fixture(scope="module")
def client():
    import server

    webdata.ensure_ready()
    return TestClient(server.app)


def test_bootstrap_has_everything_the_globe_needs(client):
    boot = client.get("/api/bootstrap").json()
    assert boot["target"] == "KAZ"
    assert boot["years"][0] == config.YEAR_MIN and boot["years"][-1] == config.YEAR_MAX
    assert len(boot["countries"]) > 150
    series = boot["values"]["co2_per_capita"]["KAZ"]
    assert len(series) == len(boot["years"]) and series[-1] > 5
    assert "KAZ" in boot["peer_groups"]["Центральная Азия и СНГ"]
    assert {m["key"] for m in boot["metrics"]} <= set(boot["values"])


def test_bootstrap_is_valid_json_without_nan(client):
    text = client.get("/api/bootstrap").text
    assert "NaN" not in text and "Infinity" not in text


def test_country_detail_and_missing_data(client):
    kz = client.get("/api/country/kaz").json()
    assert kz["label"] == "Казахстан"
    assert set(kz["mix"]["sources"]) == set(config.ENERGY_SOURCES)
    assert len(kz["monthly"]["dates"]) == len(kz["monthly"]["emissions"]) >= 84
    afg = client.get("/api/country/AFG").json()
    assert afg["mix"] is None and afg["monthly"] is None


def test_unknown_country_and_bad_frequency_give_clear_errors(client):
    assert client.get("/api/country/XXX").status_code == 404
    assert client.get("/api/forecast/XXX").status_code == 404
    bad = client.get("/api/forecast/KAZ", params={"freq": "weekly"})
    assert bad.status_code == 422 and "freq" in bad.json()["detail"]
    assert client.get("/api/forecast/AFG", params={"freq": "monthly"}).status_code == 422


def test_live_annual_forecast_for_country_outside_peer_list(client):
    data = client.get("/api/forecast/FRA").json()
    assert data["source"] == "live"
    assert len(data["holdout"]["x"]) == config.ANNUAL_HOLDOUT
    assert {"Naive", "ARIMA", "ETS"} <= set(data["holdout"]["models"])
    assert all(len(v) == config.ANNUAL_HOLDOUT for v in data["holdout"]["models"].values())
    mase = [m["MASE"] for m in data["metrics"]]
    assert mase == sorted(mase)                                  # отсортировано от лучшей модели
    future = data["future"]
    assert len(future["y"]) == config.FUTURE_HORIZON
    assert all(lo <= y <= hi for lo, y, hi in zip(future["lower"], future["y"], future["upper"]))
    assert int(future["x"][0]) == config.YEAR_MAX + 1


def test_sql_catalog_and_query(client):
    catalog = client.get("/api/sql").json()
    assert len(catalog) >= 8
    result = client.get(f"/api/sql/{catalog[0]['name']}").json()
    assert result["columns"] and len(result["rows"]) == min(result["total"], webdata.MAX_SQL_ROWS)
    assert "-- title:" not in result["sql"]
    assert client.get("/api/sql/no_such_query").status_code == 404


def test_frontend_files_are_served_locally(client):
    page = client.get("/")
    assert page.status_code == 200 and "EnergyShift" in page.text
    assert "http://" not in page.text.replace("http://www.w3.org", "") and "https://" not in page.text   # ничего не грузим из сети
    for asset in ("style.css", "js/main.js", "vendor/globe.gl.min.js", "vendor/three.min.js",
                  "vendor/countries.geojson", "vendor/fonts/geologica-cyrillic.woff2"):
        assert client.get(f"/{asset}").status_code == 200, asset
