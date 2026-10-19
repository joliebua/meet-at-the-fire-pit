import { useEffect, useRef } from "react";
import * as THREE from "three";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { heartGeometry, PALETTE, prefersReducedMotion, webglAvailable } from "./heart";

/**
 * The villa fire pit at night: a round stone fire pit, curved white couches with bright cushions, string
 * lights, the pool glowing behind and the host announcing. League players (or your islanders, each with
 * their partner) sit on the couches; the leader stands up "safe" in a spotlight; a dumped islander leaves
 * a suitcase on their seat. Figures are generic and stylized, not likenesses of real people.
 */
export type Seat = {
  label: string;
  value: number;
  sub?: string;
  highlight?: boolean; // gold name plate (you)
  partner?: string | null; // team mode: sits next to them
  left?: boolean; // dumped / left the villa: suitcase on the seat
};

const R = 3.3; // couch radius around the fire
const SAFE_SPOT = new THREE.Vector3(1.05, 0, 1.55); // where the "safe" islander stands, beside the fire
const STAND_SPOTS = [SAFE_SPOT, new THREE.Vector3(-0.55, 0, 1.75)]; // finale: the two finalists, either side of the fire
const ARC = (75 * Math.PI) / 180; // couch spans -75°..75° behind the fire
const SKIN = [0xf2c9a8, 0xd9a07a, 0xb57650, 0x8a5434, 0x5e3a22, 0xf6d7bf];
const HAIR = [0x1d1410, 0x3b2416, 0x6b4423, 0xc89b5a, 0xe8d18f, 0x2a1a2e];
const OUTFIT = [PALETTE.hot, PALETTE.pool, PALETTE.gold, 0xff8a3d, 0xffffff, 0xb36bff, 0x29d17a];
const CUSHION = [PALETTE.hot, PALETTE.pool, PALETTE.gold, 0xff8a3d, 0xff7ab8];

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return Math.abs(h);
}

const onArc = (theta: number, r = R) => new THREE.Vector3(Math.sin(theta) * r, 0, -Math.cos(theta) * r);

