"""Конфигурация проекта: пути, источники данных, константы и справочники."""

from __future__ import annotations

from pathlib import Path

# --- Пути -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "energy_co2.db"
SQL_DIR = BASE_DIR / "sql"
QUERIES_DIR = SQL_DIR / "queries"
OUTPUT_DIR = BASE_DIR / "outputs"
FIG_DIR = OUTPUT_DIR / "figures"
RESULTS_DIR = OUTPUT_DIR / "results"
DOCS_DIR = BASE_DIR / "docs"

# --- Источники данных ------------------------------------------------------
DATA_SOURCES: dict[str, dict[str, str]] = {
    "energy": {
        "file": "owid-energy-data.csv",
        "url": "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
        "description": "Our World in Data — Energy (годовые данные по странам)",
    },
    "co2": {
        "file": "owid-co2-data.csv",
        "url": "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv",
        "description": "Our World in Data — CO₂ and Greenhouse Gas Emissions",
    },
    "ember_monthly": {
        "file": "ember_monthly_generation.csv",
        "url": "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_monthly_global.csv",
        "description": "Ember — месячная генерация электроэнергии и выбросы по источникам",
    },
    "oil_price": {
        "file": "crude-oil-prices.csv",
        "url": "https://ourworldindata.org/grapher/crude-oil-prices.csv?v=1&csvType=full&useColumnShortNames=true",
        "description": "OWID — мировые цены на нефть (внешний фактор «цены»)",
    },
    "continents": {
        "file": "continents.csv",
        "url": "https://ourworldindata.org/grapher/continents-according-to-our-world-in-data.csv?v=1&csvType=full&useColumnShortNames=true",
        "description": "OWID — справочник континентов для всех стран",
    },
    "temperature": {
        "file": "temperature-anomaly.csv",
        "url": "https://ourworldindata.org/grapher/temperature-anomaly.csv?v=1&csvType=full&useColumnShortNames=true",
        "description": "OWID — глобальная температурная аномалия (внешний фактор «климат»)",
    },
}

# --- Период анализа ---------------------------------------------------------
YEAR_MIN = 1990          # постсоветские страны имеют полные данные с 1990 г.
YEAR_MAX = 2024          # последний год с полными данными OWID
MONTHLY_START = "2018-01-01"
MONTHLY_END = "2025-12-01"   # полные календарные годы; данные 2026 — предварительные оценки
RANDOM_SEED = 42

# --- Страны -----------------------------------------------------------------
TARGET_COUNTRY = "Kazakhstan"

# Группы стран-аналогов для сравнения с Казахстаном.
PEER_GROUPS: dict[str, list[str]] = {
    "Центральная Азия и СНГ": ["Kazakhstan", "Russia", "Uzbekistan", "Azerbaijan", "Turkmenistan", "Kyrgyzstan"],
    "Ресурсные экономики": ["Kazakhstan", "Australia", "Canada", "Norway", "Saudi Arabia", "Iran"],
    "Угольные экономики": ["Kazakhstan", "Poland", "South Africa", "China", "India", "Mongolia"],
    "Крупнейшие эмитенты": ["Kazakhstan", "China", "United States", "India", "Russia", "Japan", "Germany"],
}
# Список всех уникальных стран из групп (с сохранением порядка).
PEER_COUNTRIES: list[str] = list(dict.fromkeys(c for group in PEER_GROUPS.values() for c in group))

# --- Переменные энергобаланса (OWID energy) ---------------------------------
# ключ -> (колонка потребления, TWh; подпись на русском; цвет)
ENERGY_SOURCES: dict[str, dict[str, str]] = {
    "coal": {"column": "coal_consumption", "label": "Уголь", "color": "#4d4d4d"},
    "oil": {"column": "oil_consumption", "label": "Нефть", "color": "#8c564b"},
    "gas": {"column": "gas_consumption", "label": "Газ", "color": "#ff7f0e"},
    "nuclear": {"column": "nuclear_consumption", "label": "Атом", "color": "#9467bd"},
    "hydro": {"column": "hydro_consumption", "label": "Гидро", "color": "#1f77b4"},
    "wind": {"column": "wind_consumption", "label": "Ветер", "color": "#17becf"},
    "solar": {"column": "solar_consumption", "label": "Солнце", "color": "#bcbd22"},
    "biofuel": {"column": "biofuel_consumption", "label": "Биотопливо", "color": "#2ca02c"},
    "other_renewable": {"column": "other_renewable_consumption", "label": "Прочие ВИЭ", "color": "#98df8a"},
}
FOSSIL_SOURCES = ["coal", "oil", "gas"]
LOW_CARBON_SOURCES = ["nuclear", "hydro", "wind", "solar", "biofuel", "other_renewable"]

ENERGY_COLUMNS: list[str] = [
    "population", "gdp", "primary_energy_consumption", "energy_per_capita",
    *[v["column"] for v in ENERGY_SOURCES.values()],
    "fossil_share_energy", "renewables_share_energy", "low_carbon_share_energy",
    "coal_share_energy", "oil_share_energy", "gas_share_energy",
    "electricity_generation", "electricity_demand", "carbon_intensity_elec",
]

