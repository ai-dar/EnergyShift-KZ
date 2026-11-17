// Точка входа: загрузка данных с сервера, запуск разделов, навигация и поиск страны.
import { state, data, loadBoot, setState, subscribe } from "./store.js";
import { getJSON, el } from "./util.js";
import { initLede } from "./lede.js";
import { initTimeline } from "./timeline.js";
import { initGlobe } from "./globe.js";
import { initSkyline } from "./skyline.js";
import { initSpiral } from "./spiral.js";
import { initForecast } from "./forecast.js";
import { initSql } from "./sql.js";

const errorBox = document.getElementById("stage-error");
function showError(message) {
  errorBox.hidden = !message;
  errorBox.textContent = message || "";
}

function choices(host, items, current, onPick) {
  const paint = () => host.replaceChildren(...items.map(([key, label]) =>
    el("button", { class: "choice", type: "button", "aria-pressed": String(current() === key), text: label, onclick: () => onPick(key) })));
  paint();
  return paint;
}

function initNav() {
  const tabs = [...document.querySelectorAll(".views button")];
  tabs.forEach((tab) => tab.addEventListener("click", () => setState({ view: tab.dataset.view })));
  subscribe((_, changed) => {
    if (!changed.includes("view")) return;
    tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.view === state.view)));
    document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `view-${state.view}`; });
    showError(null);
  });
}

function initSearch() {
  const form = document.getElementById("search");
  const input = document.getElementById("search-input");
  const home = document.getElementById("back-home");
  const options = data.boot.countries.map((c) => [c.label.toLowerCase(), c.iso]).concat(data.boot.countries.map((c) => [c.name.toLowerCase(), c.iso]));
  document.getElementById("country-list").replaceChildren(...data.boot.countries
    .map((c) => c.label).sort((a, b) => a.localeCompare(b, "ru")).map((label) => el("option", { value: label })));

  function pick() {
    const query = input.value.trim().toLowerCase();
    if (!query) return;
    const exact = options.find(([name]) => name === query) || options.find(([name]) => name.startsWith(query));
    if (!exact) {
      input.setCustomValidity("Такой страны нет в данных. Начните вводить название и выберите из списка.");
      input.reportValidity();
      return;
    }
    input.setCustomValidity("");
    input.value = "";
    setState({ iso: exact[1] });
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); pick(); });
  input.addEventListener("change", pick);
  input.addEventListener("input", () => input.setCustomValidity(""));
  home.addEventListener("click", () => setState({ iso: data.boot.target }));
  subscribe((_, changed) => { if (changed.includes("iso")) home.hidden = state.iso === data.boot.target; });
}

function initGlobeTools() {
  const paintMetrics = choices(document.getElementById("metric-options"),
    data.boot.metrics.map((m) => [m.key, m.label]), () => state.metric, (key) => setState({ metric: key }));
  const groups = [[null, "Со всем миром"], ...Object.keys(data.boot.peer_groups).map((g) => [g, g])];
  const paintGroups = choices(document.getElementById("group-options"), groups, () => state.group, (key) => setState({ group: key }));
  subscribe((_, changed) => {
    if (changed.includes("metric")) paintMetrics();
    if (changed.includes("group")) paintGroups();
  });
}

async function boot() {
  try {
    const [bootData, geo] = await Promise.all([getJSON("/api/bootstrap"), getJSON("vendor/countries.geojson")]);
    loadBoot(bootData);
    initNav();
    initSearch();
    initGlobeTools();
    initLede();
    initTimeline();
    initGlobe(geo);
    initSkyline(showError);
    initSpiral(showError);
    initForecast(showError);
    initSql(showError);
    window.energyShift = { state, setState };   // для отладки и автотестов интерфейса
  } catch (err) {
    showError(err.message);
    console.error(err);
  }
}
boot();
