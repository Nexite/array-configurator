import type { Region } from "./types";

function openRing(points: [number, number][]): [number, number][] {
  if (points.length >= 2) {
    const a = points[0];
    const b = points[points.length - 1];
    if (a[0] === b[0] && a[1] === b[1]) return points.slice(0, -1);
  }
  return points;
}

function polygonAreaMm2(points: [number, number][]): number {
  const ring = openRing(points);
  if (ring.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

function pointInRing(x: number, y: number, points: [number, number][]): boolean {
  const ring = openRing(points);
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const crosses = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

/** Area of the imported outline in m². Coordinates are millimetres. Cutouts are subtracted; drawn regions are not. */
export function shellAreaM2(regions: Region[]): number | null {
  const items = regions
    .filter((r) => r.source === "detected")
    .map((r) => ({ points: r.points, area: polygonAreaMm2(r.points) }))
    .filter((item) => item.area > 0)
    .sort((a, b) => b.area - a.area);
  if (!items.length) return null;
  let mm2 = 0;
  for (const item of items) {
    const ring = openRing(item.points);
    let containers = 0;
    for (const outer of items) {
      if (outer.area <= item.area) continue;
      if (ring.every(([x, y]) => pointInRing(x, y, outer.points))) containers += 1;
    }
    mm2 += containers % 2 === 0 ? item.area : -item.area;
  }
  return mm2 / 1e6;
}
