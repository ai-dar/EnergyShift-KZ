// Состояние приложения и доступ к данным панели, полученным с сервера.

export const state = { view: "globe", iso: null, year: null, metric: "co2_per_capita", group: null, playing: false };
export const data = { boot: null, byIso: new Map(), caps: new Map(), world: [] };

const listeners = new Set();
export const subscribe = (fn) => listeners.add(fn);
export function setState(patch) {
  const changed = Object.keys(patch).filter((key) => state[key] !== patch[key]);
  if (!changed.length) return;
  Object.assign(state, patch);
  listeners.forEach((fn) => fn(state, changed));
}

export function loadBoot(boot) {
  data.boot = boot;
  boot.countries.forEach((c) => data.byIso.set(c.iso, c));
  // Потолок шкалы — 99-й перцентиль за все годы: высоты сравнимы во времени, а малые страны-рекордсмены не сжимают остальных.
  for (const m of boot.metrics) {
    const all = Object.values(boot.values[m.key]).flat().filter((v) => v !== null).sort((a, b) => a - b);
    data.caps.set(m.key, all[Math.floor(all.length * 0.99)] || 1);
  }
  data.world = boot.years.map((_, i) => Object.values(boot.values.co2).reduce((sum, s) => sum + (s[i] ?? 0), 0));
  state.iso = boot.target;
  state.year = boot.years[boot.years.length - 1];
}

export const yearIndex = (year) => year - data.boot.years[0];
export const metricMeta = (key = state.metric) => data.boot.metrics.find((m) => m.key === key);
export const country = (iso) => data.byIso.get(iso);
export const series = (metric, iso) => data.boot.values[metric]?.[iso] ?? null;
export function val(metric, iso, year) {
  const s = series(metric, iso);
  return s ? s[yearIndex(year)] ?? null : null;
}
// Нормировка 0..1 с учётом шкалы показателя (для больших разбросов — корень).
export function norm(metric, value) {
  if (value === null) return null;
  const cap = data.caps.get(metric);
  const f = metricMeta(metric).scale === "sqrt" ? Math.sqrt : (x) => x;
  return Math.max(0, Math.min(1, f(Math.max(value, 0)) / f(cap)));
}
// Место страны по показателю среди стран с населением от 1 млн (как в отчёте).
export function rank(metric, iso, year) {
  const mine = val(metric, iso, year);
  if (mine === null) return null;
  let place = 1, total = 0;
  for (const c of data.boot.countries) {
    const population = val("population", c.iso, year);
    const v = val(metric, c.iso, year);
    if (v === null || population === null || population < 1e6) continue;
    total += 1;
    if (v > mine && c.iso !== iso) place += 1;
  }
  return { place, total };
}
export const worldShare = (iso, year) => {
  const v = val("co2", iso, year);
  const total = data.world[yearIndex(year)];
  return v === null || !total ? null : (v / total) * 100;
};
