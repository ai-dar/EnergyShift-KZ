"""Графики проекта: matplotlib (статические PNG для отчёта) и Plotly (интерактивные HTML).

Правила оформления: фиксированные цвета стран (Казахстан всегда синий), одна ось Y на график,
последовательная одноцветная шкала для карты, расходящаяся шкала с серой серединой для корреляций.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e6e3"
PLOTLY_TEMPLATE = "plotly_white"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 160, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.edgecolor": MUTED,
    "axes.labelcolor": TEXT, "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 10,
    "axes.titleweight": "bold", "legend.frameon": False,
})


def country_colors(countries: list[str]) -> dict[str, str]:
    """Фиксированное соответствие страна → цвет: Казахстан всегда первый (синий)."""
    ordered = [config.TARGET_COUNTRY] + [c for c in countries if c != config.TARGET_COUNTRY]
    colors = {}
    for i, c in enumerate(ordered):
        colors[c] = CATEGORICAL[i % len(CATEGORICAL)]
    return colors


def label(column: str) -> str:
    return config.VARIABLE_LABELS.get(column, column)


def spread_labels(values: dict[str, float], min_gap: float) -> dict[str, float]:
    """Раздвинуть координаты подписей так, чтобы соседние отличались не меньше чем на min_gap."""
    ordered = sorted(values.items(), key=lambda kv: kv[1])
    placed: list[tuple[str, float]] = []
    for name, y in ordered:
        if placed and y - placed[-1][1] < min_gap:
            y = placed[-1][1] + min_gap
        placed.append((name, y))
    return dict(placed)


# --- Сохранение ------------------------------------------------------------------

def save_mpl(fig: plt.Figure, name: str, directory: Path | None = None) -> Path:
    """Сохранить matplotlib-фигуру в PNG."""
    directory = Path(directory or config.FIG_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_plotly(fig: go.Figure, name: str, directory: Path | None = None, png: bool = True) -> dict[str, Path]:
    """Сохранить Plotly-фигуру в HTML (интерактив) и, если доступен kaleido, в PNG."""
    directory = Path(directory or config.FIG_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {"html": directory / f"{name}.html"}
    fig.write_html(paths["html"], include_plotlyjs="cdn", full_html=True)
    if png:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig.write_image(directory / f"{name}.png", width=1100, height=620, scale=2)
            paths["png"] = directory / f"{name}.png"
        except Exception as err:  # kaleido/Chrome могут отсутствовать — это не критично
            print(f"[save_plotly] PNG для {name} не создан: {type(err).__name__}: {str(err)[:80]}")
    return paths


# --- Энергобаланс ----------------------------------------------------------------

def energy_mix_table(panel: pd.DataFrame, country: str) -> pd.DataFrame:
    """Таблица год × источник (ТВт·ч) для стековой диаграммы."""
    sub = panel[panel["country"] == country].set_index("year")
    cols = {v["column"]: v["label"] for v in config.ENERGY_SOURCES.values() if v["column"] in sub.columns}
    mix = sub[list(cols)].rename(columns=cols).dropna(how="all")
    return mix


def plot_energy_mix_plotly(panel: pd.DataFrame, country: str = config.TARGET_COUNTRY, share: bool = False) -> go.Figure:
    """Интерактивная стековая диаграмма энергобаланса страны (ТВт·ч или доли, %)."""
    mix = energy_mix_table(panel, country)
    if share:
        mix = mix.div(mix.sum(axis=1), axis=0) * 100
    fig = go.Figure()
    for key, meta in config.ENERGY_SOURCES.items():
        if meta["label"] not in mix.columns:
            continue
        fig.add_trace(go.Scatter(x=mix.index, y=mix[meta["label"]], name=meta["label"], stackgroup="one",
                                 mode="lines", line=dict(width=0.5, color=meta["color"]),
                                 hovertemplate="%{x}: %{y:.1f}" + (" %" if share else " ТВт·ч") + "<extra>%{fullData.name}</extra>"))
    fig.update_layout(template=PLOTLY_TEMPLATE, title=f"Структура энергопотребления: {country}",
                      xaxis_title="Год", yaxis_title="Доля, %" if share else "Потребление, ТВт·ч",
                      hovermode="x unified", legend=dict(orientation="h", y=-0.2), height=520)
    return fig


def plot_energy_mix_mpl(panel: pd.DataFrame, country: str = config.TARGET_COUNTRY) -> plt.Figure:
    """Статическая версия энергобаланса: абсолютные значения и доли."""
    mix = energy_mix_table(panel, country)
    colors = [meta["color"] for meta in config.ENERGY_SOURCES.values() if meta["label"] in mix.columns]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    axes[0].stackplot(mix.index, mix.T.values, labels=mix.columns, colors=colors, alpha=0.9)
    axes[0].set_title(f"{country}: потребление по источникам, ТВт·ч")
    axes[0].set_xlabel("Год")
    share = mix.div(mix.sum(axis=1), axis=0) * 100
    axes[1].stackplot(share.index, share.T.values, labels=share.columns, colors=colors, alpha=0.9)
    axes[1].set_title(f"{country}: доли источников, %")
    axes[1].set_xlabel("Год")
    axes[1].set_ylim(0, 100)
    axes[1].legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=9)
    fig.tight_layout()
    return fig


# --- Сравнение стран ------------------------------------------------------------

def plot_country_lines(panel: pd.DataFrame, countries: list[str], column: str = "co2_per_capita",
                       title: str | None = None) -> go.Figure:
    """Интерактивные линии показателя по странам; Казахстан выделен толщиной."""
    colors = country_colors(countries)
    fig = go.Figure()
    for c in countries:
        sub = panel[panel["country"] == c].dropna(subset=[column])
        if sub.empty:
            continue
        is_target = c == config.TARGET_COUNTRY
        fig.add_trace(go.Scatter(x=sub["year"], y=sub[column], name=c, mode="lines",
                                 line=dict(width=3.5 if is_target else 1.8, color=colors[c]),
                                 hovertemplate="%{x}: %{y:,.2f}<extra>" + c + "</extra>"))
    fig.update_layout(template=PLOTLY_TEMPLATE, title=title or f"{label(column)}: Казахстан и страны-аналоги",
                      xaxis_title="Год", yaxis_title=label(column), hovermode="x unified", height=520,
                      legend=dict(orientation="h", y=-0.2))
    return fig


def plot_peer_groups_mpl(panel: pd.DataFrame, column: str = "co2_per_capita") -> plt.Figure:
    """Малые кратные: по одной панели на группу стран-аналогов (статический вариант)."""
    groups = config.PEER_GROUPS
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), sharey=False)
    for ax, (group, members) in zip(axes.ravel(), groups.items()):
        colors = country_colors(members)
        ends: dict[str, float] = {}
        for c in members:
            sub = panel[panel["country"] == c].dropna(subset=[column])
            is_target = c == config.TARGET_COUNTRY
            ax.plot(sub["year"], sub[column], color=colors[c], lw=3 if is_target else 1.5, label=c,
                    alpha=1 if is_target else 0.9)
            if not sub.empty:
                ends[c] = float(sub[column].iloc[-1])
        if ends:
            gap = (max(ends.values()) - min(ends.values()) + 1e-9) * 0.045
            for c, y in spread_labels(ends, gap).items():
                ax.annotate(c, (config.YEAR_MAX, ends[c]), xytext=(config.YEAR_MAX + 0.6, y), fontsize=8,
                            color=colors[c], va="center", arrowprops=dict(arrowstyle="-", color=colors[c], lw=0.5, alpha=0.6))
        ax.set_title(group)
        ax.set_xlim(sub["year"].min() if not sub.empty else config.YEAR_MIN, config.YEAR_MAX + 6)
        ax.set_ylabel(label(column))
    fig.suptitle(f"{label(column)}: Казахстан (синий) и страны-аналоги", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_transition_mpl(panel: pd.DataFrame, countries: list[str]) -> plt.Figure:
    """Энергопереход: доля ископаемых источников и доля низкоуглеродных по годам."""
    colors = country_colors(countries)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for col, ax in zip(("fossil_share_energy", "low_carbon_share_energy"), axes):
        for c in countries:
            sub = panel[panel["country"] == c].dropna(subset=[col])
            if sub.empty:
                continue
            is_target = c == config.TARGET_COUNTRY
            ax.plot(sub["year"], sub[col], color=colors[c], lw=3 if is_target else 1.4, label=c)
        ax.set_title(label(col))
        ax.set_xlabel("Год")
        ax.set_ylabel("%")
    axes[1].legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=9)
    fig.suptitle("Энергетический переход: Казахстан и страны-аналоги", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_choropleth(panel: pd.DataFrame, column: str = "co2_per_capita", years: list[int] | None = None,
                    title: str | None = None) -> go.Figure:
    """Интерактивная карта мира с ползунком по годам (одноцветная последовательная шкала)."""
    years = years or list(range(config.YEAR_MIN, config.YEAR_MAX + 1, 2)) + [config.YEAR_MAX]
    sub = panel[panel["year"].isin(sorted(set(years)))].dropna(subset=[column]).sort_values("year")
    vmax = float(sub[column].quantile(0.97))
    fig = px.choropleth(sub, locations="iso_code", color=column, hover_name="country", animation_frame="year",
                        color_continuous_scale="Blues", range_color=(0, vmax), projection="natural earth",
                        labels={column: label(column), "year": "Год"},
                        title=title or f"{label(column)} по странам (ползунок — год)")
    fig.update_layout(template=PLOTLY_TEMPLATE, height=600, margin=dict(l=10, r=10, t=60, b=10),
                      coloraxis_colorbar=dict(title=label(column)))
    # По умолчанию показываем последний год.
    if fig.layout.sliders:
        fig.layout.sliders[0].active = len(fig.frames) - 1
        last = fig.frames[-1]
        fig.update_traces(z=last.data[0].z, locations=last.data[0].locations, hovertext=last.data[0].hovertext,
                          customdata=last.data[0].customdata)
    return fig


# --- Корреляции -----------------------------------------------------------------

def plot_corr_heatmap(corr: pd.DataFrame, title: str = "Корреляции") -> plt.Figure:
    """Тепловая карта корреляций: расходящаяся шкала с серой серединой."""
    labels = [label(c) for c in corr.columns]
    fig, ax = plt.subplots(figsize=(max(7, 0.65 * len(labels) + 2), max(6, 0.55 * len(labels) + 1.5)))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.grid(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = corr.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(v) > 0.6 else TEXT)
    fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label="коэффициент корреляции")
    ax.set_title(title)
    fig.tight_layout()
    return fig


def plot_scatter_cross_section(panel: pd.DataFrame, year: int, x: str = "gdp_per_capita",
                               y: str = "co2_per_capita", size: str = "population") -> go.Figure:
    """Интерактивная диаграмма рассеяния «ВВП на душу — CO₂ на душу» (размер — население)."""
    sub = panel[(panel["year"] == year)].dropna(subset=[x, y, size])
    sub = sub.assign(highlight=np.where(sub["country"] == config.TARGET_COUNTRY, "Казахстан", "Другие страны"))
    fig = px.scatter(sub, x=x, y=y, size=size, hover_name="country", color="highlight", log_x=True,
                     color_discrete_map={"Казахстан": CATEGORICAL[1], "Другие страны": CATEGORICAL[0]},
                     labels={x: label(x), y: label(y), "highlight": ""}, size_max=45,
                     title=f"{label(y)} против {label(x)}, {year} г. (размер — население)")
    fig.update_layout(template=PLOTLY_TEMPLATE, height=520)
    return fig


# --- Временные ряды ---------------------------------------------------------------

def plot_rolling_mpl(rolling: pd.DataFrame, title: str, ylabel: str) -> plt.Figure:
    """Ряд и скользящие средние."""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(rolling.index, rolling["value"], color=CATEGORICAL[0], lw=2, label="значение")
    for i, col in enumerate([c for c in rolling.columns if c.startswith("ma_")], start=1):
        ax.plot(rolling.index, rolling[col], color=CATEGORICAL[i], lw=1.6, ls="--", label=f"скользящее среднее {col[3:]}")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_stl_mpl(stl: pd.DataFrame, title: str) -> plt.Figure:
    """Четыре панели STL: наблюдения, тренд, сезонность, остаток."""
    fig, axes = plt.subplots(4, 1, figsize=(11, 8), sharex=True)
    for ax, col, name in zip(axes, ("observed", "trend", "seasonal", "resid"), ("Ряд", "Тренд", "Сезонность", "Остаток")):
        if col == "resid":
            ax.bar(stl.index, stl[col], width=20, color=CATEGORICAL[0])
        else:
            ax.plot(stl.index, stl[col], color=CATEGORICAL[0], lw=1.8)
        ax.set_ylabel(name)
    strength = stl.attrs.get("seasonal_strength")
    extra = f" (сила сезонности {strength:.2f}, период {stl.attrs.get('period')})" if strength is not None else ""
    axes[0].set_title(title + extra)
    fig.tight_layout()
    return fig


def plot_acf_pacf_mpl(acf_df: pd.DataFrame, title: str) -> plt.Figure:
    """ACF и PACF с доверительной полосой."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    bound = float(acf_df["conf_bound"].iloc[0])
    for ax, col, name in zip(axes, ("acf", "pacf"), ("ACF", "PACF")):
        ax.bar(acf_df["lag"], acf_df[col], width=0.35, color=CATEGORICAL[0])
        ax.axhspan(-bound, bound, color=CATEGORICAL[0], alpha=0.12)
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_title(f"{name}: {title}")
        ax.set_xlabel("лаг")
    fig.tight_layout()
    return fig


