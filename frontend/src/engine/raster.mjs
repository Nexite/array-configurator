// Cell-grid test used by the packer. The same check in the Python engine
// dominates Generate, so the browser runs it here instead.

const EPS = 1e-6;

const prepared = new Map();
let nextId = 1;

function rotatePoint(x, y, c, s) {
  return [x * c + y * s, -x * s + y * c];
}

function rotateRing(ring, c, s) {
  const out = new Array(ring.length);
  for (let i = 0; i < ring.length; i++) out[i] = rotatePoint(ring[i][0], ring[i][1], c, s);
  return out;
}

function ringBBox(ring) {
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  const n = ring.length - 1;
  for (let i = 0; i < n; i++) {
    const x = ring[i][0];
    const y = ring[i][1];
    if (x < minx) minx = x;
    if (y < miny) miny = y;
    if (x > maxx) maxx = x;
    if (y > maxy) maxy = y;
  }
  return [minx, miny, maxx, maxy];
}

function prepareLocal(polygons, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const out = new Array(polygons.length);
  for (let i = 0; i < polygons.length; i++) {
    const poly = polygons[i];
    const exterior = rotateRing(poly.exterior, c, s);
    const srcHoles = poly.holes || [];
    const holes = new Array(srcHoles.length);
    for (let h = 0; h < srcHoles.length; h++) holes[h] = rotateRing(srcHoles[h], c, s);
    out[i] = indexPolygon(exterior, holes);
  }
  return out;
}

const BIN = 160;

function ringEdges(ring, ringId) {
  const n = ring.length - 1;
  const edges = new Array(Math.max(0, n));
  for (let i = 0; i < n; i++) {
    const x1 = ring[i][0];
    const y1 = ring[i][1];
    const x2 = ring[i + 1][0];
    const y2 = ring[i + 1][1];
    edges[i] = {
      x1,
      y1,
      x2,
      y2,
      ring: ringId,
      minx: Math.min(x1, x2),
      maxx: Math.max(x1, x2),
      miny: Math.min(y1, y2),
      maxy: Math.max(y1, y2),
    };
  }
  return edges;
}

function indexPolygon(exterior, holes) {
  const exteriorEdges = ringEdges(exterior, 0);
  const holeEdges = holes.map((hole, index) => ringEdges(hole, index + 1));
  const all = exteriorEdges.length ? exteriorEdges.concat(...holeEdges) : [];
  const [minx, miny, maxx, maxy] = ringBBox(exterior);
  const ox = minx - BIN;
  const oy = miny - BIN;
  const nx = Math.max(1, Math.ceil((maxx - ox) / BIN) + 1);
  const ny = Math.max(1, Math.ceil((maxy - oy) / BIN) + 1);
  const bins = new Array(nx * ny);
  for (let e = 0; e < all.length; e++) {
    const edge = all[e];
    let i0 = Math.floor((edge.minx - ox) / BIN);
    let i1 = Math.floor((edge.maxx - ox) / BIN);
    let j0 = Math.floor((edge.miny - oy) / BIN);
    let j1 = Math.floor((edge.maxy - oy) / BIN);
    if (i0 < 0) i0 = 0;
    if (j0 < 0) j0 = 0;
    if (i1 >= nx) i1 = nx - 1;
    if (j1 >= ny) j1 = ny - 1;
    for (let i = i0; i <= i1; i++) {
      for (let j = j0; j <= j1; j++) {
        const key = i * ny + j;
        const list = bins[key];
        if (list) list.push(e);
        else bins[key] = [e];
      }
    }
  }
  return {
    exterior,
    holes,
    bbox: [minx, miny, maxx, maxy],
    exteriorEdges,
    holeEdges,
    all,
    bins,
    nx,
    ny,
    ox,
    oy,
    exCache: new Map(),
    holeCaches: holeEdges.map(() => new Map()),
    seen: new Uint32Array(all.length),
    stamp: 1,
  };
}

