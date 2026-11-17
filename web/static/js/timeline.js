// Шкала времени: вместо ползунка — кривая выбранного показателя; год выбирается перетаскиванием по ней.
import { state, data, setState, subscribe, series, country, metricMeta } from "./store.js";
import { fmt, clamp, SKY } from "./util.js";

const PAD_X = 6, PAD_TOP = 22, PAD_BOTTOM = 4;
const STEP_MS = 520;

export function initTimeline() {
  const root = document.getElementById("timeline");
  const track = document.getElementById("track");
  const svg = document.getElementById("track-svg");
  const handle = document.getElementById("handle");
  const handleYear = document.getElementById("handle-year");
  const caption = document.getElementById("track-caption");
  const play = document.getElementById("play");
  const years = data.boot.years;
  let timer = null;

  const xOf = (i, w) => PAD_X + (i / (years.length - 1)) * (w - 2 * PAD_X);

  function pathOf(values, w, h, max) {
    let d = "", pen = false;
    values.forEach((v, i) => {
      if (v === null) { pen = false; return; }
      const y = h - PAD_BOTTOM - (v / max) * (h - PAD_TOP - PAD_BOTTOM);
      d += `${pen ? "L" : "M"}${xOf(i, w).toFixed(1)},${y.toFixed(1)}`;
      pen = true;
    });
    return d;
  }

  function draw() {
    const w = track.clientWidth, h = track.clientHeight;
    if (!w || !h) return;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const own = series(state.metric, state.iso) || [];
    const target = state.iso !== data.boot.target ? series(state.metric, data.boot.target) : null;
    const max = Math.max(1e-9, ...own.filter((v) => v !== null), ...(target || []).filter((v) => v !== null));
    const idx = years.indexOf(state.year);
    const x = xOf(idx, w);
    const line = pathOf(own, w, h, max);
    const first = own.findIndex((v) => v !== null), last = own.length - 1 - [...own].reverse().findIndex((v) => v !== null);
    const area = line ? `${line}L${xOf(last, w).toFixed(1)},${h}L${xOf(first, w).toFixed(1)},${h}Z` : "";
    svg.innerHTML = `
      <defs>
        <linearGradient id="heat-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#f58a2c" stop-opacity="0.55"/><stop offset="1" stop-color="#8a2a86" stop-opacity="0.05"/>
        </linearGradient>
        <clipPath id="past"><rect x="0" y="0" width="${x}" height="${h}"/></clipPath>
      </defs>
      <path d="${area}" fill="#3a2a70" opacity="0.35"/>
      <path d="${area}" fill="url(#heat-fill)" clip-path="url(#past)"/>
      <path d="${line}" fill="none" stroke="#6a58a8" stroke-width="1.5"/>
      <path d="${line}" fill="none" stroke="#ffb45e" stroke-width="2.25" clip-path="url(#past)"/>
      ${target ? `<path d="${pathOf(target, w, h, max)}" fill="none" stroke="${SKY}" stroke-width="1.5" stroke-dasharray="4 4"/>` : ""}
      ${years.map((y, i) => (y % 5 === 0 ? `<text x="${xOf(i, w)}" y="${h - 6}" text-anchor="middle" fill="#8f82b5" font-size="11">${y}</text>` : "")).join("")}`;
    handle.style.left = `${x - 1}px`;
    handle.classList.toggle("is-flipped", idx > years.length - 5);
    handleYear.textContent = state.year;
    track.setAttribute("aria-valuenow", state.year);

    const meta = metricMeta();
    const present = own.map((v, i) => [v, years[i]]).filter(([v]) => v !== null);
    const c = country(state.iso);
    if (!present.length) {
      caption.innerHTML = `<span>${meta.label}: для страны ${c.label} нет данных</span>`;
    } else {
      const peak = present.reduce((a, b) => (b[0] > a[0] ? b : a));
      caption.innerHTML = `<span>${meta.label}, ${meta.unit}: ${c.label}. Максимум ${fmt(peak[0], meta.digits)} в ${peak[1]} году</span>`
        + (target ? `<span style="color:${SKY}">пунктир — Казахстан</span>` : `<span>перетащите, чтобы сменить год</span>`);
    }
  }

  function yearAt(clientX) {
    const rect = track.getBoundingClientRect();
    const t = clamp((clientX - rect.left - PAD_X) / (rect.width - 2 * PAD_X), 0, 1);
    return years[Math.round(t * (years.length - 1))];
  }
  function stop() {
    clearInterval(timer); timer = null;
    setState({ playing: false });
    play.textContent = "Проиграть";
    play.setAttribute("aria-label", "Проиграть годы");
  }
  function start() {
    if (state.year === years[years.length - 1]) setState({ year: years[0] });
    setState({ playing: true });
    play.textContent = "Остановить";
    play.setAttribute("aria-label", "Остановить");
    timer = setInterval(() => {
      if (state.year >= years[years.length - 1]) return stop();
      setState({ year: state.year + 1 });
    }, STEP_MS);
  }

  track.addEventListener("pointerdown", (e) => {
    if (timer) stop();
    track.setPointerCapture(e.pointerId);
    setState({ year: yearAt(e.clientX) });
  });
  track.addEventListener("pointermove", (e) => { if (e.buttons) setState({ year: yearAt(e.clientX) }); });
  track.addEventListener("keydown", (e) => {
    const i = years.indexOf(state.year);
    const next = { ArrowLeft: i - 1, ArrowDown: i - 1, ArrowRight: i + 1, ArrowUp: i + 1, Home: 0, End: years.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    if (timer) stop();
    setState({ year: years[clamp(next, 0, years.length - 1)] });
  });
  play.addEventListener("click", () => (timer ? stop() : start()));

  new ResizeObserver(draw).observe(track);
  subscribe((_, changed) => {
    if (changed.includes("view")) {
      const idle = state.view === "forecast" || state.view === "sql";
      root.classList.toggle("is-idle", idle);
      if (idle && timer) stop();
    }
    draw();
  });
  draw();
}