# --- Прогнозы --------------------------------------------------------------------

def plot_forecast_plotly(series: pd.Series, forecasts: pd.DataFrame, models: list[str] | None = None,
                         title: str = "Прогноз", ylabel: str = "", future: pd.DataFrame | None = None) -> go.Figure:
    """Факт + прогнозы моделей на hold-out (+ прогноз в будущее с интервалом)."""
    models = models or list(forecasts["model"].unique())
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, name="Факт", mode="lines",
                             line=dict(color=TEXT, width=2.5)))
    order = ["Naive", "Seasonal naive", "Drift", "Linear trend", "ETS", "ARIMA", "Lag LR", "Lag GBM"]
    for m in models:
        sub = forecasts[forecasts["model"] == m]
        if sub.empty:
            continue
        color = CATEGORICAL[order.index(m) % len(CATEGORICAL)] if m in order else MUTED   # цвет закреплён за моделью
        fig.add_trace(go.Scatter(x=sub["date"], y=sub["y_pred"], name=m, mode="lines+markers",
                                 line=dict(color=color, width=1.8, dash="dot" if m in ("Naive", "Seasonal naive", "Drift") else "solid"),
                                 marker=dict(size=6)))
    if future is not None and not future.empty:
        fig.add_trace(go.Scatter(x=pd.concat([future["date"], future["date"][::-1]]),
                                 y=pd.concat([future["upper"], future["lower"][::-1]]), fill="toself", mode="lines",
                                 fillcolor="rgba(42,120,214,0.15)", line=dict(width=0), name="интервал ±1.96σ√k", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=future["date"], y=future["forecast"], name="Прогноз (будущее)", mode="lines+markers",
                                 line=dict(color=CATEGORICAL[0], width=2.5, dash="dash")))
    if not forecasts.empty:
        fig.add_vline(x=pd.Timestamp(forecasts["date"].min()) - pd.Timedelta(days=1), line=dict(color=MUTED, dash="dash"))
    fig.update_layout(template=PLOTLY_TEMPLATE, title=title, yaxis_title=ylabel,
                      hovermode="x unified", height=540, legend=dict(orientation="h", y=-0.12),
                      margin=dict(b=110))
    return fig