function crossingXs(edges, y) {
  const xs = [];
  for (let i = 0; i < edges.length; i++) {
    const edge = edges[i];
    if (edge.y1 > y !== edge.y2 > y) {
      xs.push(edge.x1 + ((y - edge.y1) / (edge.y2 - edge.y1)) * (edge.x2 - edge.x1));
    }
  }
  xs.sort((a, b) => a - b);
  return xs;
}

function crossed(edges, cache, y, x) {
  let xs = cache.get(y);
  if (!xs) {
    xs = crossingXs(edges, y);
    cache.set(y, xs);
  }
  let lo = 0;
  let hi = xs.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= x) lo = mid + 1;
    else hi = mid;
  }
  return ((xs.length - lo) & 1) === 1;
}

function nearIndexed(poly, x, y, ringId) {
  const i = Math.floor((x - poly.ox) / BIN);
  const j = Math.floor((y - poly.oy) / BIN);
  for (let di = -1; di <= 1; di++) {
    const ii = i + di;
    if (ii < 0 || ii >= poly.nx) continue;
    for (let dj = -1; dj <= 1; dj++) {
      const jj = j + dj;
      if (jj < 0 || jj >= poly.ny) continue;
      const list = poly.bins[ii * poly.ny + jj];
      if (!list) continue;
      for (let k = 0; k < list.length; k++) {
        const edge = poly.all[list[k]];
        if (edge.ring !== ringId) continue;
        if (x < edge.minx - EPS || x > edge.maxx + EPS || y < edge.miny - EPS || y > edge.maxy + EPS) continue;
        if (distToSeg(x, y, edge.x1, edge.y1, edge.x2, edge.y2) <= EPS) return true;
      }
    }
  }
  return false;
}

function cornerInside(poly, x, y) {
  const [minx, miny, maxx, maxy] = poly.bbox;
  if (x < minx - EPS || x > maxx + EPS || y < miny - EPS || y > maxy + EPS) return false;
  if (!crossed(poly.exteriorEdges, poly.exCache, y, x)) return nearIndexed(poly, x, y, 0);
  for (let h = 0; h < poly.holeEdges.length; h++) {
    if (crossed(poly.holeEdges[h], poly.holeCaches[h], y, x) && !nearIndexed(poly, x, y, h + 1)) return false;
  }
  return true;
}

function distToSeg(x, y, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  let t = len2 > 0 ? ((x - x1) * dx + (y - y1) * dy) / len2 : 0;
  if (t < 0) t = 0;
  else if (t > 1) t = 1;
  const px = x1 + t * dx - x;
  const py = y1 + t * dy - y;
  return Math.hypot(px, py);
}

