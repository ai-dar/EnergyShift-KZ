// Общие мелочи: тепловая шкала, форматирование чисел по-русски, запросы к Python-серверу.

const STOPS = [[67, 32, 138], [138, 42, 134], [209, 73, 91], [245, 138, 44], [255, 226, 138]];

export function rampRGB(t) {
  const x = Math.max(0, Math.min(1, t)) * (STOPS.length - 1);
  const i = Math.min(Math.floor(x), STOPS.length - 2);
  const f = x - i;
  return STOPS[i].map((c, k) => Math.round(c + (STOPS[i + 1][k] - c) * f));
}
export const rgb = (c, alpha = 1, k = 1) => `rgba(${c.map((v) => Math.round(v * k)).join(",")},${alpha})`;
export const rampHex = (t) => "#" + rampRGB(t).map((v) => v.toString(16).padStart(2, "0")).join("");

export const SKY = "#1cc8e4";
export const PAPER = "#f4efe8";
export const LILAC = "#b0a3d1";
export const RULE = "#3a2a70";
export const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
export const MONTHS_FULL = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];

// Цвета источников энергии: ископаемые — «горячие», низкоуглеродные — «холодные».
export const SOURCE_COLORS = {
  coal: "#d1495b", oil: "#f58a2c", gas: "#ffd166",
  nuclear: "#b99cff", hydro: "#4d8dff", wind: "#1cc8e4", solar: "#7be0c3", biofuel: "#6fcf7c", other_renewable: "#b9e6a0",
};
// Цвет закреплён за моделью, а не за её местом в рейтинге.
export const MODEL_COLORS = {
  "Naive": "#3987e5", "Seasonal naive": "#d95926", "Drift": "#199e70", "Linear trend": "#c98500",
  "ETS": "#d55181", "ARIMA": "#5fb85f", "Lag LR": "#9085e9", "Lag GBM": "#e66767",
};

const formatters = new Map();
export function fmt(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "нет данных";
  if (!formatters.has(digits)) {
    formatters.set(digits, new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
  }
  return formatters.get(digits).format(value);
}
// Число из таблицы SQL: целые без дробной части, остальные — до трёх знаков.
export function fmtCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "number") return String(value);
  return Number.isInteger(value) ? String(value) : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(value);
}

export async function getJSON(url) {
  let response;
  try {
    response = await fetch(url);
  } catch (err) {
    throw new Error("Сервер не отвечает. Запустите его командой python web/server.py и обновите страницу.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Сервер вернул ошибку ${response.status}.`);
  }
  return response.json();
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== false && value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