def plot_model_comparison_mpl(metrics: pd.DataFrame, title: str) -> plt.Figure:
    """Сравнение моделей: качество (MASE, sMAPE) и время обучения — три отдельные панели, одна ось в каждой."""
    df = metrics.dropna(subset=["MASE"]).sort_values("MASE")
    colors = [CATEGORICAL[3] if b else CATEGORICAL[0] for b in df["is_baseline"]]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4))
    for ax, col, name in zip(axes, ("MASE", "sMAPE", "train_time_s"), ("MASE (меньше — лучше)", "sMAPE, %", "Время обучения, с")):
        ax.barh(df["model"], df[col], color=colors, height=0.6)
        ax.invert_yaxis()
        ax.set_title(name)
        for y, v in enumerate(df[col]):
            ax.text(v, y, f" {v:.3g}", va="center", fontsize=8, color=TEXT)
        if col == "train_time_s" and df[col].max() > 0:
            ax.set_xscale("symlog", linthresh=0.01)
    axes[0].axvline(1, color=MUTED, ls="--", lw=1)
    fig.suptitle(title + " (жёлтый — baseline)", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_error_heatmap_mpl(forecasts: pd.DataFrame, title: str, by: str = "horizon") -> plt.Figure:
    """Тепловая карта |ошибки|, %: модель × период горизонта (или × серия)."""
    df = forecasts.copy()
    df["ape"] = (df["y_pred"] - df["y_true"]).abs() / df["y_true"].abs().replace(0, np.nan) * 100
    if by == "horizon":
        df["col"] = pd.to_datetime(df["date"]).dt.strftime("%Y" if df["series"].nunique() == 1 and df["date"].nunique() <= 12 else "%Y-%m")
        table = df.pivot_table(index="model", columns="col", values="ape", aggfunc="mean")
    else:
        table = df.pivot_table(index="model", columns="series", values="ape", aggfunc="mean")
    table = table.loc[table.mean(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(max(8, 0.6 * table.shape[1] + 3), 0.45 * table.shape[0] + 2))
    im = ax.imshow(table.values, cmap="Blues", aspect="auto", vmin=0, vmax=np.nanpercentile(table.values, 95))
    ax.set_xticks(range(table.shape[1]), table.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(table.shape[0]), table.index, fontsize=9)
    ax.grid(False)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            v = table.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=7, color="white" if v > np.nanpercentile(table.values, 70) else TEXT)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="|ошибка|, %")
    ax.set_title(title)
    fig.tight_layout()
    return fig


