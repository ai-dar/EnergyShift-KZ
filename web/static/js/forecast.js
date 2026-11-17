// «Прогноз»: факт, проверка моделей на отложенных периодах и прогноз в будущее. Расчёт — на сервере Python.
import { state, subscribe, country } from "./store.js";
import { getJSON, fmt, el, MODEL_COLORS, SKY, PAPER, LILAC, RULE, MONTHS, clamp } from "./util.js";

const BASELINES = new Set(["Naive", "Seasonal naive", "Drift"]);
const M = { left: 54, right: 18, top: 26, bottom: 30 };

export function initForecast(showError) {
  const svg = document.getElementById("forecast-chart");
  const wrap = svg.parentElement;
  const tip = document.getElementById("forecast-tip");
  const title = document.getElementById("forecast-title");
  const verdict = document.getElementById("forecast-verdict");
  const tbody = document.querySelector("#forecast-table tbody");
  const freqHost = document.getElementById("forecast-freq");
  const cache = new Map();
  const hidden = new Set(["Drift", "Lag GBM"]);   // по умолчанию показываем главное, остальное включается кликом
  let freq = "annual", payload = null, token = 0, active = false, geometry = null;

  function paintFreq() {
    const monthly = country(state.iso).has_monthly;
    if (!monthly && freq === "monthly") freq = "annual";
    freqHost.replaceChildren(
      el("button", { type: "button", "aria-pressed": String(freq === "annual"), text: "По годам", onclick: () => { freq = "annual"; load(); } }),
      el("button", { type: "button", "aria-pressed": String(freq === "monthly"), text: "По месяцам", disabled: monthly ? null : "",
        title: monthly ? null : "Для этой страны нет месячных данных", onclick: () => { freq = "monthly"; load(); } }),
    );
  }

  async function load() {
    const mine = ++token;
    paintFreq();
    const key = `${state.iso}:${freq}`;
    title.textContent = `${country(state.iso).label}: считаем прогноз…`;
    try {
      if (!cache.has(key)) cache.set(key, await getJSON(`/api/forecast/${state.iso}?freq=${freq}`));
      if (mine !== token) return;
      payload = cache.get(key);
      render();
      showError(null);
    } catch (err) {
      if (mine !== token) return;
      title.textContent = `${country(state.iso).label}: прогноз построить не удалось`;
      verdict.textContent = "";
      showError(err.message);
    }
  }

  const label = (x) => (payload.freq === "monthly" ? `${MONTHS[+x.slice(5, 7) - 1]} ${x.slice(0, 4)}` : x);

  function render() {
    const p = payload;
    title.textContent = p.freq === "annual" ? `${p.label}: выбросы CO₂ по годам` : `${p.label}: выбросы электростанций по месяцам`;
    const best = p.metrics[0];
    const naive = p.metrics.find((m) => m.model === (p.freq === "monthly" ? "Seasonal naive" : "Naive"));
    const last = p.future.x.length - 1;
    const beat = !best.is_baseline;
    verdict.replaceChildren(
      "Точнее всех на проверке ", el("b", { text: best.model }), `: ошибка ${fmt(best.MAPE, 1)} %. `,
      beat ? `Наивный прогноз она обошла (у него ${fmt(naive.MAPE, 1)} %). ` : "Ни одна модель не обошла наивный прогноз. ",
      `Прогноз ${p.future.model} на ${label(p.future.x[last])}: `, el("b", { text: `${fmt(p.future.y[last], p.freq === "annual" ? 0 : 1)} ${p.unit}` }),
      p.source === "live" ? ". Модели обучены только что." : ".",
    );

    tbody.replaceChildren(...p.metrics.map((m) => {
      const row = el("tr", { class: hidden.has(m.model) ? "is-off" : "", tabindex: "0", role: "button",
        "aria-pressed": String(!hidden.has(m.model)), "aria-label": `Показать или скрыть линию ${m.model}` },
        el("td", {}, el("span", { class: "dot", style: `background:${MODEL_COLORS[m.model] || LILAC}` }), m.model, m.is_baseline ? el("em", { text: "базовая" }) : ""),
        el("td", { class: "num", text: fmt(m.MAPE, 1) }), el("td", { class: "num", text: fmt(m.MASE, 2) }),
        el("td", { class: "num", text: m.train_time_s < 0.001 ? "< 0,001" : fmt(m.train_time_s, 3) }));
      const toggle = () => { hidden.has(m.model) ? hidden.delete(m.model) : hidden.add(m.model); render(); };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
      return row;
    }));
    draw();
  }

  function draw() {
    if (!payload) return;
    const p = payload;
    const w = wrap.clientWidth, h = wrap.clientHeight;
    if (!w || !h) return;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const xs = [...p.history.x, ...p.future.x];
    const n = xs.length, nh = p.history.x.length, split = nh - p.holdout_size;
    const shown = Object.keys(p.holdout.models).filter((m) => !hidden.has(m));
    const all = [...p.history.y, ...p.future.lower, ...p.future.upper, ...shown.flatMap((m) => p.holdout.models[m])].filter((v) => v !== null);
    let lo = Math.min(...all), hi = Math.max(...all);
    const pad = (hi - lo) * 0.07 || 1;
    lo = Math.max(0, lo - pad); hi += pad;
    const X = (i) => M.left + (i / (n - 1)) * (w - M.left - M.right);
    const Y = (v) => h - M.bottom - ((v - lo) / (hi - lo)) * (h - M.top - M.bottom);
    geometry = { X, Y, n, nh, split, w, h, xs };
    const line = (values, offset = 0) => values.map((v, i) => (v === null ? "" : `${i && values[i - 1] !== null ? "L" : "M"}${X(i + offset).toFixed(1)},${Y(v).toFixed(1)}`)).join("");

    const raw = (hi - lo) / 5, power = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * power).find((s) => s >= raw);
    const ticks = [];
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
    const digits = step < 1 ? 1 : 0;
    const xTicks = xs.map((x, i) => (p.freq === "annual" ? (+x % 5 === 0 ? [i, x] : null) : (x.endsWith("-01") ? [i, x.slice(0, 4)] : null))).filter(Boolean);
    const band = `${p.future.upper.map((v, i) => `${i ? "L" : "M"}${X(nh + i).toFixed(1)},${Y(v).toFixed(1)}`).join("")}`
      + `${[...p.future.lower].reverse().map((v, i) => `L${X(n - 1 - i).toFixed(1)},${Y(v).toFixed(1)}`).join("")}Z`;

    svg.innerHTML = `
      ${ticks.map((t) => `<line x1="${M.left}" x2="${w - M.right}" y1="${Y(t)}" y2="${Y(t)}" stroke="${RULE}" stroke-width="1" opacity="0.6"/>
        <text x="${M.left - 8}" y="${Y(t) + 4}" text-anchor="end" fill="${LILAC}" font-size="11">${fmt(t, digits)}</text>`).join("")}
      ${xTicks.map(([i, t]) => `<text x="${X(i)}" y="${h - 9}" text-anchor="middle" fill="${LILAC}" font-size="11">${t}</text>`).join("")}
      <rect x="${X(split)}" y="${M.top}" width="${X(nh - 1) - X(split)}" height="${h - M.top - M.bottom}" fill="#ffffff" opacity="0.045"/>
      <text x="${X(split) + 6}" y="${M.top - 8}" fill="${LILAC}" font-size="11">проверка</text>
      <text x="${X(nh) + 4}" y="${M.top - 8}" fill="${SKY}" font-size="11">прогноз</text>
      <path d="${band}" fill="${SKY}" opacity="0.14"/>
      ${shown.map((m) => `<path d="${line(p.holdout.models[m], split)}" fill="none" stroke="${MODEL_COLORS[m] || LILAC}" stroke-width="1.75" ${BASELINES.has(m) ? 'stroke-dasharray="5 4"' : ""}/>`).join("")}
      <path d="${line(p.history.y)}" fill="none" stroke="${PAPER}" stroke-width="2.25"/>
      <path d="M${X(nh - 1).toFixed(1)},${Y(p.history.y[nh - 1]).toFixed(1)}${p.future.y.map((v, i) => `L${X(nh + i).toFixed(1)},${Y(v).toFixed(1)}`).join("")}" fill="none" stroke="${SKY}" stroke-width="2.25" stroke-dasharray="7 5"/>
      <text x="${M.left}" y="${M.top - 8}" fill="${LILAC}" font-size="11">${p.unit}</text>
      <line id="cross" y1="${M.top}" y2="${h - M.bottom}" stroke="${PAPER}" stroke-width="1" opacity="0" />`;
  }

  wrap.addEventListener("pointermove", (event) => {
    if (!payload || !geometry) return;
    const { X, n, nh, split, w, xs } = geometry;
    const rect = wrap.getBoundingClientRect();
    const i = clamp(Math.round(((event.clientX - rect.left - M.left) / (w - M.left - M.right)) * (n - 1)), 0, n - 1);
    const cross = svg.querySelector("#cross");
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("opacity", "0.45");
    const p = payload, d = p.freq === "annual" ? 1 : 2;
    const rows = [];
    if (i < nh) rows.push(["Факт", p.history.y[i], PAPER]);
    if (i >= split && i < nh) {
      for (const [m, values] of Object.entries(p.holdout.models)) if (!hidden.has(m)) rows.push([m, values[i - split], MODEL_COLORS[m] || LILAC]);
    }
    if (i >= nh) {
      rows.push([`Прогноз ${p.future.model}`, p.future.y[i - nh], SKY]);
      rows.push(["от", p.future.lower[i - nh], LILAC], ["до", p.future.upper[i - nh], LILAC]);
    }
    tip.replaceChildren(el("b", { text: label(xs[i]) }), ...rows.map(([name, v, color]) =>
      el("div", {}, el("span", { style: `color:${color}`, text: name }), el("span", { text: fmt(v, d) }))));
    tip.hidden = false;
    const tx = X(i) + 14, flip = tx + 190 > w;
    tip.style.left = `${flip ? X(i) - 14 - tip.offsetWidth : tx}px`;
    tip.style.top = `${M.top + 6}px`;
  });
  wrap.addEventListener("pointerleave", () => {
    tip.hidden = true;
    svg.querySelector("#cross")?.setAttribute("opacity", "0");
  });
  new ResizeObserver(draw).observe(wrap);

  subscribe((_, changed) => {
    if (changed.includes("view")) {
      active = state.view === "forecast";
      if (active) load();
    } else if (active && changed.includes("iso")) load();
  });
}
