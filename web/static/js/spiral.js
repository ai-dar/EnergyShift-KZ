// «Сезоны»: спираль месячных выбросов электроэнергетики. Виток — год, угол — месяц, радиус — выбросы.
/* global THREE */
import { state, data, subscribe, country } from "./store.js";
import { createStage, disposeGroup, growIn } from "./stage3d.js";
import { getJSON, fmt, el, rampRGB, MONTHS, MONTHS_FULL, SKY, reducedMotion } from "./util.js";

const R_MIN = 1.4, R_SPAN = 3.8, PITCH = 0.105;

export function initSpiral(showError) {
  const host = document.getElementById("spiral");
  const readout = document.getElementById("spiral-readout");
  const note = document.getElementById("spiral-note");
  const stage = createStage(host, { position: [11, 9, 17], target: [0, 5.6, 0], fov: 32, minDistance: 9, maxDistance: 70 });
  const cache = new Map();
  let group = null, dots = null, futureDots = null, points = [], token = 0, active = false;
  const dummy = new THREE.Object3D();

  const load = async (iso) => {
    if (!cache.has(iso)) {
      // Месячный прогноз запрашиваем только у стран, для которых есть месячные данные.
      const monthly = country(iso).has_monthly;
      const [detail, forecast] = await Promise.all([
        getJSON(`/api/country/${iso}`),
        monthly ? getJSON(`/api/forecast/${iso}?freq=monthly`).catch(() => null) : null,
      ]);
      cache.set(iso, { detail, forecast });
    }
    return cache.get(iso);
  };

  function place(i, value, lo, hi) {
    const month = points.length ? (points[0].month + i) % 12 : 0;
    const angle = (month / 12) * Math.PI * 2;
    const r = R_MIN + ((value - lo) / (hi - lo || 1)) * R_SPAN;
    return new THREE.Vector3(Math.sin(angle) * r, i * PITCH, Math.cos(angle) * r);
  }

  function tube(vectors, colorAt) {
    const curve = new THREE.CatmullRomCurve3(vectors);
    const segments = vectors.length * 8, radial = 6;
    const geometry = new THREE.TubeGeometry(curve, segments, 0.05, radial, false);
    const colors = new Float32Array(geometry.attributes.position.count * 3);
    for (let v = 0; v < geometry.attributes.position.count; v++) {
      const t = Math.floor(v / (radial + 1)) / segments;
      const [r, g, b] = colorAt(t);
      colors.set([r / 255, g / 255, b / 255], v * 3);
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true }));
  }

  function setDot(mesh, index, position, scale) {
    dummy.position.copy(position);
    dummy.scale.setScalar(scale);
    dummy.updateMatrix();
    mesh.setMatrixAt(index, dummy.matrix);
  }

  async function rebuild() {
    const mine = ++token;
    const target = data.boot.target;
    try {
      let { detail, forecast } = await load(state.iso);
      let prefix = "";
      if (!detail.monthly) {
        prefix = `Для страны ${detail.label} нет месячных данных Ember, поэтому показан Казахстан. `;
        ({ detail, forecast } = await load(target));
      }
      if (mine !== token) return;
      if (group) disposeGroup(group);
      stage.clearLabels();
      group = new THREE.Group();
      stage.scene.add(group);

      const values = detail.monthly.emissions;
      const future = forecast ? forecast.future.y : [];
      const lo = Math.min(...values, ...future), hi = Math.max(...values, ...future);
      points = detail.monthly.dates.map((d, i) => ({ date: d, year: +d.slice(0, 4), month: +d.slice(5, 7) - 1, value: values[i] }));
      const vectors = points.map((p, i) => place(i, p.value, lo, hi));
      group.add(tube(vectors, (t) => {
        const x = t * (values.length - 1), i = Math.min(Math.floor(x), values.length - 2), f = x - i;
        return rampRGB((values[i] + (values[i + 1] - values[i]) * f - lo) / (hi - lo || 1));
      }));

      const sphere = new THREE.SphereGeometry(0.105, 14, 12);
      dots = new THREE.InstancedMesh(sphere, new THREE.MeshStandardMaterial({ roughness: 0.45, emissive: 0x331a00, emissiveIntensity: 0.4 }), points.length);
      const color = new THREE.Color();
      points.forEach((p, i) => {
        p.position = vectors[i];
        const [r, g, b] = rampRGB((p.value - lo) / (hi - lo || 1));
        dots.setColorAt(i, color.setRGB(r / 255, g / 255, b / 255));
      });
      group.add(dots);

      futureDots = null;
      if (future.length) {
        const fv = future.map((v, k) => place(points.length + k, v, lo, hi));
        const sky = new THREE.Color(SKY);
        group.add(tube([vectors[vectors.length - 1], ...fv], () => [sky.r * 255, sky.g * 255, sky.b * 255]));
        futureDots = new THREE.InstancedMesh(sphere, new THREE.MeshStandardMaterial({ color: sky, emissive: sky, emissiveIntensity: 0.35 }), fv.length);
        futureDots.userData.items = forecast.future.x.map((x, k) => ({ date: x, value: future[k], position: fv[k] }));
        fv.forEach((v, k) => setDot(futureDots, k, v, 1));
        group.add(futureDots);
      }

      // Круг месяцев у основания и ось времени.
      const spokes = [];
      for (let m = 0; m < 12; m++) {
        const a = (m / 12) * Math.PI * 2, r = R_MIN + R_SPAN + 0.5;
        spokes.push(0, 0, 0, Math.sin(a) * r, 0, Math.cos(a) * r);
        stage.addLabel(MONTHS[m], new THREE.Vector3(Math.sin(a) * (r + 0.7), 0, Math.cos(a) * (r + 0.7)), m === 0 || m === 11 || m === 1 ? "is-strong" : "");
      }
      const total = points.length + future.length;
      spokes.push(0, 0, 0, 0, total * PITCH + 0.6, 0);
      const lines = new THREE.BufferGeometry();
      lines.setAttribute("position", new THREE.Float32BufferAttribute(spokes, 3));
      group.add(new THREE.LineSegments(lines, new THREE.LineBasicMaterial({ color: 0x3a2a70 })));
      points.forEach((p) => {
        if (p.month === 0) stage.addLabel(String(p.year), p.position.clone().add(new THREE.Vector3(0, 0.05, 0.75)));
      });
      if (future.length) stage.addLabel("прогноз", futureDots.userData.items[Math.min(5, future.length - 1)].position.clone().multiplyScalar(1.18), "is-sky");

      stage.frameTo({ halfWidth: R_MIN + R_SPAN + 1.6, halfHeight: (total * PITCH) / 2 + 2.3, centerY: (total * PITCH) / 2 - 0.9 });
      growIn(group, stage, reducedMotion());
      highlight();
      const winter = points.filter((p) => [11, 0, 1].includes(p.month)), summer = points.filter((p) => [5, 6, 7].includes(p.month));
      const mean = (a) => a.reduce((s, p) => s + p.value, 0) / (a.length || 1);
      const lift = (mean(winter) / mean(summer) - 1) * 100;
      note.textContent = prefix + `${detail.label}: с декабря по февраль электростанции выбрасывают на ${fmt(Math.abs(lift), 0)} % ${lift >= 0 ? "больше" : "меньше"}, чем с июня по август. `
        + (forecast ? `Бирюзовый хвост — прогноз модели ${forecast.future.model}.` : "");
      document.getElementById("spiral-min").textContent = `${fmt(lo, 1)} Мт в месяц`;
      document.getElementById("spiral-max").textContent = `${fmt(hi, 1)} Мт`;
      showError(null);
    } catch (err) {
      showError(err.message);
    }
  }

  function highlight() {
    if (!dots) return;
    points.forEach((p, i) => setDot(dots, i, p.position, p.year === state.year ? 1.75 : 1));
    dots.instanceMatrix.needsUpdate = true;
    if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
    if (futureDots) futureDots.instanceMatrix.needsUpdate = true;
  }

  host.addEventListener("pointermove", (event) => {
    const hit = stage.pick(event, [dots, futureDots].filter(Boolean));
    host.style.cursor = hit ? "crosshair" : "grab";
    if (!hit) return;
    const isFuture = hit.object === futureDots;
    const item = isFuture ? futureDots.userData.items[hit.instanceId] : points[hit.instanceId];
    const [year, month] = item.date.split("-");
    readout.replaceChildren(el("b", { text: `${MONTHS_FULL[+month - 1]} ${year}` }),
      `${isFuture ? "Прогноз: " : ""}${fmt(item.value, 2)} Мт CO₂ от электростанций`);
  });

  subscribe((_, changed) => {
    if (changed.includes("view")) {
      active = state.view === "seasons";
      stage.setActive(active);
      if (active) rebuild();
    } else if (active && changed.includes("iso")) rebuild();
    else if (active && changed.includes("year")) highlight();
  });
}