# --- Переменные выбросов (OWID co2) -----------------------------------------
CO2_COLUMNS: list[str] = [
    "co2", "co2_per_capita", "co2_per_gdp", "co2_growth_prct",
    "coal_co2", "oil_co2", "gas_co2", "cement_co2", "flaring_co2", "other_industry_co2",
    "consumption_co2", "total_ghg", "methane", "nitrous_oxide",
    "share_global_co2", "cumulative_co2", "temperature_change_from_co2",
]

# Подписи переменных для графиков и дашборда.
VARIABLE_LABELS: dict[str, str] = {
    "co2": "Выбросы CO₂, млн т",
    "co2_per_capita": "CO₂ на душу населения, т/чел",
    "co2_per_gdp": "CO₂ на единицу ВВП, кг/$",
    "primary_energy_consumption": "Первичное энергопотребление, ТВт·ч",
    "energy_per_capita": "Энергопотребление на душу, кВт·ч/чел",
    "fossil_share_energy": "Доля ископаемых источников, %",
    "renewables_share_energy": "Доля ВИЭ, %",
    "low_carbon_share_energy": "Доля низкоуглеродных источников, %",
    "coal_share_energy": "Доля угля, %",
    "carbon_intensity_elec": "Углеродоёмкость электроэнергии, г CO₂/кВт·ч",
    "electricity_generation": "Выработка электроэнергии, ТВт·ч",
    "gdp": "ВВП, $ (ППС, 2011)",
    "population": "Население",
    "oil_price": "Цена нефти, $/баррель",
    "temperature_anomaly": "Температурная аномалия, °C",
    "co2_per_energy": "CO₂ на единицу энергии, т/ТВт·ч",
    "emissions_mtco2": "Выбросы электроэнергетики, Мт CO₂",
    "generation_twh": "Выработка, ТВт·ч",
}

# --- Прогнозирование ---------------------------------------------------------
ANNUAL_HOLDOUT = 8          # последние 8 лет (2017–2024) — hold-out
ANNUAL_CV_SPLITS = 4        # число блоков скользящей кросс-валидации
ANNUAL_CV_TEST_SIZE = 3     # размер тестового блока (лет)
MONTHLY_HOLDOUT = 12        # последние 12 месяцев — hold-out
MONTHLY_CV_SPLITS = 3
MONTHLY_CV_TEST_SIZE = 6
MONTHLY_SEASON = 12         # длина сезона для месячных данных
FUTURE_HORIZON = 6          # горизонт прогноза «в будущее» для дашборда (лет)

# Страны для прогнозной «батареи» (годовой CO₂): аналоги Казахстана.
FORECAST_COUNTRIES: list[str] = PEER_COUNTRIES


def ensure_dirs() -> None:
    """Создать все рабочие каталоги, если их ещё нет."""
    for path in (RAW_DIR, PROCESSED_DIR, FIG_DIR, RESULTS_DIR, DOCS_DIR, QUERIES_DIR):
        path.mkdir(parents=True, exist_ok=True)


# --- Веб-интерфейс (3D-фронтенд) ---------------------------------------------------
WEB_DIR = BASE_DIR / "web"
WEB_HOST = "127.0.0.1"
WEB_PORT = 8000

# Русские названия стран-аналогов для интерфейса (остальные показываются как в OWID).
COUNTRY_NAMES_RU: dict[str, str] = {
    "Kazakhstan": "Казахстан", "Russia": "Россия", "Uzbekistan": "Узбекистан", "Azerbaijan": "Азербайджан",
    "Turkmenistan": "Туркменистан", "Kyrgyzstan": "Кыргызстан", "Australia": "Австралия", "Canada": "Канада",
    "Norway": "Норвегия", "Saudi Arabia": "Саудовская Аравия", "Iran": "Иран", "Poland": "Польша",
    "South Africa": "ЮАР", "China": "Китай", "India": "Индия", "Mongolia": "Монголия",
    "United States": "США", "Japan": "Япония", "Germany": "Германия", "Denmark": "Дания",
    "United Kingdom": "Великобритания", "France": "Франция", "Brazil": "Бразилия", "Qatar": "Катар",
    "Turkey": "Турция", "Ukraine": "Украина", "Belarus": "Беларусь", "Tajikistan": "Таджикистан",
}

# Показатели, которые можно положить на глобус: ключ → подпись, единица, шкала высоты, число знаков.
WEB_METRICS: list[dict[str, object]] = [
    {"key": "co2_per_capita", "label": "CO₂ на человека", "unit": "т", "scale": "linear", "digits": 1},
    {"key": "co2", "label": "Выбросы CO₂", "unit": "млн т", "scale": "sqrt", "digits": 0},
    {"key": "fossil_share_energy", "label": "Доля ископаемых источников", "unit": "%", "scale": "linear", "digits": 1},
    {"key": "low_carbon_share_energy", "label": "Доля низкоуглеродных источников", "unit": "%", "scale": "linear", "digits": 1},
    {"key": "energy_per_capita", "label": "Энергия на человека", "unit": "кВт·ч", "scale": "sqrt", "digits": 0},
]
