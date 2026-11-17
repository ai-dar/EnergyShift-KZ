// Общая сцена three.js для разделов «Энергобаланс» и «Сезоны»: рендер, камера, вращение мышью, подписи поверх canvas.
/* global THREE */

export function createStage(host, { position, target, fov = 32, minDistance = 10, maxDistance = 90 }) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  host.append(renderer.domElement);
  const labelLayer = document.createElement("div");
  labelLayer.style.cssText = "position:absolute;inset:0;overflow:hidden;pointer-events:none";
  host.append(labelLayer);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 600);
  camera.position.set(...position);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.target.set(...target);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = minDistance;
  controls.maxDistance = maxDistance;
  controls.maxPolarAngle = Math.PI * 0.62;

  scene.add(new THREE.AmbientLight(0xffffff, 0.62));
  const key = new THREE.DirectionalLight(0xfff1dc, 0.95);
  key.position.set(12, 30, 22);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x8a5cff, 0.45);
  rim.position.set(-20, 10, -18);
  scene.add(rim);

  const labels = [];
  const direction = new THREE.Vector3(...position).sub(new THREE.Vector3(...target)).normalize();
  let fit = null;
  const frameHooks = new Set();
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const probe = new THREE.Vector3();
  let active = false;

  function resize() {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = `${w}px`;
    renderer.domElement.style.height = `${h}px`;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    applyFit();
  }

  // Отодвинуть камеру так, чтобы объект заданной полуширины и полувысоты целиком поместился в кадр.
  function applyFit() {
    if (!fit) return;
    const t = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const distance = Math.max(fit.halfWidth / (t * camera.aspect), fit.halfHeight / t) * 1.08;
    controls.target.set(0, fit.centerY, 0);
    camera.position.copy(controls.target).addScaledVector(direction, distance);
    controls.maxDistance = Math.max(controls.maxDistance, distance * 1.6);
  }
  new ResizeObserver(resize).observe(host);

  function frame() {
    if (!active) return;
    controls.update();
    frameHooks.forEach((fn) => fn(performance.now()));
    renderer.render(scene, camera);
    const w = host.clientWidth, h = host.clientHeight;
    for (const label of labels) {
      probe.copy(label.position).project(camera);
      const visible = probe.z < 1 && Math.abs(probe.x) < 1.05 && Math.abs(probe.y) < 1.05;
      label.node.style.display = visible ? "" : "none";
      if (visible) {
        label.node.style.left = `${((probe.x + 1) / 2) * w}px`;
        label.node.style.top = `${((1 - probe.y) / 2) * h}px`;
      }
    }
    requestAnimationFrame(frame);
  }

  return {
    scene, camera, controls, renderer,
    onFrame: (fn) => frameHooks.add(fn),
    frameTo(box) { fit = box; applyFit(); },
    offFrame: (fn) => frameHooks.delete(fn),
    setActive(on) {
      if (on === active) return;
      active = on;
      if (on) { resize(); requestAnimationFrame(frame); }
    },
    addLabel(text, position, cls = "") {
      const node = document.createElement("span");
      node.className = `scene-label ${cls}`.trim();
      node.textContent = text;
      labelLayer.append(node);
      const label = { node, position: position.clone() };
      labels.push(label);
      return label;
    },
    clearLabels() {
      labels.splice(0).forEach((l) => l.node.remove());
    },
    // Первый объект под указателем мыши.
    pick(event, objects) {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      return raycaster.intersectObjects(objects, false)[0] || null;
    },
  };
}

export function disposeGroup(group) {
  group.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
  });
  group.parent?.remove(group);
}

// Плавный рост сцены снизу вверх после смены данных — ответ на действие пользователя.
export function growIn(group, stage, reduced, ms = 650) {
  if (reduced) { group.scale.y = 1; return; }
  const start = performance.now();
  group.scale.y = 0.001;
  const tick = (now) => {
    const t = Math.min(1, (now - start) / ms);
    group.scale.y = 1 - Math.pow(1 - t, 3);
    if (t >= 1) stage.offFrame(tick);
  };
  stage.onFrame(tick);
}
