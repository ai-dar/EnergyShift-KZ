// «Энергобаланс»: 3D-город из столбцов. Столбец — год, слои — источники энергии.
/* global THREE */
import { state, data, subscribe } from "./store.js";
import { createStage, disposeGroup, growIn } from "./stage3d.js";
import { getJSON, fmt, el, SOURCE_COLORS, reducedMotion } from "./util.js";

const HEIGHT = 13, HALF = 8, STEP = 1, BOX = 0.8, DEPTH = 1.5, GAP = 0.09;

export function initSkyline(showError) {
  const host = document.getElementById("skyline");
  const readout = document.getElementById("mix-readout");
  const stage = createStage(host, { position: [-13, 13, 38], target: [0, 5, 0], fov: 30, minDistance: 14, maxDistance: 90 });
  const sources = data.boot.sources;
  const materials = new Map(sources.map((s) => {
    const color = new THREE.Color(SOURCE_COLORS[s.key]);
    return [s.key, {
      bright: new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05, emissive: color, emissiveIntensity: 0.22 }),
      dim: new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.62), roughness: 0.75, metalness: 0.05 }),
    }];
  }));
  const box = new THREE.BoxGeometry(BOX, 1, DEPTH);
  const cache = new Map();
  let mode = "twh", group = null, meshes = [], token = 0, active = false;

  document.getElementById("source-legend").replaceChildren(...sources.map((s) =>
    el("li", {}, el("span", { class: "swatch", style: `background:${SOURCE_COLORS[s.key]}` }), s.label)));
  const modes = [["twh", "Потребление, ТВт·ч"], ["share", "Доля источника, %"]];
  const modeHost = document.getElementById("mix-mode");
  const paintModes = () => modeHost.replaceChildren(...modes.map(([key, label]) =>
    el("button", { class: "choice", type: "button", "aria-pressed": String(mode === key), text: label, onclick: () => { mode = key; paintModes(); rebuild(); } })));
  paintModes();

  const detail = async (iso) => {
    if (!cache.has(iso)) cache.set(iso, await getJSON(`/api/country/${iso}`));
    return cache.get(iso);
  };

  // direction = 1 — столбцы растут вверх, −1 — вниз от общей оси (зеркальное сравнение с Казахстаном).
  function buildRow(mix, label, direction, height, scaleMax, isTarget) {
    const n = mix.years.length;
    mix.years.forEach((year, i) => {
      const total = sources.reduce((sum, s) => sum + (mix.sources[s.key][i] || 0), 0);
      if (!total) return;
      let y = 0;
      for (const s of sources) {
        const value = mix.sources[s.key][i] || 0;
        const h = mode === "share" ? (value / total) * height : (value / scaleMax) * height;
        if (h < 0.004) continue;
        const mesh = new THREE.Mesh(box, materials.get(s.key).bright);
        mesh.scale.y = h;
        mesh.position.set((i - (n - 1) / 2) * STEP, direction * (y + h / 2 + GAP), 0);
        mesh.userData = { year, key: s.key, source: s.label, value, share: (value / total) * 100, label };
        group.add(mesh);
        meshes.push(mesh);
        y += h;
      }
    });
    stage.addLabel(label, new THREE.Vector3(((n - 1) / 2 + 2.6) * STEP, direction * (height * 0.5), 0), isTarget ? "is-sky" : "is-strong");
  }

  async function rebuild() {
    const mine = ++token;
    const target = data.boot.target;
    let iso = state.iso, note = "";
    try {
      let own = await detail(iso);
      if (!own.mix) {
        note = `Для страны ${own.label} в источнике нет энергобаланса, поэтому показан Казахстан. `;
        iso = target;
        own = await detail(target);
      }
      const kz = iso !== target && mode === "share" ? await detail(target) : null;
      if (mine !== token) return;
      if (group) disposeGroup(group);
      stage.clearLabels();
      group = new THREE.Group();
      meshes = [];
      stage.scene.add(group);

      const totals = own.mix.years.map((_, i) => sources.reduce((sum, s) => sum + (own.mix.sources[s.key][i] || 0), 0));
      const scaleMax = Math.max(...totals);
      buildRow(own.mix, own.label, 1, kz ? HALF : HEIGHT, scaleMax, iso === target);
      if (kz) buildRow(kz.mix, kz.label, -1, HALF, 1, true);

      const n = own.mix.years.length;
      own.mix.years.forEach((year, i) => {
        if (year % 5 === 0) stage.addLabel(String(year), new THREE.Vector3((i - (n - 1) / 2) * STEP, kz ? 0 : -0.6, 1.7), kz ? "is-strong" : "");
      });
      const base = new THREE.Mesh(new THREE.BoxGeometry(n * STEP + 1.6, 0.08, 2.8),
        new THREE.MeshStandardMaterial({ color: 0x3a2a70, roughness: 0.9 }));
      base.position.y = kz ? 0 : -0.05;
      group.add(base);
      stage.frameTo(kz ? { halfWidth: n / 2 + 4.6, halfHeight: HALF + 1.4, centerY: 0 }
        : { halfWidth: n / 2 + 4.6, halfHeight: HEIGHT / 2 + 1.8, centerY: HEIGHT / 2 - 0.8 });
      growIn(group, stage, reducedMotion());
      highlight();
      readout.textContent = note + (mode === "share"
        ? (kz ? `Вверх растёт ${own.label}, вниз — Казахстан: состав энергии в те же годы. ` : "Все столбцы одной высоты: видно, как меняется состав. ") + "Наведите на блок, чтобы увидеть значение."
        : `Высота столбца — всё потребление за год, максимум ${fmt(scaleMax, 0)} ТВт·ч. Наведите на блок, чтобы увидеть значение.`);
      showError(null);
    } catch (err) {
      showError(err.message);
    }
  }

  function highlight() {
    for (const mesh of meshes) {
      const m = materials.get(mesh.userData.key);
      mesh.material = mesh.userData.year === state.year ? m.bright : m.dim;
    }
  }

  host.addEventListener("pointermove", (event) => {
    const hit = stage.pick(event, meshes);
    host.style.cursor = hit ? "crosshair" : "grab";
    if (!hit) return;
    const d = hit.object.userData;
    readout.replaceChildren(el("b", { text: `${d.source}, ${d.year}` }),
      `${d.label}: ${fmt(d.value, d.value < 10 ? 1 : 0)} ТВт·ч, ${fmt(d.share, 1)} % энергобаланса`);
  });

  subscribe((_, changed) => {
    if (changed.includes("view")) {
      active = state.view === "mix";
      stage.setActive(active);
      if (active) rebuild();
    } else if (active && changed.includes("iso")) rebuild();
    else if (active && changed.includes("year")) highlight();
  });
}
