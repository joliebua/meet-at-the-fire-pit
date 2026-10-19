import { useEffect, useRef } from "react";
import * as THREE from "three";
import { heartGeometry, PALETTE, prefersReducedMotion, webglAvailable } from "./heart";

const COUNT = 46;
const DURATION = 1.9; // seconds

/** Full-screen 3D heart confetti. Bump `burst` (e.g. a counter) to fire it; renders nothing when idle. */
export default function HeartBurst({ burst }: { burst: number }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!burst || !el || !webglAvailable() || prefersReducedMotion()) return;
    const w = window.innerWidth;
    const h = window.innerHeight;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h);
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100);
    camera.position.z = 14;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x662244, 1.4));
    const light = new THREE.DirectionalLight(0xffe0ee, 1.4);
    light.position.set(3, 5, 8);
    scene.add(light);

    const geo = heartGeometry();
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.15, transparent: true });
    const hearts = new THREE.InstancedMesh(geo, mat, COUNT);
    const colors = [PALETTE.hot, PALETTE.hotSoft, PALETTE.gold, PALETTE.pool, 0xffffff];
    const parts = Array.from({ length: COUNT }, (_, i) => {
      hearts.setColorAt(i, new THREE.Color(colors[i % colors.length]));
      const a = Math.random() * Math.PI * 2;
      const speed = 5 + Math.random() * 7;
      return {
        p: new THREE.Vector3(0, -2, 0),
        v: new THREE.Vector3(Math.cos(a) * speed * 0.8, 6 + Math.random() * 7, Math.sin(a) * speed * 0.4),
        r: new THREE.Euler(Math.random() * 3, Math.random() * 3, 0),
        spin: (Math.random() - 0.5) * 8,
        s: 0.35 + Math.random() * 0.45,
      };
    });
    scene.add(hearts);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const start = performance.now();
    let last = start;
    let raf = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = (now - start) / 1000;
      parts.forEach((pt, i) => {
        pt.v.y -= 14 * dt;
        pt.p.addScaledVector(pt.v, dt);
        pt.r.y += pt.spin * dt;
        pt.r.x += pt.spin * 0.4 * dt;
        q.setFromEuler(pt.r);
        m.compose(pt.p, q, new THREE.Vector3(pt.s, pt.s, pt.s));
        hearts.setMatrixAt(i, m);
      });
      hearts.instanceMatrix.needsUpdate = true;
      mat.opacity = Math.max(0, 1 - Math.max(0, t - DURATION * 0.6) / (DURATION * 0.4));
      renderer.render(scene, camera);
      if (t < DURATION) raf = requestAnimationFrame(tick);
      else cleanup();
    };
    raf = requestAnimationFrame(tick);
    let done = false;
    function cleanup() {
      if (done) return;
      done = true;
      cancelAnimationFrame(raf);
      geo.dispose();
      mat.dispose();
      hearts.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    }
    return cleanup;
  }, [burst]);

  return <div ref={host} className="heart-burst" aria-hidden="true" />;
}
