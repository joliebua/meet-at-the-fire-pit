import * as THREE from "three";

/** A chunky extruded heart, centred on the origin, about one unit tall. */
export function heartGeometry(): THREE.ExtrudeGeometry {
  const s = new THREE.Shape();
  s.moveTo(0, -0.5);
  s.bezierCurveTo(-0.15, -0.35, -0.55, -0.1, -0.55, 0.18);
  s.bezierCurveTo(-0.55, 0.42, -0.36, 0.55, -0.2, 0.55);
  s.bezierCurveTo(-0.08, 0.55, 0, 0.47, 0, 0.36);
  s.bezierCurveTo(0, 0.47, 0.08, 0.55, 0.2, 0.55);
  s.bezierCurveTo(0.36, 0.55, 0.55, 0.42, 0.55, 0.18);
  s.bezierCurveTo(0.55, -0.1, 0.15, -0.35, 0, -0.5);
  const g = new THREE.ExtrudeGeometry(s, { depth: 0.22, bevelEnabled: true, bevelSize: 0.06, bevelThickness: 0.06, bevelSegments: 3, curveSegments: 18 });
  g.center();
  return g;
}

export const PALETTE = {
  hot: 0xff2e93,
  hotSoft: 0xff7ab8,
  gold: 0xffd23f,
  pool: 0x29e6d6,
  poolDeep: 0x0c8fa3,
  bad: 0xff5a5a,
  leaf: 0x1f9d6b,
  trunk: 0x8a5a3c,
  deck: 0xffe6f2,
};

export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export const prefersReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
