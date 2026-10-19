import { useEffect, useRef } from "react";
import * as THREE from "three";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { heartGeometry, PALETTE, prefersReducedMotion, webglAvailable } from "./heart";

export type Bar = { label: string; value: number; sub?: string; highlight?: boolean };

type Pillar = {
  group: THREE.Group;
  column: THREE.Mesh<THREE.CylinderGeometry, THREE.MeshStandardMaterial>;
  heart: THREE.Mesh;
  label: CSS2DObject;
  target: number;
  current: number;
  x: number;
};

const POOL_W = 13;
const POOL_D = 6;
const MAX_H = 2.9;

function skyMaterial() {
  return new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      top: { value: new THREE.Color(0x1d0730) },
      mid: { value: new THREE.Color(0x9c1f6e) },
      low: { value: new THREE.Color(0xff8a3d) },
    },
    vertexShader: "varying vec3 vPos; void main(){ vPos = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 low; varying vec3 vPos;
      void main(){ float h = vPos.y; vec3 c = h > 0.18 ? mix(mid, top, smoothstep(0.18, 0.75, h)) : mix(low, mid, smoothstep(-0.05, 0.18, h));
      gl_FragColor = vec4(c, 1.0); }`,
  });
}

function glowTexture(color: string) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, color);
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

function palm(x: number, z: number, lean: number) {
  const tree = new THREE.Group();
  const trunkMat = new THREE.MeshStandardMaterial({ color: PALETTE.trunk, roughness: 0.9, flatShading: true });
  let y = 0;
  let px = 0;
  for (let i = 0; i < 7; i++) {
    const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.12 - i * 0.008, 0.15 - i * 0.008, 0.55, 7), trunkMat);
    px += lean * i * 0.035;
    seg.position.set(px, y + 0.27, 0);
    seg.rotation.z = -lean * 0.12;
    tree.add(seg);
    y += 0.5;
  }
  const leafMat = new THREE.MeshStandardMaterial({ color: PALETTE.leaf, emissive: 0x0b4d33, emissiveIntensity: 0.4, flatShading: true, side: THREE.DoubleSide });
  for (let i = 0; i < 7; i++) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(1, 8, 4), leafMat);
    leaf.scale.set(1.15, 0.07, 0.26);
    const a = (i / 7) * Math.PI * 2;
    leaf.position.set(px + Math.cos(a) * 0.75, y + 0.02, Math.sin(a) * 0.75);
    leaf.rotation.set(0, -a, -0.45);
    tree.add(leaf);
  }
  tree.position.set(x, 0, z);
  return tree;
}

type FirePit = { group: THREE.Group; flames: THREE.Mesh[]; light: THREE.PointLight; embers: THREE.Points; seeds: number[] };

/** The villa fire pit: a ring of stones, crossed logs, flickering flames, rising embers and a warm light. */
function firePit(track: <T extends { dispose: () => void }>(x: T) => T, glow: THREE.Texture): FirePit {
  const group = new THREE.Group();
  const stoneMat = track(new THREE.MeshStandardMaterial({ color: 0x6b4a6e, roughness: 0.95, flatShading: true }));
  const stoneGeo = track(new THREE.DodecahedronGeometry(0.2, 0));
  for (let i = 0; i < 11; i++) {
    const a = (i / 11) * Math.PI * 2;
    const stone = new THREE.Mesh(stoneGeo, stoneMat);
    stone.position.set(Math.cos(a) * 0.62, 0.12, Math.sin(a) * 0.62);
    stone.rotation.set(a, a * 2, 0);
    stone.scale.set(1.1, 0.75, 1);
    group.add(stone);
  }
  const logMat = track(new THREE.MeshStandardMaterial({ color: PALETTE.trunk, roughness: 0.9, flatShading: true }));
  const logGeo = track(new THREE.CylinderGeometry(0.07, 0.08, 0.9, 6));
  for (const a of [0, Math.PI / 3, (2 * Math.PI) / 3]) {
    const log = new THREE.Mesh(logGeo, logMat);
    log.rotation.set(Math.PI / 2, 0, a);
    log.position.y = 0.14;
    group.add(log);
  }
  const flames: THREE.Mesh[] = [];
  const colors = [0xff3d00, 0xff8a3d, 0xffb02e, 0xffd23f, 0xff6a1f];
  for (let i = 0; i < 5; i++) {
    const h = 0.75 + (i % 3) * 0.2;
    const geo = track(new THREE.ConeGeometry(0.16 + (i % 2) * 0.06, h, 7, 1, true));
    geo.translate(0, h / 2, 0);
    const mat = track(new THREE.MeshBasicMaterial({ color: colors[i], transparent: true, opacity: 0.85,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    const flame = new THREE.Mesh(geo, mat);
    const a = (i / 5) * Math.PI * 2;
    flame.position.set(Math.cos(a) * 0.16, 0.18, Math.sin(a) * 0.16);
    group.add(flame);
    flames.push(flame);
  }
  const halo = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: glow, color: 0xff8a3d, transparent: true,
    depthWrite: false, blending: THREE.AdditiveBlending })));
  halo.scale.set(3.4, 3.4, 1);
  halo.position.y = 0.7;
  group.add(halo);
  const light = new THREE.PointLight(0xff8a3d, 22, 9);
  light.position.y = 0.9;
  group.add(light);
  const count = 26;
  const positions = new Float32Array(count * 3);
  const seeds = Array.from({ length: count }, () => Math.random());
  const emberGeo = track(new THREE.BufferGeometry());
  emberGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const embers = new THREE.Points(emberGeo, track(new THREE.PointsMaterial({ color: 0xffb02e, size: 0.07, transparent: true,
    opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })));
  group.add(embers);
  return { group, flames, light, embers, seeds };
}

export default function Villa3D({ bars, height = 320, caption }: { bars: Bar[]; height?: number; caption?: string }) {
  const mount = useRef<HTMLDivElement>(null);
  const api = useRef<{ setBars: (b: Bar[]) => void } | null>(null);
  const latest = useRef(bars);
  latest.current = bars;
  const ok = useRef(webglAvailable());

  useEffect(() => {
    const el = mount.current;
    if (!el || !ok.current) return;
    const reduce = prefersReducedMotion();
    const width = el.clientWidth || 800;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.setSize(width, height);
    labels.domElement.className = "villa3d-labels";
    el.appendChild(labels.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x9c1f6e, 22, 48);
    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 200);
    const disposables: { dispose: () => void }[] = [];
    const track = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x);

    // sky, sun, lights
    scene.add(new THREE.Mesh(track(new THREE.SphereGeometry(80, 32, 16)), track(skyMaterial())));
    const sun = new THREE.Mesh(track(new THREE.SphereGeometry(2.4, 32, 16)), track(new THREE.MeshBasicMaterial({ color: PALETTE.gold })));
    sun.position.set(9, 4.5, -30);
    scene.add(sun);
    const glow = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: track(glowTexture("rgba(255,170,80,0.9)")), transparent: true, depthWrite: false })));
    glow.scale.set(16, 16, 1);
    glow.position.copy(sun.position);
    scene.add(glow);
    scene.add(new THREE.HemisphereLight(0xffd6e8, 0x2a0a3f, 1.1));
    const key = new THREE.DirectionalLight(0xffb38a, 1.6);
    key.position.set(6, 8, 6);
    scene.add(key);
    const rim = new THREE.PointLight(PALETTE.hot, 30, 20);
    rim.position.set(0, 4, 3);
    scene.add(rim);

    // pool water (low-poly, rippling) + deck
    const waterGeo = track(new THREE.PlaneGeometry(POOL_W, POOL_D, 60, 28));
    waterGeo.rotateX(-Math.PI / 2);
    const water = new THREE.Mesh(waterGeo, track(new THREE.MeshStandardMaterial({
      color: PALETTE.pool, emissive: PALETTE.poolDeep, emissiveIntensity: 0.45, roughness: 0.15, metalness: 0.2,
      flatShading: true,
    })));
    water.position.y = 0.16; // ripples stay above the ground plane
    scene.add(water);
    const base = waterGeo.attributes.position.array.slice() as Float32Array;
    const deckMat = track(new THREE.MeshStandardMaterial({ color: PALETTE.deck, roughness: 0.7 }));
    for (const [w, d, x, z] of [[POOL_W + 1.2, 0.6, 0, POOL_D / 2 + 0.3], [POOL_W + 1.2, 0.6, 0, -POOL_D / 2 - 0.3],
                                [0.6, POOL_D, POOL_W / 2 + 0.3, 0], [0.6, POOL_D, -POOL_W / 2 - 0.3, 0]]) {
      const slab = new THREE.Mesh(track(new THREE.BoxGeometry(w, 0.25, d)), deckMat);
      slab.position.set(x, 0.05, z);
      scene.add(slab);
    }
    const ground = new THREE.Mesh(track(new THREE.PlaneGeometry(120, 120)), track(new THREE.MeshStandardMaterial({ color: 0x3b0f3d, roughness: 1 })));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.05;
    scene.add(ground);
    for (const [x, z, lean] of [[-8.2, -2.4, 1], [-7.4, 1.6, 0.6], [8.3, -1.8, -1], [7.6, 2.2, -0.5]]) scene.add(palm(x, z, lean));
    const pit = firePit(track, track(glowTexture("rgba(255,170,80,0.9)")));
    pit.group.position.set(-5.2, 0.05, 4.5);
    pit.group.scale.setScalar(1.3);
    scene.add(pit.group);

    // pillars
    const heartGeo = track(heartGeometry());
    const pillars = new Map<string, Pillar>();
    const pillarGeo = track(new THREE.CylinderGeometry(0.34, 0.42, 1, 28));
    pillarGeo.translate(0, 0.5, 0);

    function makePillar(bar: Bar): Pillar {
      const color = bar.highlight ? PALETTE.gold : PALETTE.hot;
      const column = new THREE.Mesh(pillarGeo, new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.75, roughness: 0.25, metalness: 0.3 }));
      const heart = new THREE.Mesh(heartGeo, new THREE.MeshStandardMaterial({ color: bar.highlight ? PALETTE.gold : PALETTE.hotSoft, emissive: color, emissiveIntensity: 0.9 }));
      heart.scale.setScalar(0.8);
      const div = document.createElement("div");
      div.className = "villa3d-label";
      const label = new CSS2DObject(div);
      const group = new THREE.Group();
      group.add(column, heart, label);
      scene.add(group);
      return { group, column, heart, label, target: 0.2, current: 0.05, x: 0 };
    }

    function setBars(next: Bar[]) {
      const max = Math.max(1, ...next.map((b) => Math.abs(b.value)));
      const spacing = Math.min(2.4, (POOL_W - 2) / Math.max(1, next.length - 1 || 1));
      const seen = new Set<string>();
      next.forEach((b, i) => {
        seen.add(b.label);
        const p = pillars.get(b.label) ?? makePillar(b);
        pillars.set(b.label, p);
        p.x = (i - (next.length - 1) / 2) * spacing;
        p.group.position.set(p.x, 0, 0.2);
        p.target = Math.max(0.2, (Math.max(0, b.value) / max) * MAX_H);
        const color = b.value < 0 ? PALETTE.bad : b.highlight ? PALETTE.gold : PALETTE.hot;
        p.column.material.color.setHex(color);
        p.column.material.emissive.setHex(color);
        (p.label.element as HTMLDivElement).innerHTML =
          `<b>${b.label}</b><span>${b.value}</span>${b.sub ? `<small>${b.sub}</small>` : ""}`;
        (p.label.element as HTMLDivElement).classList.toggle("you", !!b.highlight);
      });
      for (const [k, p] of pillars) {
        if (!seen.has(k)) {
          scene.remove(p.group);
          p.column.material.dispose();
          (p.heart.material as THREE.Material).dispose();
          p.label.element.remove();
          pillars.delete(k);
        }
      }
    }
    api.current = { setBars };
    setBars(latest.current);

    // animation
    let frame = 0;
    let raf = 0;
    const pos = waterGeo.attributes.position;
    const tick = () => {
      frame += 1;
      const t = frame / 60;
      if (!reduce) {
        for (let i = 0; i < pos.count; i++) {
          const x = base[i * 3];
          const z = base[i * 3 + 2];
          pos.setY(i, Math.sin(x * 1.3 + t * 1.6) * 0.06 + Math.cos(z * 1.7 + t * 1.2) * 0.05);
        }
        pos.needsUpdate = true;
        waterGeo.computeVertexNormals();
      }
      for (const p of pillars.values()) {
        p.current += (p.target - p.current) * (reduce ? 1 : 0.06);
        p.column.scale.y = p.current;
        p.heart.position.y = p.current + 0.6 + (reduce ? 0 : Math.sin(t * 2 + p.x) * 0.08);
        p.heart.rotation.y = reduce ? 0.4 : t * 1.2 + p.x;
        p.label.position.y = p.current + 1.6;
      }
      if (!reduce) {
        pit.flames.forEach((f, i) => {
          const k = Math.sin(t * (7 + i) + i * 1.7) * 0.5 + Math.sin(t * 13.3 + i) * 0.25;
          f.scale.set(1 + k * 0.12, 1 + k * 0.28, 1 + k * 0.12);
          f.rotation.y = t * (0.6 + i * 0.2);
        });
        pit.light.intensity = 20 + Math.sin(t * 11) * 4 + Math.sin(t * 17.7) * 3;
        const ep = pit.embers.geometry.attributes.position as THREE.BufferAttribute;
        pit.seeds.forEach((sd, i) => {
          const life = (t * (0.35 + sd * 0.4) + sd) % 1;
          ep.setXYZ(i, Math.sin(sd * 40 + t * 2) * 0.25 * life, 0.3 + life * 2.2, Math.cos(sd * 30 + t * 1.6) * 0.25 * life);
        });
        ep.needsUpdate = true;
      }
      const a = reduce ? 0 : Math.sin(t * 0.12) * 0.32;
      camera.position.set(Math.sin(a) * 12, 4.6, Math.cos(a) * 12);
      camera.lookAt(0, 1.5, 0);
      renderer.render(scene, camera);
      labels.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();

    const ro = new ResizeObserver(() => {
      const w = el.clientWidth || width;
      renderer.setSize(w, height);
      labels.setSize(w, height);
      camera.aspect = w / height;
      camera.updateProjectionMatrix();
    });
    ro.observe(el);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      api.current = null;
      for (const p of pillars.values()) {
        p.column.material.dispose();
        (p.heart.material as THREE.Material).dispose();
      }
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh && !disposables.includes(o.geometry)) o.geometry.dispose();
      });
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      renderer.forceContextLoss(); // free the WebGL context now; browsers only allow a handful
      el.innerHTML = "";
    };
  }, [height]);

  useEffect(() => {
    api.current?.setBars(bars);
  }, [bars]);

  if (!ok.current) {
    return <div className="villa3d fallback" style={{ height }}>🌴 3D villa needs WebGL. Standings are below.</div>;
  }
  return (
    <figure className="villa3d" style={{ margin: 0 }}>
      <div ref={mount} className="villa3d-stage" style={{ height }} />
      {caption && <figcaption className="small muted" style={{ marginTop: 6 }}>{caption}</figcaption>}
    </figure>
  );
}
