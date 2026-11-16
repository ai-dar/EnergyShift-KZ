"""Сборка презентации docs/presentation.pptx (python-pptx). Числа берутся из outputs/results/*.json."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "outputs" / "figures"
RES = ROOT / "outputs" / "results"
DOCS = ROOT / "docs"

INK = RGBColor(0x1E, 0x22, 0x2B)        # графит — основной тёмный
EMBER = RGBColor(0xE8, 0x69, 0x2C)      # акцент «тлеющий уголь»
KZ = RGBColor(0x2A, 0x78, 0xD6)         # Казахстан на всех графиках
MUTED = RGBColor(0x5A, 0x5F, 0x6A)
TINT = RGBColor(0xF2, 0xF4, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD, BODY = "Cambria", "Calibri"
W, H = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]
fs = json.loads((RES / "forecast_summary.json").read_text(encoding="utf-8"))
bench = json.loads((RES / "benchmark_summary.json").read_text(encoding="utf-8"))


def text_box(slide, x, y, w, h, paragraphs, size=16, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, bullets=False, space_after=6, name=None):
    """Текстовое поле; paragraphs — строка или список строк/кортежей (текст, {опции})."""
    box = slide.shapes.add_textbox(x, y, w, h)
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    items = [paragraphs] if isinstance(paragraphs, str) else paragraphs
    for i, item in enumerate(items):
        text, opts = (item, {}) if isinstance(item, str) else item
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        if bullets and not opts.get("no_bullet"):
            pPr = p._p.get_or_add_pPr()
            pPr.set("marL", str(Emu(Inches(0.25)))); pPr.set("indent", str(-Emu(Inches(0.22))))
            bu = pPr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}buChar", {"char": "•"})
            pPr.append(bu)
        run = p.add_run()
        run.text = text
        f = run.font
        f.name = opts.get("font", font); f.size = Pt(opts.get("size", size)); f.bold = opts.get("bold", bold)
        f.italic = opts.get("italic", False); f.color.rgb = opts.get("color", color)
    return box


def title(slide, text, dark=False):
    text_box(slide, Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.9), text, size=32, font=HEAD, bold=True,
             color=WHITE if dark else INK, anchor=MSO_ANCHOR.MIDDLE, name="Title")


def background(slide, color):
    fill = slide.background.fill
    fill.solid(); fill.fore_color.rgb = color


def picture(slide, path, x, y, w, h, name=None):
    """Вставить картинку, вписав её в прямоугольник с сохранением пропорций (по центру)."""
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = int(iw * scale), int(ih * scale)
    pic = slide.shapes.add_picture(str(path), x + (w - pw) // 2, y + (h - ph) // 2, pw, ph)
    if name:
        pic.name = name
    return pic


def card(slide, x, y, w, h, fill=TINT):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shp.adjustments[0] = 0.06
    shp.fill.solid(); shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def stat(slide, x, y, w, value, label, color=EMBER, dark=False):
    text_box(slide, x, y, w, Inches(0.85), value, size=40, font=HEAD, bold=True, color=color)
    text_box(slide, x, y + Inches(0.85), w, Inches(0.7), label, size=13, color=WHITE if dark else MUTED)


def ru(value: float, digits: int = 1) -> str:
    """Число с десятичной запятой."""
    return f"{value:.{digits}f}".replace(".", ",")


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def caption(slide, text, y=Inches(6.95)):
    text_box(slide, Inches(0.6), y, Inches(12.1), Inches(0.4), text, size=11, color=MUTED)


def bar_chart(slide, x, y, w, h, categories, series, number_format="0.0", colors=None, title_text=None, legend=False):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, x, y, w, h, data)
    chart = gf.chart
    chart.font.name = BODY; chart.font.size = Pt(12); chart.font.color.rgb = MUTED
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM; chart.legend.include_in_layout = False
    if title_text:
        chart.has_title = True
        chart.chart_title.text_frame.text = title_text
        tp = chart.chart_title.text_frame.paragraphs[0]
        tp.runs[0].font.size = Pt(14); tp.runs[0].font.bold = True; tp.runs[0].font.color.rgb = INK
    va = chart.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = RGBColor(0xE3, 0xE5, 0xE8)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(11)
    ca = chart.category_axis
    ca.reverse_order = True
    ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW   # подписи слева даже при отрицательных значениях
    ca.format.line.color.rgb = RGBColor(0xC8, 0xCB, 0xD0)
    ca.tick_labels.font.size = Pt(12)
    plot = chart.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = number_format; dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(11); dl.font.color.rgb = INK
    for i, s in enumerate(plot.series):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = (colors or [KZ, EMBER])[i % len(colors or [KZ, EMBER])]
    return chart


# 1. Титул -------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); background(s, INK)
text_box(s, Inches(0.8), Inches(1.0), Inches(11.5), Inches(0.5), "ИТОГОВЫЙ ПРОЕКТ · ТЕМА 60 · GLOBAL ENERGY MIX AND CO₂ EMISSIONS", size=14, color=EMBER, bold=True)
text_box(s, Inches(0.8), Inches(1.5), Inches(11.5), Inches(2.0), "EnergyShift KZ", size=54, font=HEAD, bold=True, color=WHITE)
text_box(s, Inches(0.8), Inches(3.0), Inches(11.5), Inches(1.0), "Казахстан на карте мирового энергоперехода: энергобаланс, выбросы CO₂ и прогноз против наивного baseline", size=20, color=RGBColor(0xC9, 0xCD, 0xD6))
text_box(s, Inches(0.8), Inches(5.3), Inches(11.5), Inches(1.2), [
    ("Aidar · Daniyal · Nurzhan — группа AAI-2604", {"size": 18, "color": WHITE, "bold": True}),
    ("Programming for Data Analysis and Database · Applied Artificial Intelligence, магистратура · 2026", {"size": 14, "color": RGBColor(0xC9, 0xCD, 0xD6)}),
])
notes(s, "Представление команды и темы. Тема 60 из кластера 10 Forecasting & Open Data Analytics.")

# 2. Вопросы и данные -------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Четыре вопроса и открытые данные")
text_box(s, Inches(0.6), Inches(1.45), Inches(6.2), Inches(4.8), [
    ("Как устроен энергобаланс Казахстана и как он менялся с 1990 г.?", {}),
    ("Где Казахстан по выбросам CO₂ среди 204 стран и трёх групп аналогов?", {}),
    ("Какие внешние факторы связаны с динамикой выбросов: нефть, климат, экономика?", {}),
    ("Можно ли прогнозировать выбросы точнее, чем «завтра как сегодня», и какой ценой?", {}),
], size=18, bullets=True, space_after=14)
card(s, Inches(7.2), Inches(1.45), Inches(5.5), Inches(4.9))
stat(s, Inches(7.5), Inches(1.65), Inches(2.5), "204", "страны × 35 лет (1990–2024), OWID Energy + CO₂")
stat(s, Inches(10.1), Inches(1.65), Inches(2.5), "88", "стран с месячными данными Ember, 2018–2025")
stat(s, Inches(7.5), Inches(3.8), Inches(2.5), "2,7 млн", "строк в «длинном» формате, собранном чанками")
stat(s, Inches(10.1), Inches(3.8), Inches(2.5), "4", "внешних фактора: цена нефти, температура, ВВП, население")
caption(s, "Источники: github.com/owid/energy-data · github.com/owid/co2-data · ember-energy.org · ourworldindata.org/grapher")
notes(s, "Годовые данные OWID дают сравнение стран, месячные данные Ember — сезонность для STL и seasonal naive.")

# 3. Архитектура ----------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Архитектура: один пакет, четыре интерфейса")
steps = ["Загрузка", "Очистка\nи Parquet", "EDA", "Временные\nряды", "SQLite\nи SQL", "Прогноз", "Корреляции\nи графики"]
for i, label in enumerate(steps):
    x = Inches(0.6 + i * 1.76)
    shp = card(s, x, Inches(1.5), Inches(1.55), Inches(1.0), fill=INK if i != 5 else EMBER)
    tf = shp.text_frame; tf.text = label
    for p in tf.paragraphs:
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = BODY
    if i < len(steps) - 1:
        arrow = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + Inches(1.58), Inches(1.88), Inches(0.16), Inches(0.24))
        arrow.fill.solid(); arrow.fill.fore_color.rgb = MUTED; arrow.line.fill.background()
cols = [
    ("energy_co2/ — 12 модулей", ["config · io_utils · cleaning · eda", "timeseries · metrics · forecasting", "correlation · benchmark · database", "visualization · pipeline", "90+ функций, реестр моделей"]),
    ("Интерфейсы", ["main.py — консольное меню, 15 пунктов", "app.py — Streamlit: фильтры и прогноз", "web/server.py — 3D-фронтенд на FastAPI", "Final_Project.ipynb — выполненный ноутбук"]),
    ("Хранение и проверка", ["Parquet: панель, месячные, факторы", "SQLite: 7 таблиц, 12 запросов", "CSV/JSON: метрики, прогнозы, сводки", "pytest: 28 тестов, try/except на вводе"]),
]
for i, (head, items) in enumerate(cols):
    x = Inches(0.6 + i * 4.12)
    card(s, x, Inches(2.95), Inches(3.9), Inches(3.6))
    text_box(s, x + Inches(0.2), Inches(3.1), Inches(3.5), Inches(0.5), head, size=18, bold=True, font=HEAD)
    text_box(s, x + Inches(0.2), Inches(3.65), Inches(3.5), Inches(2.8), items, size=15, bullets=True, space_after=8)
notes(s, "Каждый шаг — функция в pipeline.py. Меню, дашборд и ноутбук вызывают одни и те же функции, поэтому результат воспроизводим.")

# 4. Очистка и Parquet -----------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Очистка панели: от 314 сущностей к 204 странам")
text_box(s, Inches(0.6), Inches(1.45), Inches(6.6), Inches(5.2), [
    ("Агрегаты без ISO-кода удалены: World, Asia, OECD — 94 сущности", {}),
    ("Период 1990–2024: постсоветские страны полны с 1990 г.", {}),
    ("Energy + CO₂ объединены по стране и году, validate one_to_one", {}),
    ("Пропуски ≤ 2 лет — интерполяция только внутри ряда, края не трогаем", {}),
    ("На душу: CO₂·10⁶/население — совпало с OWID до округления", {}),
    ("Страны с < 20 годами данных удалены → 7 140 строк × 49 колонок", {}),
    ("Ember: 88 стран × 96 месяцев, данные 2026 г. исключены", {}),
], size=16, bullets=True, space_after=10)
card(s, Inches(7.6), Inches(1.45), Inches(5.1), Inches(5.1))
fmt = {r["format"]: r for r in bench["formats"]}
ratio = fmt["CSV"]["size_mb"] / fmt["Parquet (snappy)"]["size_mb"]
stat(s, Inches(7.9), Inches(1.65), Inches(4.6), f"в {ratio:.0f} раз", f"Parquet меньше CSV: {fmt['Parquet (snappy)']['size_mb']:.1f} против {fmt['CSV']['size_mb']:.0f} МБ на 2,7 млн строк".replace(".", ","))
stat(s, Inches(7.9), Inches(3.25), Inches(4.6), "−51 %", "памяти после float32 и category: 23,5 → 11,5 МБ")
stat(s, Inches(7.9), Inches(4.85), Inches(4.6), "5 000", "строк в чанке при сборке длинного формата из обоих файлов OWID")
notes(s, "Тема в списке исключений по объёму, но чанки, оптимизация типов и Parquet реализованы и измерены.")

# 5. EDA -----------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "EDA: полные ряды, пропуски в энергобалансе")
picture(s, FIG / "eda_missing_by_year.png", Inches(0.5), Inches(1.4), Inches(7.6), Inches(5.3))
text_box(s, Inches(8.4), Inches(1.5), Inches(4.4), Inches(5.2), [
    ("204 из 204 годовых и 88 из 88 месячных рядов регулярны: без пропущенных периодов и дубликатов", {}),
    ("61 % строк без структуры энергобаланса: источник покрывает ~80 крупных экономик", {}),
    ("CO₂ и население заполнены почти полностью, ВВП отстаёт на два года", {}),
    ("Выбросы ищем в годовых изменениях: IQR −16…+21 %, 605 случаев; z-score — 19", {}),
    ("Кувейт 1991 и нефть Экваториальной Гвинеи — реальные события, не удаляем", {}),
], size=15, bullets=True, space_after=10)
notes(s, "Выбросы в уровнях дали бы просто крупные страны, поэтому проверяем приросты.")

# 6. Энергобаланс Казахстана ---------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Казахстан: 95 % энергии — уголь, нефть и газ")
picture(s, FIG / "energy_mix_kazakhstan_mpl.png", Inches(0.4), Inches(1.35), Inches(8.6), Inches(4.3))
for i, (v, l) in enumerate([("94,9 %", "ископаемые источники в 2024 г. (97,6 % в 1990 г.)"), ("48 %", "доля угля; газ вырос с 15 до 24 %"), ("5,1 %", "низкоуглеродные: гидро 3 %, ветер и солнце 2 %")]):
    stat(s, Inches(9.4), Inches(1.35 + i * 1.5), Inches(3.5), v, l)
text_box(s, Inches(0.6), Inches(6.3), Inches(12.1), Inches(0.8), "Выбросы: 267 млн т (1990) → 119 (1999) → пик 330 (2018) → 287 млн т (2024), 0,8 % мировых", size=17, bold=True)
notes(s, "Структура почти не изменилась за 35 лет. Ветер и солнце появились только после 2019 г.")

# 7. Аналоги ---------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "13,9 т CO₂ на человека: 10-е место в мире")
picture(s, FIG / "co2_per_capita_peer_groups.png", Inches(0.4), Inches(1.35), Inches(8.0), Inches(5.5))
rows = [("Центральная Азия и СНГ", "1-е", "Россия 12,3 · Узбекистан 3,8"), ("Угольные экономики", "1-е", "Монголия 12,9 · Китай 8,6"),
        ("Ресурсные экономики", "3-е", "Саудовская Аравия 20,4 · Австралия 14,5"), ("Крупнейшие эмитенты", "2-е", "США 14,2 · Германия 6,7")]
for i, (g, r, peers) in enumerate(rows):
    y = Inches(1.45 + i * 1.32)
    card(s, Inches(8.7), y, Inches(4.1), Inches(1.15))
    text_box(s, Inches(8.85), y + Inches(0.08), Inches(1.0), Inches(1.0), r, size=30, font=HEAD, bold=True, color=EMBER, anchor=MSO_ANCHOR.MIDDLE)
    text_box(s, Inches(9.85), y + Inches(0.12), Inches(2.9), Inches(0.45), g, size=15, bold=True)
    text_box(s, Inches(9.85), y + Inches(0.55), Inches(2.9), Inches(0.5), peers, size=12, color=MUTED)
caption(s, "Место Казахстана по CO₂ на душу внутри групп, 2024 г.; в мире — 10-е из 157 стран с населением ≥ 1 млн (SQL-запрос 04)")
notes(s, "Казахстан синий на всех графиках. Душевые выбросы на уровне Австралии и Канады, выше Китая и Германии.")

# 8. Энергопереход и карта ---------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Энергопереход не начался: 70-е место из 79")
picture(s, FIG / "map_co2_per_capita.png", Inches(0.4), Inches(1.35), Inches(7.4), Inches(4.6))
bar_chart(s, Inches(8.0), Inches(1.3), Inches(4.9), Inches(4.8),
          ["Дания", "Португалия", "Финляндия", "Ирландия", "Узбекистан", "Россия", "Казахстан"],
          [("Изменение доли ископаемых, п.п.", (-35.0, -27.3, -26.5, -20.3, -1.8, -0.4, 0.6))],
          number_format="+0.0;−0.0", colors=[KZ], title_text="Доля ископаемых, 2000→2024, п.п.")
caption(s, "Слева — кадр интерактивной карты Plotly с ползунком по годам (map_co2_per_capita.html). Справа — SQL-запрос 09 (CTE, FIRST_VALUE, RANK).", y=Inches(6.2))
notes(s, "Доля ископаемых у Казахстана выросла на 0,6 п.п., у лидеров упала на 20–35 п.п. Карта интерактивная — покажем в дашборде.")

# 9. Временные ряды -----------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Ряды: годовой нестационарен, месячный сезонен")
picture(s, FIG / "ts_stl_monthly.png", Inches(0.4), Inches(1.35), Inches(6.9), Inches(5.5))
tbl = s.shapes.add_table(5, 4, Inches(7.6), Inches(1.5), Inches(5.2), Inches(2.6)).table
data = [["Ряд", "ADF p", "KPSS p", "Вывод"], ["Годовой CO₂", "0,205", "0,041", "нестационарен"], ["Годовой, Δ1", "0,368", "0,100", "мало данных"],
        ["Месячный", "0,989", "0,100", "тренд + сезон"], ["Месячный, Δ1 Δ12", "0,004", "0,100", "стационарен"]]
for r, row in enumerate(data):
    for c, v in enumerate(row):
        cell = tbl.cell(r, c); cell.text = v
        para = cell.text_frame.paragraphs[0]; run = para.runs[0]
        run.font.size = Pt(13); run.font.name = BODY; run.font.bold = r == 0
        run.font.color.rgb = WHITE if r == 0 else INK
        cell.fill.solid(); cell.fill.fore_color.rgb = INK if r == 0 else (TINT if r % 2 else WHITE)
tbl.columns[0].width = Inches(1.75); tbl.columns[1].width = Inches(0.8); tbl.columns[2].width = Inches(0.85); tbl.columns[3].width = Inches(1.8)
text_box(s, Inches(7.6), Inches(4.4), Inches(5.2), Inches(2.4), [
    ("Сила сезонности STL 0,94: зима 9,0 Мт против 6,7 Мт в июне (+35 %)", {}),
    ("Пик ACF на лаге 12 → seasonal naive и SARIMA с m = 12", {}),
    ("Годовой ряд: ARIMA на первых разностях", {}),
], size=15, bullets=True, space_after=8)
notes(s, "ADF — H0 единичный корень, KPSS — H0 стационарность. Комбинация двух тестов даёт вывод.")

# 10. Годовой прогноз ------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Годовой прогноз: naive не уступил трендам")
picture(s, FIG / "forecast_annual_kazakhstan.png", Inches(0.3), Inches(1.3), Inches(7.6), Inches(4.4))
kz = {r["model"]: r for r in fs["annual"]["kazakhstan_holdout"]}
order = ["Naive", "ARIMA", "Linear trend", "Drift", "ETS", "Lag GBM", "Lag LR"]
ch = bar_chart(s, Inches(8.1), Inches(1.3), Inches(4.8), Inches(4.5), order, [("MAPE, %", tuple(round(kz[m]["MAPE"], 1) for m in order))],
               colors=[KZ], title_text="MAPE на hold-out 2017–2024, %")
for idx, m in enumerate(order):
    if m in ("Naive", "Drift"):
        pt = ch.plots[0].series[0].points[idx]; pt.format.fill.solid(); pt.format.fill.fore_color.rgb = EMBER
fut = fs["annual"]["future"][-1]
text_box(s, Inches(0.6), Inches(5.9), Inches(12.2), Inches(1.0), [
    ("Выбросы вышли на плато, а модели на лагах экстраполировали рост 2000–2016 гг. Оранжевые столбцы — baseline.", {"size": 15}),
    (f"Прогноз на 2030 г. ({fs['annual']['selected_model']}, лучшая сумма рангов hold-out и CV): {fut['forecast']:.0f} млн т [{fut['lower']:.0f}; {fut['upper']:.0f}], naive — {fs['annual']['future_naive_value']:.0f}", {"size": 15, "bold": True}),
])
notes(s, "Хронологический hold-out 8 лет и TimeSeriesSplit 4 блока по 3 года. В CV лучший Lag LR, на hold-out — Naive, поэтому выбор по сумме рангов.")

# 11. Месячный прогноз и серии ---------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Месячный прогноз: сезонность решает")
picture(s, FIG / "forecast_monthly_kazakhstan.png", Inches(0.3), Inches(1.3), Inches(7.6), Inches(4.4))
km = {r["model"]: r for r in fs["monthly"]["kazakhstan_holdout"]}
order_m = ["ARIMA", "Lag LR", "Seasonal naive", "ETS", "Lag GBM", "Linear trend", "Naive"]
ch = bar_chart(s, Inches(8.1), Inches(1.3), Inches(4.8), Inches(4.5), order_m, [("MAPE, %", tuple(round(km[m]["MAPE"], 1) for m in order_m))],
               colors=[KZ], title_text="MAPE на hold-out 2025, %")
for idx, m in enumerate(order_m):
    if m in ("Naive", "Seasonal naive"):
        pt = ch.plots[0].series[0].points[idx]; pt.format.fill.solid(); pt.format.fill.fore_color.rgb = EMBER
arima_t = km["ARIMA"]["train_time_s"]; ets_t = km["ETS"]["train_time_s"]
text_box(s, Inches(0.6), Inches(5.9), Inches(12.2), Inches(1.0), [
    (f"SARIMA точнее всех, но обучается {ru(arima_t, 1)} с против {ru(ets_t, 2)} с у ETS. В CV ARIMA и ETS на 26 % лучше seasonal naive.", {"size": 15}),
    (f"По 16 странам средний ранг: ETS и seasonal naive 2,6, ARIMA 3,1, naive 6,6. Прогноз на 2026 г.: {ru(fs['monthly']['future_2026_total'], 1)} Мт.", {"size": 15, "bold": True}),
])
notes(s, "MASE учитывает масштаб, поэтому страны сравниваем по среднему рангу MASE.")

# 12. Корреляции ----------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Выбросы растут с экономикой, а не с ценой нефти")
bar_chart(s, Inches(0.5), Inches(1.4), Inches(6.4), Inches(4.6), ["ВВП", "Население", "Цена нефти", "Температура"],
          [("По уровням", (0.84, 0.80, 0.57, 0.66)), ("По годовым приростам", (0.57, 0.40, 0.17, 0.24))],
          number_format="0.00", colors=[RGBColor(0xB8, 0xBE, 0xC8), KZ], title_text="Корреляция с CO₂ Казахстана (Пирсон)", legend=True)
text_box(s, Inches(7.3), Inches(1.5), Inches(5.5), Inches(5.0), [
    ("По уровням всё «связано» со всем: растущие ряды дают ложную корреляцию", {}),
    ("По приростам остаётся экономика: ВВП r = 0,57, с лагом в год 0,59", {}),
    ("Цена нефти — слабо и с лагом (0,31), температура — не влияет", {}),
    ("Мир: прирост выбросов синхронен с ценой нефти (0,70) — общий деловой цикл", {}),
    ("Между странами решает объём: энергия на душу ρ = 0,90, ВВП на душу 0,65, доля угля −0,10", {}),
], size=16, bullets=True, space_after=12)
notes(s, "Разности убирают общий тренд. Межстрановой срез — 2022 г., последний год с полными данными по ВВП.")

# 13. БД и SQL ------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "SQLite: 7 таблиц, 12 запросов, результаты в Pandas")
picture(s, DOCS / "er_diagram.png", Inches(0.3), Inches(1.3), Inches(6.8), Inches(5.6))
text_box(s, Inches(7.4), Inches(1.4), Inches(5.5), Inches(5.4), [
    ("JOIN трёх таблиц — углеродоёмкость энергии Казахстана", {}),
    ("GROUP BY + HAVING — ВИЭ и CO₂ по континентам", {}),
    ("Подзапросы — 71 страна выше среднего, Казахстан ×3,1", {}),
    ("CTE — аналоги по десятилетиям, мир против цены нефти", {}),
    ("RANK, LAG, AVG/SUM OVER, FIRST/LAST_VALUE", {}),
    ("ROW_NUMBER — лучшая модель по каждой стране", {}),
    ("model_metrics: 280 строк, forecast_results: 2 752", {}),
], size=16, bullets=True, space_after=10)
notes(s, "Все запросы в sql/queries, выполняются из меню (пункт 12) и из дашборда, результаты сохраняются в CSV.")

# 14. Сравнение подходов -----------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Сравнение подходов: время, память, размер")
bar_chart(s, Inches(0.5), Inches(1.4), Inches(6.0), Inches(2.6), ["CSV", "Parquet snappy", "Parquet gzip"],
          [("МБ", tuple(fmt[k]["size_mb"] for k in ("CSV", "Parquet (snappy)", "Parquet (gzip)")))], number_format="0.0", colors=[KZ],
          title_text="Размер файла, 2,7 млн строк, МБ")
bar_chart(s, Inches(0.5), Inches(4.15), Inches(6.0), Inches(2.6), ["CSV", "Parquet snappy", "Parquet gzip"],
          [("МБ", tuple(fmt[k]["loaded_memory_mb"] for k in ("CSV", "Parquet (snappy)", "Parquet (gzip)")))], number_format="0", colors=[KZ],
          title_text="Память после загрузки, МБ")
pvs = {(r["task"], r["approach"]): r["mean_ms"] for r in bench["pandas_vs_sql"]}
tasks = sorted({t for t, _ in pvs})
labels = {t: ("Агрегация по странам" if t.startswith("avg") else "Топ-10 с сортировкой" if t.startswith("top") else "Годовой прирост, LAG / diff") for t in tasks}
bar_chart(s, Inches(6.9), Inches(1.4), Inches(6.0), Inches(3.4), [labels[t] for t in tasks],
          [("Pandas", tuple(pvs[(t, "Pandas")] for t in tasks)), ("SQLite", tuple(pvs[(t, "SQLite")] for t in tasks))],
          number_format="0.0", colors=[KZ, EMBER], title_text="Pandas против SQLite, мс", legend=True)
text_box(s, Inches(6.9), Inches(5.0), Inches(6.0), Inches(1.8), [
    ("Хранение и выборки топ-N — в SQL и Parquet", {}),
    ("Векторные расчёты по всей таблице — в Pandas", {}),
    ("Модели против baseline — на слайдах 10 и 11", {}),
], size=15, bullets=True, space_after=6)
notes(s, "Parquet читается в 2,5 раза быстрее CSV. SQLite быстрее на ORDER BY + LIMIT, Pandas — на оконных вычислениях.")

# 15. Интерфейсы -----------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "Дашборд Streamlit и консольное меню")
picture(s, DOCS / "dashboard_forecast.png", Inches(0.4), Inches(1.3), Inches(8.2), Inches(5.4))
text_box(s, Inches(8.9), Inches(1.4), Inches(4.0), Inches(5.3), [
    ("Фильтры: период, континент, группа аналогов, страны, серия", {}),
    ("Вкладки: обзор, карта, прогноз, SQL, бенчмарки", {}),
    ("Прогноз: частота, страна, модели, горизонт; сохранение в Parquet и SQLite", {}),
    ("main.py: 15 пунктов, журнал сессий в JSON, обработка ошибок ввода", {}),
], size=15, bullets=True, space_after=10)
caption(s, "Запуск: streamlit run app.py · python main.py · python main.py --all")
notes(s, "На защите показываем вживую вкладку «Прогноз» и пункт меню 11 — прогноз для выбранной страны.")

# 16. 3D-фронтенд -----------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
title(s, "3D-фронтенд: Земля в тепловизоре")
picture(s, DOCS / "frontend_globe.png", Inches(0.4), Inches(1.3), Inches(8.3), Inches(4.75))
for i, (shot, cap_text) in enumerate([("frontend_mix.png", "Энергобаланс: год × источник"), ("frontend_seasons.png", "Сезонная спираль и прогноз")]):
    picture(s, DOCS / shot, Inches(8.95), Inches(1.3 + i * 2.45), Inches(4.0), Inches(2.25))
text_box(s, Inches(0.6), Inches(6.15), Inches(12.2), Inches(0.9), [
    ("Высота и цвет столбика — показатель страны за год; Казахстан обведён бирюзой; год выбирается на кривой выбросов.", {"size": 15}),
    ("Расчёты на Python: FastAPI отдаёт данные, прогноз и SQL из пакета energy_co2, браузер только рисует. Запуск: python web/server.py", {"size": 15, "bold": True}),
])
notes(s, "Расширение проекта сверх требований. Отрисовка в браузере на JavaScript (three.js, globe.gl), всё остальное на Python. Показываем вживую: проиграть годы, выбрать группу аналогов, открыть спираль.")

# 17. Выводы и вклад ---------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); background(s, INK)
title(s, "Выводы", dark=True)
text_box(s, Inches(0.6), Inches(1.4), Inches(7.4), Inches(5.4), [
    ("Казахстан — одна из самых углеродоёмких экономик: 95 % ископаемых, 802 г CO₂/кВт·ч", {}),
    ("Энергопереход 2000–2024 не начался, у лидеров −20…−35 п.п.", {}),
    ("Годовые выбросы: naive — сильный ориентир, тренд нужно проверять CV", {}),
    ("Месячные: SARIMA и ETS дают MAPE 4–6 %, naive 16 %", {}),
    ("Приросты выбросов следуют за ВВП; связь с нефтью и климатом ложная", {}),
    ("Parquet −95 % места, SQL и Pandas — каждому своя задача", {}),
], size=17, color=WHITE, bullets=True, space_after=12)
team = [("Aidar", "архитектура, очистка, прогноз, меню, дашборд, API"), ("Daniyal", "EDA, временные ряды, корреляции, графики, 3D-фронт"), ("Nurzhan", "SQLite, ER, SQL, бенчмарки, отчёт")]
for i, (n, role) in enumerate(team):
    y = Inches(1.5 + i * 1.7)
    card(s, Inches(8.4), y, Inches(4.4), Inches(1.45), fill=RGBColor(0x2E, 0x33, 0x3F))
    text_box(s, Inches(8.6), y + Inches(0.12), Inches(4.0), Inches(0.5), n, size=20, bold=True, font=HEAD, color=EMBER)
    text_box(s, Inches(8.6), y + Inches(0.65), Inches(4.0), Inches(0.7), role, size=14, color=WHITE)
notes(s, "Вклад участников указан по требованиям к командной работе.")

out = DOCS / "presentation.pptx"
prs.save(out)
print("written", out, len(prs.slides), "slides")
