-- Схема базы данных проекта «Global Energy Mix and CO₂ Emissions» (SQLite).
-- ER: countries 1—N energy_annual, countries 1—N emissions_annual, countries 1—N electricity_monthly,
--     countries 1—N model_metrics, countries 1—N forecast_results; external_factors связана по году.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS forecast_results;
DROP TABLE IF EXISTS model_metrics;
DROP TABLE IF EXISTS electricity_monthly;
DROP TABLE IF EXISTS emissions_annual;
DROP TABLE IF EXISTS energy_annual;
DROP TABLE IF EXISTS external_factors;
DROP TABLE IF EXISTS countries;

CREATE TABLE countries (
    country_id   INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    iso_code     TEXT    NOT NULL UNIQUE,
    continent    TEXT,
    region       TEXT,
    eu           INTEGER NOT NULL DEFAULT 0,
    oecd         INTEGER NOT NULL DEFAULT 0,
    g20          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE energy_annual (
    country_id                  INTEGER NOT NULL REFERENCES countries(country_id),
    year                        INTEGER NOT NULL,
    population                  REAL,
    gdp                         REAL,
    primary_energy_consumption  REAL,   -- ТВт·ч
    energy_per_capita           REAL,   -- кВт·ч/чел
    coal_consumption            REAL,
    oil_consumption             REAL,
    gas_consumption             REAL,
    nuclear_consumption         REAL,
    hydro_consumption           REAL,
    wind_consumption            REAL,
    solar_consumption           REAL,
    biofuel_consumption         REAL,
    other_renewable_consumption REAL,
    fossil_share_energy         REAL,   -- %
    renewables_share_energy     REAL,
    low_carbon_share_energy     REAL,
    coal_share_energy           REAL,
    electricity_generation      REAL,   -- ТВт·ч
    carbon_intensity_elec       REAL,   -- г CO₂/кВт·ч
    PRIMARY KEY (country_id, year)
);

CREATE TABLE emissions_annual (
    country_id        INTEGER NOT NULL REFERENCES countries(country_id),
    year              INTEGER NOT NULL,
    co2               REAL,   -- млн т
    co2_per_capita    REAL,   -- т/чел
    co2_per_gdp       REAL,
    coal_co2          REAL,
    oil_co2           REAL,
    gas_co2           REAL,
    cement_co2        REAL,
    flaring_co2       REAL,
    consumption_co2   REAL,
    total_ghg         REAL,
    methane           REAL,
    nitrous_oxide     REAL,
    share_global_co2  REAL,
    cumulative_co2    REAL,
    PRIMARY KEY (country_id, year)
);

CREATE TABLE electricity_monthly (
    country_id          INTEGER NOT NULL REFERENCES countries(country_id),
    date                TEXT    NOT NULL,   -- первое число месяца, ISO
    source              TEXT    NOT NULL,   -- Coal, Gas, Hydro, ..., Total generation
    generation_twh      REAL,
    share_pct           REAL,
    emissions_mtco2     REAL,
    intensity_gco2_kwh  REAL,
    PRIMARY KEY (country_id, date, source)
);

CREATE TABLE external_factors (
    year                 INTEGER PRIMARY KEY,
    oil_price            REAL,   -- $/баррель
    temperature_anomaly  REAL    -- °C
);

CREATE TABLE model_metrics (
    metric_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id    INTEGER NOT NULL REFERENCES countries(country_id),
    target        TEXT NOT NULL,
    frequency     TEXT NOT NULL,     -- annual / monthly
    model         TEXT NOT NULL,
    is_baseline   INTEGER NOT NULL,
    mae REAL, rmse REAL, mape REAL, smape REAL, mase REAL,
    train_time_s  REAL,
    created_at    TEXT NOT NULL
);

CREATE TABLE forecast_results (
    forecast_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id    INTEGER NOT NULL REFERENCES countries(country_id),
    target        TEXT NOT NULL,
    frequency     TEXT NOT NULL,
    model         TEXT NOT NULL,
    date          TEXT NOT NULL,
    y_true        REAL,
    y_pred        REAL,
    created_at    TEXT NOT NULL
);

CREATE INDEX idx_energy_year ON energy_annual(year);
CREATE INDEX idx_emissions_year ON emissions_annual(year);
CREATE INDEX idx_monthly_source ON electricity_monthly(source, date);
CREATE INDEX idx_metrics_country ON model_metrics(country_id, target, frequency);