def plot_series_errors_mpl(rank: pd.DataFrame, title: str) -> plt.Figure:
    """Средний ранг моделей по сериям (странам)."""
    df = rank.sort_values("mean_rank")
    colors = [CATEGORICAL[3] if b else CATEGORICAL[0] for b in df["is_baseline"]]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(df.index, df["mean_rank"], color=colors, height=0.6)
    ax.invert_yaxis()
    ax.set_xlabel("средний ранг по MASE (1 — лучшая)")
    ax.set_title(title + " (жёлтый — baseline)")
    for y, v in enumerate(df["mean_rank"]):
        ax.text(v, y, f" {v:.2f}", va="center", fontsize=8)
    fig.tight_layout()
    return fig


def plot_benchmark_mpl(formats: pd.DataFrame, pandas_sql: pd.DataFrame) -> plt.Figure:
    """Сравнение форматов (размер, время чтения) и Pandas vs SQL (время)."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    axes[0].bar(formats["format"], formats["size_mb"], color=CATEGORICAL[0], width=0.55)
    axes[0].set_title("Размер файла, МБ")
    axes[1].bar(formats["format"], formats["read_s_mean"], color=CATEGORICAL[0], width=0.55)
    axes[1].set_title("Среднее время чтения, с")
    for ax in axes[:2]:
        ax.tick_params(axis="x", labelsize=8)
    piv = pandas_sql.pivot(index="task", columns="approach", values="mean_ms")
    x = np.arange(len(piv))
    axes[2].bar(x - 0.18, piv["Pandas"], width=0.36, color=CATEGORICAL[0], label="Pandas")
    axes[2].bar(x + 0.18, piv["SQLite"], width=0.36, color=CATEGORICAL[1], label="SQLite")
    axes[2].set_xticks(x, [t[:28] for t in piv.index], rotation=15, ha="right", fontsize=8)
    axes[2].set_title("Pandas vs SQLite: среднее время, мс")
    axes[2].legend()
    fig.tight_layout()
    return fig


def plot_missing_mpl(missing_by_year: pd.DataFrame, variables: list[str]) -> plt.Figure:
    """Доля пропусков по годам для ключевых переменных."""
    df = missing_by_year.set_index("year")[[v for v in variables if v in missing_by_year.columns]]
    fig, ax = plt.subplots(figsize=(11, 0.4 * df.shape[1] + 2))
    im = ax.imshow(df.T.values, cmap="Blues", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(range(len(df.index))[::2], df.index[::2], rotation=90, fontsize=8)
    ax.set_yticks(range(df.shape[1]), [label(c) for c in df.columns], fontsize=8)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02, label="пропуски, %")
    ax.set_title("Доля пропусков по годам (панель стран)")
    fig.tight_layout()
    return fig
