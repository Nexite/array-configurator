export type OutlineEdge = {
  i: number;
  j: number;
  from: number;
  to: number;
};

const EDGE_NEIGHBOR: { di: number; dj: number; from: number; to: number }[] = [
  { di: 1, dj: 0, from: 1, to: 2 },
  { di: 0, dj: 1, from: 2, to: 3 },
  { di: -1, dj: 0, from: 3, to: 0 },
  { di: 0, dj: -1, from: 0, to: 1 },
];

/** Unshared polyomino sides of a panel, as local cell-corner edges. */
export function panelOutlineEdges(occupied: readonly [number, number][]): OutlineEdge[] {
  const set = new Set(occupied.map(([i, j]) => `${i},${j}`));
  const edges: OutlineEdge[] = [];
  for (const [i, j] of occupied) {
    for (const e of EDGE_NEIGHBOR) {
      if (!set.has(`${i + e.di},${j + e.dj}`)) {
        edges.push({ i, j, from: e.from, to: e.to });
      }
    }
  }
  return edges;
}
