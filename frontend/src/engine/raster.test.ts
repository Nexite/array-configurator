import { describe, expect, it } from "vitest";
import { bestOnAngle, prepareRaster, rasterPhases, releaseRaster } from "./raster.mjs";

function ring(points: number[][]) {
  const first = points[0];
  const last = points[points.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) points = [...points, first];
  return points;
}

function cells(id: number, phase: { u0: number; v0: number; ni: number; nj: number }, px: number, py: number, cw: number, ch: number) {
  const raw = rasterPhases(id, 0, [phase], px, py, cw, ch);
  releaseRaster(id);
  const found = new Set<string>();
  for (let k = 0; k < raw.data.length; k += 2) found.add(`${raw.data[k]},${raw.data[k + 1]}`);
  return found;
}

describe("rasterMask", () => {
  it("returns the fullest panel on an angle", () => {
    const id = prepareRaster([{ exterior: ring([[0, 0], [300, 0], [300, 200], [0, 200]]), holes: [] }]);
    const best = bestOnAngle(id, 0, [{ u0: 0, v0: 0, ni: 4, nj: 3 }], 100, 100, 100, 100, 0, 24, 24);
    releaseRaster(id);
    expect(best?.count).toBe(6);
  });

  it("fills a rectangle on its grid", () => {
    const id = prepareRaster([{ exterior: ring([[0, 0], [300, 0], [300, 200], [0, 200]]), holes: [] }]);
    expect(cells(id, { u0: 0, v0: 0, ni: 4, nj: 3 }, 100, 100, 100, 100)).toEqual(
      new Set(["0,0", "1,0", "2,0", "0,1", "1,1", "2,1"]),
    );
  });

  it("rejects a cell whose corners are inside but an edge crosses it", () => {
    const notch = ring([
      [0, 0],
      [100, 0],
      [100, 100],
      [60, 100],
      [50, 40],
      [40, 100],
      [0, 100],
    ]);
    const id = prepareRaster([{ exterior: notch, holes: [] }]);
    const found = cells(id, { u0: 0, v0: 0, ni: 2, nj: 2 }, 100, 100, 90, 90);
    expect(found.has("0,0")).toBe(false);
  });

  it("rejects a cell that covers a hole and keeps one that misses it", () => {
    const id = prepareRaster([
      {
        exterior: ring([[0, 0], [200, 0], [200, 200], [0, 200]]),
        holes: [ring([[40, 40], [60, 40], [60, 60], [40, 60]])],
      },
    ]);
    const raw = rasterPhases(id, 0, [{ u0: 0, v0: 0, ni: 2, nj: 1 }], 100, 100, 100, 100);
    releaseRaster(id);
    const found = new Set<string>();
    for (let k = 0; k < raw.data.length; k += 2) found.add(`${raw.data[k]},${raw.data[k + 1]}`);
    expect(found.has("0,0")).toBe(false);
    expect(found.has("1,0")).toBe(true);
  });

  it("rejects a cell an edge cuts through, even when every corner is inside", () => {
    const spike = ring([
      [0, 0],
      [300, 0],
      [300, 300],
      [160, 300],
      [150, 140],
      [140, 300],
      [0, 300],
    ]);
    const id = prepareRaster([{ exterior: spike, holes: [] }]);
    const found = cells(id, { u0: 0, v0: 0, ni: 3, nj: 3 }, 100, 100, 90, 90);
    expect(found.has("0,0")).toBe(true);
    expect(found.has("1,1")).toBe(false);
  });

  it("matches a direct edge walk on a wavy outline", () => {
    const points: number[][] = [];
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * Math.PI * 2;
      const wobble = 1 + 0.18 * Math.sin(5 * a);
      points.push([1500 + Math.cos(a) * 900 * wobble, 800 + Math.sin(a) * 500 * wobble]);
    }
    const outline = ring(points);
    const phase = { u0: 700, v0: 350, ni: 9, nj: 10 };
    const id = prepareRaster([{ exterior: outline, holes: [] }]);
    const raw = rasterPhases(id, 17, [phase], 184, 98, 182, 96);
    releaseRaster(id);
    const fast = new Set<string>();
    for (let k = 0; k < raw.data.length; k += 2) fast.add(`${raw.data[k]},${raw.data[k + 1]}`);
    expect(fast).toEqual(bruteCells(outline, 17, phase, 184, 98, 182, 96));
  });
});

function bruteCells(
  outline: number[][],
  angleDeg: number,
  phase: { u0: number; v0: number; ni: number; nj: number },
  px: number,
  py: number,
  cw: number,
  ch: number,
) {
  const rad = (angleDeg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const local = outline.map(([x, y]) => [x * c + y * s, -x * s + y * c]);
  const found = new Set<string>();
  for (let i = 0; i < phase.ni; i++) {
    for (let j = 0; j < phase.nj; j++) {
      const x = phase.u0 + i * px;
      const y = phase.v0 + j * py;
      if (bruteCover(local, x, y, x + cw, y + ch)) found.add(`${i},${j}`);
    }
  }
  return found;
}

function bruteCover(ring: number[][], x0: number, y0: number, x1: number, y1: number) {
  const eps = 1e-6;
  if (![
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ].every(([x, y]) => bruteInside(ring, x, y))) return false;
  const ix0 = x0 + eps;
  const iy0 = y0 + eps;
  const ix1 = x1 - eps;
  const iy1 = y1 - eps;
  for (let i = 0; i < ring.length - 1; i++) {
    if (bruteCuts(ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1], ix0, iy0, ix1, iy1)) return false;
  }
  return true;
}

function bruteInside(ring: number[][], x: number, y: number) {
  let inside = false;
  for (let i = 0; i < ring.length - 1; i++) {
    const x1 = ring[i][0];
    const y1 = ring[i][1];
    const x2 = ring[i + 1][0];
    const y2 = ring[i + 1][1];
    if (y1 > y !== y2 > y) {
      const xint = x1 + ((y - y1) / (y2 - y1)) * (x2 - x1);
      if (x < xint) inside = !inside;
    }
  }
  if (inside) return true;
  const eps = 1e-6;
  for (let i = 0; i < ring.length - 1; i++) {
    const x1 = ring[i][0];
    const y1 = ring[i][1];
    const x2 = ring[i + 1][0];
    const y2 = ring[i + 1][1];
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len2 = dx * dx + dy * dy;
    let t = len2 > 0 ? ((x - x1) * dx + (y - y1) * dy) / len2 : 0;
    if (t < 0) t = 0;
    else if (t > 1) t = 1;
    const px = x1 + t * dx - x;
    const py = y1 + t * dy - y;
    if (Math.hypot(px, py) <= eps) return true;
  }
  return false;
}

function bruteCuts(x1: number, y1: number, x2: number, y2: number, xmin: number, ymin: number, xmax: number, ymax: number) {
  let t0 = 0;
  let t1 = 1;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const p = [-dx, dx, -dy, dy];
  const q = [x1 - xmin, xmax - x1, y1 - ymin, ymax - y1];
  for (let i = 0; i < 4; i++) {
    if (Math.abs(p[i]) < 1e-15) {
      if (q[i] < 0) return false;
      continue;
    }
    const r = q[i] / p[i];
    if (p[i] < 0) {
      if (r > t1) return false;
      if (r > t0) t0 = r;
    } else {
      if (r < t0) return false;
      if (r < t1) t1 = r;
    }
  }
  return t1 - t0 > 1e-12;
}