function cutsRect(x1, y1, x2, y2, xmin, ymin, xmax, ymax) {
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

function anyCut(poly, x0, y0, x1, y1) {
  let i0 = Math.floor((x0 - poly.ox) / BIN) - 1;
  let i1 = Math.floor((x1 - poly.ox) / BIN) + 1;
  let j0 = Math.floor((y0 - poly.oy) / BIN) - 1;
  let j1 = Math.floor((y1 - poly.oy) / BIN) + 1;
  if (i0 < 0) i0 = 0;
  if (j0 < 0) j0 = 0;
  if (i1 >= poly.nx) i1 = poly.nx - 1;
  if (j1 >= poly.ny) j1 = poly.ny - 1;
  let stamp = ++poly.stamp;
  if (stamp >= 0xf0000000) {
    poly.seen.fill(0);
    poly.stamp = 1;
    stamp = 1;
  }
  for (let i = i0; i <= i1; i++) {
    for (let j = j0; j <= j1; j++) {
      const list = poly.bins[i * poly.ny + j];
      if (!list) continue;
      for (let k = 0; k < list.length; k++) {
        const ei = list[k];
        if (poly.seen[ei] === stamp) continue;
        poly.seen[ei] = stamp;
        const edge = poly.all[ei];
        if (edge.maxx < x0 || edge.minx > x1 || edge.maxy < y0 || edge.miny > y1) continue;
        if (cutsRect(edge.x1, edge.y1, edge.x2, edge.y2, x0, y0, x1, y1)) return true;
      }
    }
  }
  return false;
}

function polygonCoversRect(x0, y0, x1, y1, poly) {
  const [minx, miny, maxx, maxy] = poly.bbox;
  if (x1 < minx - EPS || x0 > maxx + EPS || y1 < miny - EPS || y0 > maxy + EPS) return false;
  if (!cornerInside(poly, x0, y0) || !cornerInside(poly, x1, y0) || !cornerInside(poly, x1, y1) || !cornerInside(poly, x0, y1)) {
    return false;
  }
  const ix0 = x0 + EPS;
  const iy0 = y0 + EPS;
  const ix1 = x1 - EPS;
  const iy1 = y1 - EPS;
  if (ix1 <= ix0 || iy1 <= iy0) return true;
  return !anyCut(poly, ix0, iy0, ix1, iy1);
}

function rectCovered(x0, y0, x1, y1, polys) {
  for (const poly of polys) {
    if (polygonCoversRect(x0, y0, x1, y1, poly)) return true;
  }
  return false;
}

function copyRing(ring) {
  const n = ring.length;
  const out = new Array(n);
  for (let i = 0; i < n; i++) {
    const point = ring[i];
    out[i] = [+point[0], +point[1]];
  }
  return out;
}

export function prepareRaster(polygons) {
  const id = nextId++;
  const copy = [];
  const count = polygons.length;
  for (let i = 0; i < count; i++) {
    const poly = polygons[i];
    const holes = [];
    const holeCount = poly.holes ? poly.holes.length : 0;
    for (let h = 0; h < holeCount; h++) holes.push(copyRing(poly.holes[h]));
    copy.push({ exterior: copyRing(poly.exterior), holes });
  }
  prepared.set(id, copy);
  return id;
}

export function releaseRaster(id) {
  prepared.delete(id);
}

function largestRect(mask, ni, nj, cw, ch, gap, capW, capH) {
  let iMin = ni;
  let iMax = -1;
  let jMin = nj;
  let jMax = -1;
  for (let i = 0; i < ni; i++) {
    for (let j = 0; j < nj; j++) {
      if (!mask[i * nj + j]) continue;
      if (i < iMin) iMin = i;
      if (i > iMax) iMax = i;
      if (j < jMin) jMin = j;
      if (j > jMax) jMax = j;
    }
  }
  if (iMax < 0) return null;
  const heights = new Array(iMax - iMin + 1).fill(0);
  let best = null;
  function consider(w, h, i0, j0) {
    if (w <= 0 || h <= 0 || w > capW || h > capH) return;
    const pw = w * cw + (w - 1) * gap;
    const ph = h * ch + (h - 1) * gap;
    const aspect = Math.min(pw, ph) / Math.max(pw, ph);
    const area = w * h;
    if (!best || area > best.area || (area === best.area && aspect > best.aspect)) {
      best = { area, aspect, i0, j0, w, h };
    }
  }
  for (let j = jMin; j <= jMax; j++) {
    for (let t = 0, i = iMin; i <= iMax; t++, i++) {
      heights[t] = mask[i * nj + j] ? heights[t] + 1 : 0;
    }
    const stack = [-1];
    const extended = heights.concat([0]);
    for (let idx = 0; idx < extended.length; idx++) {
      const hgt = extended[idx];
      while (stack[stack.length - 1] !== -1 && heights[stack[stack.length - 1]] > hgt) {
        const sh = heights[stack.pop()];
        const width = idx - stack[stack.length - 1] - 1;
        const left = iMin + stack[stack.length - 1] + 1;
        consider(width, sh, left, j - sh + 1);
      }
      stack.push(idx);
    }
  }
  if (!best) return null;
  return [best.i0, best.j0, best.w, best.h];
}

function grow(mask, ni, nj, rect, capW, capH) {
  const [i0, j0, w, h] = rect;
  const occupied = new Set();
  for (let i = i0; i < i0 + w; i++) {
    for (let j = j0; j < j0 + h; j++) {
      if (i >= 0 && j >= 0 && i < ni && j < nj && mask[i * nj + j]) occupied.add(i * 100000 + j);
    }
  }
  if (!occupied.size) return null;
  let iMin = Infinity;
  let iMax = -Infinity;
  let jMin = Infinity;
  let jMax = -Infinity;
  for (const key of occupied) {
    const i = (key / 100000) | 0;
    const j = key % 100000;
    if (i < iMin) iMin = i;
    if (i > iMax) iMax = i;
    if (j < jMin) jMin = j;
    if (j > jMax) jMax = j;
  }
  const frontier = [...occupied];
  const dirs = [1, 0, -1, 0, 0, 1, 0, -1];
  while (frontier.length) {
    const key = frontier.pop();
    const i = (key / 100000) | 0;
    const j = key % 100000;
    for (let d = 0; d < 8; d += 2) {
      const niCell = i + dirs[d];
      const njCell = j + dirs[d + 1];
      if (niCell < 0 || njCell < 0 || niCell >= ni || njCell >= nj || !mask[niCell * nj + njCell]) continue;
      const nxt = niCell * 100000 + njCell;
      if (occupied.has(nxt)) continue;
      const nIMin = Math.min(iMin, niCell);
      const nIMax = Math.max(iMax, niCell);
      const nJMin = Math.min(jMin, njCell);
      const nJMax = Math.max(jMax, njCell);
      if (nIMax - nIMin + 1 > capW || nJMax - nJMin + 1 > capH) continue;
      occupied.add(nxt);
      frontier.push(nxt);
      iMin = nIMin;
      iMax = nIMax;
      jMin = nJMin;
      jMax = nJMax;
    }
  }
  const cells = [];
  for (const key of occupied) cells.push((key / 100000) | 0, key % 100000);
  return { cells, iMin, iMax, jMin, jMax, count: occupied.size };
}

export function bestOnAngle(id, angleDeg, phases, px, py, cw, ch, gap, capW, capH) {
  const polygons = prepared.get(id) || [];
  const local = prepareLocal(polygons, angleDeg);
  let best = null;
  const phaseCount = phases.length;
  for (let p = 0; p < phaseCount; p++) {
    const phase = phases[p];
    const u0 = +phase.u0;
    const v0 = +phase.v0;
    const ni = phase.ni | 0;
    const nj = phase.nj | 0;
    if (ni <= 0 || nj <= 0) continue;
    const mask = new Uint8Array(ni * nj);
    let maskCount = 0;
    for (let i = 0; i < ni; i++) {
      const x = u0 + i * px;
      for (let j = 0; j < nj; j++) {
        if (rectCovered(x, v0 + j * py, x + cw, v0 + j * py + ch, local)) {
          mask[i * nj + j] = 1;
          maskCount++;
        }
      }
    }
    if (!maskCount) continue;
    const rect = largestRect(mask, ni, nj, cw, ch, gap, capW | 0, capH | 0);
    if (!rect) continue;
    const grown = grow(mask, ni, nj, rect, capW | 0, capH | 0);
    if (!grown) continue;
    const fill = grown.count / ((grown.iMax - grown.iMin + 1) * (grown.jMax - grown.jMin + 1));
    if (
      !best ||
      grown.count > best.count ||
      (grown.count === best.count && (maskCount > best.maskCount || (maskCount === best.maskCount && fill > best.fill)))
    ) {
      best = { count: grown.count, maskCount, fill, u0, v0, cells: grown.cells };
    }
  }
  return best;
}

export function rasterPhases(id, angleDeg, phases, px, py, cw, ch) {
  const polygons = prepared.get(id) || [];
  const local = prepareLocal(polygons, angleDeg);
  const counts = [];
  const data = [];
  const phaseCount = phases.length;
  for (let p = 0; p < phaseCount; p++) {
    const phase = phases[p];
    const u0 = +phase.u0;
    const v0 = +phase.v0;
    const ni = phase.ni | 0;
    const nj = phase.nj | 0;
    let count = 0;
    for (let i = 0; i < ni; i++) {
      const x = u0 + i * px;
      for (let j = 0; j < nj; j++) {
        const y = v0 + j * py;
        if (rectCovered(x, y, x + cw, y + ch, local)) {
          data.push(i, j);
          count++;
        }
      }
    }
    counts.push(count);
  }
  return { counts, data };
}
