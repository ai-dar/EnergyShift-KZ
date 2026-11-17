// Глобус: страны выдавлены вверх по значению показателя и окрашены по тепловой шкале.
import { state, data, setState, subscribe, val, norm, country, metricMeta, rank } from "./store.js";
import { rampRGB, rgb, fmt, el, SKY, PAPER, reducedMotion } from "./util.js";

const MISSING = "rgba(58,42,112,0.5)";
const BASE_ALT = 0.006, MAX_ALT = 0.55;

function centroid(geometry) {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const ring = polygons.map((p) => p[0]).reduce((a, b) => (b.length > a.length ? b : a));
  const sum = ring.reduce((acc, [lng, lat]) => [acc[0] + lng, acc[1] + lat], [0, 0]);
  return { lng: sum[0] / ring.length, lat: sum[1] / ring.length };
}

export function initGlobe(geo) {
  const host = document.getElementById("globe");
  const readout = document.getElementById("readout");
  const features = geo.features
    .map((f) => {
      const p = f.properties;
      const iso = p.ISO_A3 && p.ISO_A3 !== "-99" ? p.ISO_A3 : p.ADM0_A3;
      return { ...f, iso, center: centroid(f.geometry) };
    })
    .filter((f) => f.iso !== "ATA");
  const centers = new Map(features.map((f) => [f.iso, f.center]));
  const target = data.boot.target;
  let risen = false;   // до вступительной анимации все страны плоские

  const members = () => (state.group ? new Set(data.boot.peer_groups[state.group]) : null);
  const altitude = (f) => {
    if (!risen) return BASE_ALT;
    const n = norm(state.metric, val(state.metric, f.iso, state.year));
    if (n === null) return BASE_ALT;
    const group = members();
    return BASE_ALT + n * MAX_ALT * (group && !group.has(f.iso) ? 0.25 : 1);
  };
  const capColor = (f) => {
    const n = norm(state.metric, val(state.metric, f.iso, state.year));
    if (n === null) return MISSING;
    const group = members();
    return rgb(rampRGB(n), group && !group.has(f.iso) ? 0.22 : 0.96);
  };
  const sideColor = (f) => {
    const n = norm(state.metric, val(state.metric, f.iso, state.year));
    if (n === null) return "rgba(40,28,84,0.5)";
    const group = members();
    return rgb(rampRGB(n), group && !group.has(f.iso) ? 0.15 : 0.9, 0.55);
  };
  const stroke = (f) => (f.iso === target ? SKY : f.iso === state.iso ? PAPER : "rgba(244,239,232,0.14)");

  const globe = Globe()(host)
    .backgroundColor("rgba(0,0,0,0)")
    .showAtmosphere(true).atmosphereColor("#8a5cff").atmosphereAltitude(0.16)
    .showGraticules(true)
    .polygonsData(features)
    .polygonAltitude(altitude).polygonCapColor(capColor).polygonSideColor(sideColor).polygonStrokeColor(stroke)
    .polygonsTransitionDuration(0)
    .onPolygonHover((f) => {
      host.style.cursor = f ? "pointer" : "grab";
      describe(f ? f.iso : null);
    })
    .onPolygonClick((f) => { if (country(f.iso)) setState({ iso: f.iso }); })
    .htmlElementsData([])
    .htmlLat((d) => d.lat).htmlLng((d) => d.lng).htmlAltitude((d) => d.alt)
    .htmlElement((d) => el("div", { class: `globe-tag${d.selected ? " is-selected" : ""}`, text: d.text }))
    .arcsData([])
    .arcStartLat((d) => d.from.lat).arcStartLng((d) => d.from.lng).arcEndLat((d) => d.to.lat).arcEndLng((d) => d.to.lng)
    .arcColor(() => [SKY, "rgba(28,200,228,0.35)"]).arcStroke(0.7).arcAltitude(0.62)
    .arcDashLength(0.5).arcDashGap(0.25).arcDashAnimateTime(reducedMotion() ? 0 : 4200);
  globe.globeMaterial().color.set("#07041a");      // свет сцены усиливает цвет примерно втрое
  globe.globeMaterial().emissive.set("#0a0522");
  globe.controls().enablePan = false;
  globe.controls().minDistance = 150;
  globe.controls().maxDistance = 520;

  function describe(iso) {
    const c = iso ? country(iso) : null;
    if (!c) {
      readout.textContent = iso ? "Для этой территории в данных нет страны." : "Наведите на страну. Нажмите, чтобы выбрать её.";
      return;
    }
    const meta = metricMeta();
    const v = val(state.metric, iso, state.year);
    const place = rank(state.metric, iso, state.year);
    readout.replaceChildren(
      el("b", { text: c.label }),
      v === null ? `${meta.label}: нет данных за ${state.year} год` : `${meta.label}: ${fmt(v, meta.digits)} ${meta.unit}`,
      place ? `, ${place.place}-е место из ${place.total}` : "",
    );
  }

  function tags() {
    const meta = metricMeta();
    const make = (iso, selected) => {
      const center = centers.get(iso);
      if (!center) return null;
      const v = val(state.metric, iso, state.year);
      const n = norm(state.metric, v);
      return {
        ...center, selected, alt: BASE_ALT + (n ?? 0) * MAX_ALT + 0.02,
        text: `${country(iso).label}${v === null ? "" : ` ${fmt(v, meta.digits)} ${meta.unit}`}`,
      };
    };
    const list = [make(target, false)];
    if (state.iso !== target) list.push(make(state.iso, true));
    globe.htmlElementsData(list.filter(Boolean));
  }

  function arcs() {
    const group = members();
    const from = centers.get(target);
    globe.arcsData(group ? [...group].filter((iso) => iso !== target && centers.has(iso)).map((iso) => ({ from, to: centers.get(iso) })) : []);
  }

  function repaint(duration) {
    globe.polygonsTransitionDuration(reducedMotion() ? 0 : duration)
      .polygonAltitude(altitude).polygonCapColor(capColor).polygonSideColor(sideColor).polygonStrokeColor(stroke);
    tags();
    const cap = data.caps.get(state.metric), meta = metricMeta();
    document.getElementById("scale-max").textContent = `${fmt(cap, meta.digits)} ${meta.unit} и больше`;
  }

  function resize() {
    if (host.clientWidth && host.clientHeight) globe.width(host.clientWidth).height(host.clientHeight);
  }
  new ResizeObserver(resize).observe(host);
  resize();

  // Единственная «режиссёрская» анимация: страны вырастают, камера прилетает к Казахстану.
  const home = centers.get(target);
  if (reducedMotion()) {
    risen = true;
    globe.pointOfView({ lat: home.lat - 6, lng: home.lng, altitude: 1.9 }, 0);
    repaint(0);
  } else {
    globe.pointOfView({ lat: 12, lng: home.lng - 95, altitude: 3.1 }, 0);
    setTimeout(() => {
      risen = true;
      repaint(1600);
      globe.pointOfView({ lat: home.lat - 6, lng: home.lng, altitude: 1.9 }, 2600);
    }, 500);
  }

  subscribe((_, changed) => {
    if (changed.includes("view")) {
      if (state.view === "globe") { globe.resumeAnimation(); resize(); } else globe.pauseAnimation();
    }
    if (changed.some((k) => ["year", "metric", "iso", "group"].includes(k))) {
      repaint(changed.includes("year") && state.playing ? 480 : 700);
    }
    if (changed.includes("group")) {
      arcs();
      if (state.group) globe.pointOfView({ lat: home.lat - 10, lng: home.lng, altitude: 2.5 }, 1200);
    }
    if (changed.includes("iso") && state.view === "globe") {
      const center = centers.get(state.iso);
      if (center) globe.pointOfView({ lat: center.lat - 6, lng: center.lng, altitude: globe.pointOfView().altitude }, 1100);
    }
  });
  return { resize };
}