function skyMaterial() {
  return new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: { top: { value: new THREE.Color(0x07031a) }, mid: { value: new THREE.Color(0x240b40) }, low: { value: new THREE.Color(0x6a1f5c) } },
    vertexShader: "varying vec3 vPos; void main(){ vPos = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 low; varying vec3 vPos;
      void main(){ float h = vPos.y; vec3 c = h > 0.12 ? mix(mid, top, smoothstep(0.12, 0.7, h)) : mix(low, mid, smoothstep(-0.05, 0.12, h));
      gl_FragColor = vec4(c, 1.0); }`,
  });
}

function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, "rgba(255,190,110,1)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

type Figure = { group: THREE.Group; legs: THREE.Group[]; torso: THREE.Mesh; stand: number; standTarget: number; phase: number };

/** A stylized islander: hips at the group origin, facing +z. Legs swing from forward (seated) to down (standing). */
function makeFigure(seed: string, track: <T extends { dispose: () => void }>(x: T) => T, scale = 1): Figure {
  const h = hash(seed);
  const skin = track(new THREE.MeshStandardMaterial({ color: SKIN[h % SKIN.length], roughness: 0.7, flatShading: true }));
  const hair = track(new THREE.MeshStandardMaterial({ color: HAIR[(h >> 3) % HAIR.length], roughness: 0.8, flatShading: true }));
  const outfit = track(new THREE.MeshStandardMaterial({ color: OUTFIT[(h >> 6) % OUTFIT.length], roughness: 0.5, flatShading: true }));
  const group = new THREE.Group();
  const torso = new THREE.Mesh(track(new THREE.CapsuleGeometry(0.16, 0.3, 4, 10)), outfit);
  torso.position.y = 0.3;
  const head = new THREE.Mesh(track(new THREE.SphereGeometry(0.15, 16, 12)), skin);
  head.position.y = 0.68;
  const hairCap = new THREE.Mesh(track(new THREE.SphereGeometry(0.16, 16, 8, 0, Math.PI * 2, 0, Math.PI / 1.7)), hair);
  hairCap.position.set(0, 0.7, -0.015);
  const longHair = (h >> 9) % 2 === 0;
  if (longHair) {
    const back = new THREE.Mesh(track(new THREE.CapsuleGeometry(0.12, 0.22, 4, 8)), hair);
    back.position.set(0, 0.52, -0.08);
    group.add(back);
  }
  const armGeo = track(new THREE.CapsuleGeometry(0.05, 0.3, 4, 6));
  for (const x of [-0.22, 0.22]) {
    const arm = new THREE.Mesh(armGeo, skin);
    arm.position.set(x, 0.3, 0.02);
    arm.rotation.z = x > 0 ? -0.15 : 0.15;
    group.add(arm);
  }
  const legGeo = track(new THREE.CapsuleGeometry(0.065, 0.36, 4, 6));
  const legs: THREE.Group[] = [];
  for (const x of [-0.08, 0.08]) {
    const pivot = new THREE.Group();
    const leg = new THREE.Mesh(legGeo, skin);
    leg.position.y = -0.24;
    pivot.add(leg);
    pivot.position.set(x, 0.02, 0);
    group.add(pivot);
    legs.push(pivot);
  }
  group.add(torso, head, hairCap);
  group.scale.setScalar(scale);
  return { group, legs, torso, stand: 0, standTarget: 0, phase: (h % 100) / 16 };
}

function suitcase(track: <T extends { dispose: () => void }>(x: T) => T) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(track(new THREE.BoxGeometry(0.42, 0.32, 0.16)), track(new THREE.MeshStandardMaterial({ color: PALETTE.hotSoft, roughness: 0.4 })));
  body.position.y = 0.16;
  const handle = new THREE.Mesh(track(new THREE.TorusGeometry(0.07, 0.015, 6, 12, Math.PI)), track(new THREE.MeshStandardMaterial({ color: 0x333333 })));
  handle.position.y = 0.33;
  g.add(body, handle);
  return g;
}

function couch(track: <T extends { dispose: () => void }>(x: T) => T) {
  const group = new THREE.Group();
  const white = track(new THREE.MeshStandardMaterial({ color: 0xfff4e8, roughness: 0.85 }));
  const n = 18;
  const span = ARC * 2 + 0.25;
  const segW = ((span * R) / n) * 1.06;
  for (let i = 0; i < n; i++) {
    const theta = -span / 2 + (span * (i + 0.5)) / n;
    const seat = new THREE.Mesh(track(new THREE.BoxGeometry(segW, 0.36, 0.85)), white);
    seat.position.copy(onArc(theta, R)).setY(0.18);
    seat.rotation.y = -theta;
    const back = new THREE.Mesh(track(new THREE.BoxGeometry(segW, 0.75, 0.22)), white);
    back.position.copy(onArc(theta, R + 0.45)).setY(0.5);
    back.rotation.y = -theta;
    const cushion = new THREE.Mesh(track(new THREE.BoxGeometry(segW * 0.7, 0.36, 0.12)),
      track(new THREE.MeshStandardMaterial({ color: CUSHION[i % CUSHION.length], roughness: 0.6 })));
    cushion.position.copy(onArc(theta, R + 0.3)).setY(0.6);
    cushion.rotation.set(-0.15, -theta, 0);
    group.add(seat, back, cushion);
  }
  return group;
}

function stringLights(track: <T extends { dispose: () => void }>(x: T) => T, a: THREE.Vector3, b: THREE.Vector3, sag: number, n: number) {
  const mats = [0, 1].map(() => track(new THREE.MeshStandardMaterial({ color: 0xffe2a8, emissive: 0xffc56b, emissiveIntensity: 1.6 })));
  const bulbGeo = track(new THREE.SphereGeometry(0.055, 8, 6));
  const group = new THREE.Group();
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const p = a.clone().lerp(b, t);
    p.y -= Math.sin(Math.PI * t) * sag;
    pts.push(p);
    const bulb = new THREE.Mesh(bulbGeo, mats[i % 2]);
    bulb.position.copy(p).setY(p.y - 0.06);
    group.add(bulb);
  }
  const wire = new THREE.Line(track(new THREE.BufferGeometry().setFromPoints(pts)), track(new THREE.LineBasicMaterial({ color: 0x1a1020 })));
  group.add(wire);
  return { group, mats };
}

function palm(track: <T extends { dispose: () => void }>(x: T) => T, x: number, z: number, lean: number) {
  const tree = new THREE.Group();
  const trunkMat = track(new THREE.MeshStandardMaterial({ color: 0x3a2418, roughness: 0.9, flatShading: true }));
  let y = 0;
  let px = 0;
  for (let i = 0; i < 8; i++) {
    const seg = new THREE.Mesh(track(new THREE.CylinderGeometry(0.13 - i * 0.008, 0.16 - i * 0.008, 0.6, 7)), trunkMat);
    px += lean * i * 0.035;
    seg.position.set(px, y + 0.3, 0);
    tree.add(seg);
    y += 0.55;
  }
  const leafMat = track(new THREE.MeshStandardMaterial({ color: 0x0f3d2c, roughness: 0.8, flatShading: true, side: THREE.DoubleSide }));
  const leafGeo = track(new THREE.SphereGeometry(1, 8, 4));
  for (let i = 0; i < 7; i++) {
    const leaf = new THREE.Mesh(leafGeo, leafMat);
    leaf.scale.set(1.3, 0.07, 0.28);
    const a = (i / 7) * Math.PI * 2;
    leaf.position.set(px + Math.cos(a) * 0.85, y, Math.sin(a) * 0.85);
    leaf.rotation.set(0, -a, -0.45);
    tree.add(leaf);
  }
  tree.position.set(x, 0, z);
  return { tree, top: new THREE.Vector3(x + px, y, z) };
}

export default function FirePitScene({ seats, height = 340, caption, mode = "standings", standers = 1, envelopes = false }:
  { seats: Seat[]; height?: number; caption?: string; mode?: "standings" | "team"; standers?: number; envelopes?: boolean }) {
  const mount = useRef<HTMLDivElement>(null);
  const api = useRef<{ setSeats: (s: Seat[]) => void } | null>(null);
  const latest = useRef(seats);
  latest.current = seats;
  const ok = useRef(webglAvailable());

  useEffect(() => {
    const el = mount.current;
    if (!el || !ok.current) return;
    const reduce = prefersReducedMotion();
    const width = el.clientWidth || 800;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.setSize(width, height);
    labels.domElement.className = "villa3d-labels";
    el.appendChild(labels.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x240b40, 16, 40);
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 200);
    const disposables: { dispose: () => void }[] = [];
    const track = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x);
    const glow = track(glowTexture());

    // night sky + stars
    scene.add(new THREE.Mesh(track(new THREE.SphereGeometry(80, 32, 16)), track(skyMaterial())));
    const starPos = new Float32Array(500 * 3);
    for (let i = 0; i < 500; i++) {
      const u = Math.random() * Math.PI * 2;
      const v = 0.15 + Math.random() * 0.8;
      starPos.set([Math.cos(u) * 70 * Math.cos(v), 70 * Math.sin(v), Math.sin(u) * 70 * Math.cos(v)], i * 3);
    }
    const starGeo = track(new THREE.BufferGeometry());
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    scene.add(new THREE.Points(starGeo, track(new THREE.PointsMaterial({ color: 0xffffff, size: 0.35, sizeAttenuation: true, transparent: true, opacity: 0.8 }))));

    // lights: dusky fill + the fire does the rest
    scene.add(new THREE.HemisphereLight(0x8a6bd6, 0x1a0a1f, 0.55));
    const moon = new THREE.DirectionalLight(0xb7a6ff, 0.35);
    moon.position.set(-6, 10, -4);
    scene.add(moon);
    const fill = new THREE.PointLight(0xffd0e6, 9, 14, 1.4); // soft light from the camera side so faces read
    fill.position.set(0, 3.2, 5.5);
    scene.add(fill);

    // deck, rug, pool behind, villa lights
    const deck = new THREE.Mesh(track(new THREE.CircleGeometry(9, 48)), track(new THREE.MeshStandardMaterial({ color: 0x5a3a2c, roughness: 0.95 })));
    deck.rotation.x = -Math.PI / 2;
    scene.add(deck);
    const rug = new THREE.Mesh(track(new THREE.RingGeometry(1.3, 2.75, 48)), track(new THREE.MeshStandardMaterial({ color: 0x8a3f5f, roughness: 1 })));
    rug.rotation.x = -Math.PI / 2;
    rug.position.y = 0.01;
    scene.add(rug);
    const pool = new THREE.Mesh(track(new THREE.PlaneGeometry(16, 3.2, 1, 1)), track(new THREE.MeshStandardMaterial({
      color: PALETTE.pool, emissive: PALETTE.poolDeep, emissiveIntensity: 1.1, roughness: 0.2 })));
    pool.rotation.x = -Math.PI / 2;
    pool.position.set(0, 0.02, -7.6);
    scene.add(pool);
    const poolGlow = new THREE.PointLight(PALETTE.pool, 18, 10);
    poolGlow.position.set(0, 1, -7.6);
    scene.add(poolGlow);
    const villa = new THREE.Mesh(track(new THREE.BoxGeometry(22, 3.2, 1)), track(new THREE.MeshStandardMaterial({ color: 0x1b0f26, roughness: 1 })));
    villa.position.set(0, 1.6, -11.5);
    scene.add(villa);
    const windowMat = track(new THREE.MeshStandardMaterial({ color: 0xffd9a0, emissive: 0xffb36b, emissiveIntensity: 1.2 }));
    const windowGeo = track(new THREE.PlaneGeometry(1.1, 0.7));
    for (let i = -4; i <= 4; i++) {
      const w = new THREE.Mesh(windowGeo, windowMat);
      w.position.set(i * 2.3, 1.7 + (i % 2) * 0.1, -10.98);
      scene.add(w);
    }

    // palms + string lights over the couches
    const palms = [palm(track, -7.2, -4.2, 0.8), palm(track, 7.2, -4.4, -0.8), palm(track, -8.5, 1.2, 0.5), palm(track, 8.4, 1.0, -0.5)];
    palms.forEach((p) => scene.add(p.tree));
    const strands = [
      stringLights(track, palms[0].top.clone().setY(3.9), palms[1].top.clone().setY(3.9), 1.0, 30),
      stringLights(track, new THREE.Vector3(-6.2, 3.3, -0.5), new THREE.Vector3(6.2, 3.3, -0.5), 0.8, 26),
    ];
    strands.forEach((s) => scene.add(s.group));

    // couches + fire pit
    scene.add(couch(track));
    const pit = new THREE.Group();
    const stone = track(new THREE.MeshStandardMaterial({ color: 0x4a3b4f, roughness: 0.9, flatShading: true }));
    const bowl = new THREE.Mesh(track(new THREE.CylinderGeometry(0.85, 1.0, 0.42, 28)), stone);
    bowl.position.y = 0.21;
    const inner = new THREE.Mesh(track(new THREE.CircleGeometry(0.72, 28)), track(new THREE.MeshStandardMaterial({ color: 0x1a0f0f, roughness: 1 })));
    inner.rotation.x = -Math.PI / 2;
    inner.position.y = 0.425;
    pit.add(bowl, inner);
    const logMat = track(new THREE.MeshStandardMaterial({ color: 0x5a3a24, roughness: 0.9, flatShading: true }));
    const logGeo = track(new THREE.CylinderGeometry(0.07, 0.08, 1.0, 6));
    for (const a of [0, Math.PI / 3, (2 * Math.PI) / 3]) {
      const log = new THREE.Mesh(logGeo, logMat);
      log.rotation.set(Math.PI / 2, 0, a);
      log.position.y = 0.5;
      pit.add(log);
    }
    const flames: THREE.Mesh[] = [];
    const flameColors = [0xff3d00, 0xff8a3d, 0xffb02e, 0xffd23f, 0xff6a1f, 0xff8a3d];
    flameColors.forEach((c, i) => {
      const fh = 0.8 + (i % 3) * 0.25;
      const g = track(new THREE.ConeGeometry(0.18 + (i % 2) * 0.07, fh, 7, 1, true));
      g.translate(0, fh / 2, 0);
      const f = new THREE.Mesh(g, track(new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.85,
        blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide })));
      const a = (i / flameColors.length) * Math.PI * 2;
      f.position.set(Math.cos(a) * 0.18, 0.5, Math.sin(a) * 0.18);
      pit.add(f);
      flames.push(f);
    });
    const halo = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: glow, color: 0xff8a3d, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
    halo.scale.set(3.0, 3.0, 1);
    halo.position.y = 0.9;
    pit.add(halo);
    const fireLight = new THREE.PointLight(0xff9a4d, 38, 12, 1.6);
    fireLight.position.y = 1.2;
    pit.add(fireLight);
    const emberCount = 40;
    const emberSeeds = Array.from({ length: emberCount }, () => Math.random());
    const emberGeo = track(new THREE.BufferGeometry());
    emberGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(emberCount * 3), 3));
    const embers = new THREE.Points(emberGeo, track(new THREE.PointsMaterial({ color: 0xffb02e, size: 0.07, transparent: true,
      opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })));
    pit.add(embers);
    scene.add(pit);

    // the host, standing by the fire with the phone ("I got a text!")
    const hostFig = makeFigure("host-of-the-villa", track, 1.08);
    hostFig.stand = hostFig.standTarget = 1;
    const dress = new THREE.Mesh(track(new THREE.ConeGeometry(0.3, 0.75, 14, 1, true)),
      track(new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.6, roughness: 0.3, side: THREE.DoubleSide })));
    dress.position.y = 0.05;
    hostFig.group.add(dress);
    const phone = new THREE.Mesh(track(new THREE.BoxGeometry(0.09, 0.16, 0.015)),
      track(new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xbfe9ff, emissiveIntensity: 1.5 })));
    phone.position.set(0.2, 0.42, 0.18);
    phone.rotation.x = -0.5;
    hostFig.group.add(phone);
    hostFig.group.position.set(-2.05, 0.5, 1.9);
    hostFig.group.rotation.y = Math.PI * 0.86;
    scene.add(hostFig.group);
    const hostDiv = document.createElement("div");
    hostDiv.className = "villa3d-label host";
    hostDiv.innerHTML = "<b>🎙️ Host</b><small>“Islanders…”</small>";
    const hostLabel = new CSS2DObject(hostDiv);
    hostLabel.position.set(0, 1.25, 0);
    hostFig.group.add(hostLabel);

    // spotlight + rings for whoever is standing by the fire
    const spot = new THREE.SpotLight(0xffd6ec, 40, 12, 0.35, 0.6, 1.2);
    spot.position.set(0, 7, 2);
    scene.add(spot, spot.target);
    const ringGeo = track(new THREE.RingGeometry(0.35, 0.5, 32));
    const ringMat = track(new THREE.MeshBasicMaterial({ color: PALETTE.hot, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
    const rings = STAND_SPOTS.map(() => {
      const r = new THREE.Mesh(ringGeo, ringMat);
      r.rotation.x = -Math.PI / 2;
      r.visible = false;
      scene.add(r);
      return r;
    });
    const envelopeGeo = track(new THREE.BoxGeometry(0.2, 0.13, 0.012));
    const envelopeMat = track(new THREE.MeshStandardMaterial({ color: 0xfffaf2, emissive: 0xffe6f2, emissiveIntensity: 0.35 }));
    const sealGeo = track(new THREE.CircleGeometry(0.03, 16));
    const sealMat = track(new THREE.MeshBasicMaterial({ color: PALETTE.hot }));
    const heart = new THREE.Mesh(track(heartGeometry()), track(new THREE.MeshStandardMaterial({ color: PALETTE.hot, emissive: PALETTE.hot, emissiveIntensity: 0.9 })));
    heart.scale.setScalar(0.32);
    heart.visible = false;
    scene.add(heart);

    // seated people (rebuilt whenever the seats change)
    let people: { fig?: Figure; label: CSS2DObject; extra: THREE.Object3D[]; home: THREE.Vector3; theta: number; leader: boolean; standIdx: number }[] = [];
    const personBits: { dispose: () => void }[] = [];
    const trackPerson = <T extends { dispose: () => void }>(x: T) => (personBits.push(x), x);

    function clearPeople() {
      for (const p of people) {
        if (p.fig) scene.remove(p.fig.group);
        p.extra.forEach((o) => scene.remove(o));
        p.label.element.remove();
        scene.remove(p.label);
      }
      personBits.splice(0).forEach((d) => d.dispose());
      people = [];
    }

    function label(html: string, cls: string) {
      const div = document.createElement("div");
      div.className = `villa3d-label ${cls}`;
      div.innerHTML = html;
      return new CSS2DObject(div);
    }

    function setSeats(next: Seat[]) {
      clearPeople();
      // Seat order: the first seat (leader / your best) in the middle, then alternating outward.
      const perSeat = mode === "team" ? 2 : 1;
      const slots = Math.max(1, next.length * perSeat);
      const step = Math.min(mode === "team" ? 0.3 : 0.62, (ARC * 2) / Math.max(1, slots - 1 || 1));
      const thetas: number[] = [];
      for (let i = 0; i < next.length; i++) {
        const k = i === 0 ? 0 : Math.ceil(i / 2) * (i % 2 ? 1 : -1);
        thetas.push(k * step * (mode === "team" ? perSeat * 1.05 : 1));
      }
      next.forEach((s, i) => {
        const theta = thetas[i];
        const standIdx = mode === "standings" && i < Math.min(standers, STAND_SPOTS.length) ? i : -1;
        const leader = standIdx === 0;
        const extra: THREE.Object3D[] = [];
        const home = onArc(theta, R).setY(0.4);
        let fig: Figure | undefined;
        if (s.left) {
          const bag = suitcase(trackPerson);
          bag.position.copy(onArc(theta, R)).setY(0.36);
          bag.rotation.y = -theta;
          scene.add(bag);
          extra.push(bag);
        } else {
          fig = makeFigure(s.label, trackPerson);
          fig.group.position.copy(home);
          fig.group.rotation.y = -theta; // face the fire
          fig.standTarget = standIdx >= 0 ? 1 : 0;
          if (envelopes && standIdx >= 0) {
            const env = new THREE.Mesh(envelopeGeo, envelopeMat);
            env.position.set(0.24, 0.3, 0.16);
            env.rotation.set(-0.4, 0.3, 0.1);
            const seal = new THREE.Mesh(sealGeo, sealMat);
            seal.position.z = 0.007;
            env.add(seal);
            fig.group.add(env);
          }
          scene.add(fig.group);
          if (mode === "team" && s.partner) {
            const pt = theta + step * 0.95 * (theta >= 0 ? 1 : -1);
            const partner = makeFigure(s.partner, trackPerson, 0.96);
            partner.group.position.copy(onArc(pt, R).setY(0.4));
            partner.group.rotation.y = -pt;
            partner.legs.forEach((l) => (l.rotation.x = -Math.PI / 2));
            scene.add(partner.group);
            extra.push(partner.group);
          }
        }
        const pts = s.value > 0 ? `+${s.value}` : `${s.value}`;
        const lab = label(`<b>${s.label}${leader && !envelopes ? " 💖" : envelopes && standIdx >= 0 ? " ✉️" : ""}</b><span>${mode === "team" ? pts : s.value}</span>${s.sub ? `<small>${s.sub}</small>` : ""}`,
          `${s.highlight ? "you" : ""} ${standIdx >= 0 ? "safe" : ""} ${s.left ? "gone" : ""}`);
        scene.add(lab);
        people.push({ fig, label: lab, extra, home, theta, leader, standIdx });
      });
      const standing = people.filter((p) => p.standIdx >= 0 && p.fig);
      rings.forEach((r, k) => {
        r.visible = standing.some((p) => p.standIdx === k);
        r.position.copy(STAND_SPOTS[k]).setY(0.02);
      });
      heart.visible = !envelopes && standing.some((p) => p.leader);
      if (standing.length) {
        const mid = new THREE.Vector3();
        standing.forEach((p) => mid.add(STAND_SPOTS[p.standIdx]));
        spot.target.position.copy(mid.divideScalar(standing.length));
      } else {
        spot.target.position.set(0, 0, 0);
      }
    }
    api.current = { setSeats };
    setSeats(latest.current);

    // animation
    let raf = 0;
    const start = performance.now();
    let last = start;
    const tick = () => {
      const now = performance.now();
      const t = (now - start) / 1000;
      const dt = Math.min(0.25, (now - last) / 1000); // time-based, so slow or background tabs still animate correctly
      last = now;
      const ep = emberGeo.attributes.position as THREE.BufferAttribute;
      if (!reduce) {
        flames.forEach((f, i) => {
          const k = Math.sin(t * (7 + i) + i * 1.7) * 0.5 + Math.sin(t * 13.3 + i) * 0.25;
          f.scale.set(1 + k * 0.12, 1 + k * 0.3, 1 + k * 0.12);
          f.rotation.y = t * (0.6 + i * 0.2);
        });
        fireLight.intensity = 34 + Math.sin(t * 11) * 6 + Math.sin(t * 17.7) * 4;
        emberSeeds.forEach((sd, i) => {
          const life = (t * (0.3 + sd * 0.4) + sd) % 1;
          ep.setXYZ(i, Math.sin(sd * 40 + t * 2) * 0.35 * life, 0.6 + life * 2.6, Math.cos(sd * 30 + t * 1.6) * 0.35 * life);
        });
        ep.needsUpdate = true;
        strands.forEach((s, j) => s.mats.forEach((m, k) => (m.emissiveIntensity = 1.3 + Math.sin(t * 2.2 + k * 1.9 + j) * 0.5)));
      }
      for (const p of people) {
        if (!p.fig) {
          p.label.position.copy(p.home).setY(1.05);
          continue;
        }
        const f = p.fig;
        f.stand += (f.standTarget - f.stand) * (reduce ? 1 : Math.min(1, dt * 2.2));
        // standing: the leader walks from the couch to the safe spot beside the fire, legs straighten, hips rise
        const target = p.standIdx >= 0 ? STAND_SPOTS[p.standIdx] : null;
        const pos = target ? p.home.clone().setY(0).lerp(target, f.stand) : onArc(p.theta, R);
        f.group.position.set(pos.x, 0.4 + 0.12 * f.stand, pos.z);
        if (target) f.group.rotation.y = -p.theta + ((p.standIdx === 0 ? -0.35 : 0.35) + p.theta) * f.stand; // turn to face the group
        f.legs.forEach((l) => (l.rotation.x = -Math.PI / 2 * (1 - f.stand)));
        f.torso.scale.y = 1 + (reduce ? 0 : Math.sin(t * 1.6 + f.phase) * 0.025);
        p.label.position.set(pos.x, 1.45 + 0.15 * f.stand, pos.z);
        if (p.leader) {
          heart.position.set(pos.x, 1.2 + 0.15 * f.stand + (reduce ? 0 : Math.sin(t * 2) * 0.05), pos.z);
          heart.rotation.y = reduce ? 0.4 : t * 1.4;
        }
      }
      hostFig.legs.forEach((l) => (l.rotation.x = 0));
      if (!reduce) hostFig.group.rotation.y = Math.PI * 0.86 + Math.sin(t * 0.5) * 0.12;
      const a = reduce ? 0 : Math.sin(t * 0.1) * 0.22;
      camera.position.set(Math.sin(a) * 6.4, 2.9, Math.cos(a) * 6.4 - 0.2);
      camera.lookAt(0, 0.95, -1.5);
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
      clearPeople();
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      renderer.forceContextLoss(); // free the WebGL context now; browsers only allow a handful
      el.innerHTML = "";
    };
  }, [height, mode, standers, envelopes]);

  useEffect(() => {
    api.current?.setSeats(seats);
  }, [seats]);

  if (!ok.current) {
    return <div className="villa3d fallback" style={{ height }}>🔥 The 3D fire pit needs WebGL. Standings are below.</div>;
  }
  return (
    <figure className="villa3d" style={{ margin: 0 }}>
      <div ref={mount} className="villa3d-stage" style={{ height }} />
      {caption && <figcaption className="small muted" style={{ marginTop: 6 }}>{caption}</figcaption>}
    </figure>
  );
}
