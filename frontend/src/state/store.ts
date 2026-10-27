import { cycleKind, DEFAULT_PARAMS, scoreLayout, type Layout, type LayoutParams, type Panel, type Region, type RegionKind } from "../types";

export type AppState = {
  params: LayoutParams;
  regions: Region[];
  layouts: Layout[];
  active: Layout | null;
  dirty: boolean;
  pendingGalleryId: string | null;
  selectedPanelId: string | null;
  history: Layout[];
  future: Layout[];
};

export function initialState(): AppState {
  return {
    params: { ...DEFAULT_PARAMS },
    regions: [],
    layouts: [],
    active: null,
    dirty: false,
    pendingGalleryId: null,
    selectedPanelId: null,
    history: [],
    future: [],
  };
}

function snapshot(s: AppState): AppState {
  return {
    ...s,
    history: s.active ? [...s.history, structuredClone(s.active)].slice(-40) : s.history,
    future: [],
    dirty: true,
  };
}

export function loadRegions(s: AppState, regions: Region[]): AppState {
  return { ...s, regions, layouts: [], active: null, dirty: false, pendingGalleryId: null };
}

export function cycleRegion(s: AppState, id: string): AppState {
  return {
    ...s,
    regions: s.regions.map((r) => (r.id === id ? { ...r, kind: cycleKind(r.kind) } : r)),
  };
}

export function addDrawnRegion(s: AppState, points: [number, number][], kind: RegionKind): AppState {
  return {
    ...s,
    regions: [...s.regions, { id: `d${s.regions.length}`, points, kind, source: "drawn" }],
  };
}

export function setLayouts(s: AppState, layouts: Layout[]): AppState {
  return { ...s, layouts, active: layouts[0] ?? null, dirty: false, pendingGalleryId: null, history: [], future: [] };
}

export function selectGallery(s: AppState, id: string): AppState {
  if (s.dirty) return { ...s, pendingGalleryId: id };
  const next = s.layouts.find((l) => l.id === id) ?? s.active;
  return { ...s, active: next, pendingGalleryId: null };
}

export function confirmReplace(s: AppState): AppState {
  if (!s.pendingGalleryId) return s;
  const next = s.layouts.find((l) => l.id === s.pendingGalleryId) ?? s.active;
  return { ...s, active: next, dirty: false, pendingGalleryId: null, history: [], future: [] };
}

export function movePanel(s: AppState, id: string, origin: [number, number]): AppState {
  if (!s.active) return s;
  const next = snapshot(s);
  next.active = {
    ...s.active,
    panels: s.active.panels.map((p) => (p.id === id ? { ...p, origin } : p)),
  };
  next.active.score = scoreLayout(next.active.panels, s.params);
  return next;
}

export function resizeBound(s: AppState, id: string, w: number, h: number): AppState {
  if (!s.active) return s;
  const maxW = s.params.max_wide;
  const maxH = s.params.max_tall;
  w = Math.max(1, Math.min(w, maxW));
  h = Math.max(1, Math.min(h, maxH));
  const next = snapshot(s);
  next.active = {
    ...s.active,
    panels: s.active.panels.map((p) => {
      if (p.id !== id) return p;
      const occupied = p.occupied.filter(([i, j]) => i < w && j < h);
      const grown = [...occupied];
      for (let i = 0; i < w; i++) {
        for (let j = 0; j < h; j++) {
          const fringe = i >= p.cells_wide || j >= p.cells_tall;
          if (fringe && !grown.some(([a, b]) => a === i && b === j)) grown.push([i, j]);
        }
      }
      return { ...p, cells_wide: w, cells_tall: h, occupied: grown.length ? grown : [[0, 0]] };
    }),
  };
  next.active.score = scoreLayout(next.active.panels, s.params);
  return next;
}

export function toggleCell(s: AppState, panelId: string, i: number, j: number): AppState {
  if (!s.active) return s;
  const next = snapshot(s);
  const panels: Panel[] = [];
  for (const p of s.active.panels) {
    if (p.id !== panelId) {
      panels.push(p);
      continue;
    }
    const has = p.occupied.some(([a, b]) => a === i && b === j);
    const occupied = has ? p.occupied.filter(([a, b]) => !(a === i && b === j)) : [...p.occupied, [i, j] as [number, number]];
    if (occupied.length === 0) continue;
    panels.push({ ...p, occupied });
  }
  next.active = { ...s.active, panels };
  next.active.score = scoreLayout(panels, s.params);
  return next;
}

export function deletePanel(s: AppState, id: string): AppState {
  if (!s.active) return s;
  const next = snapshot(s);
  const panels = s.active.panels.filter((p) => p.id !== id);
  next.active = { ...s.active, panels };
  next.active.score = scoreLayout(panels, s.params);
  return next;
}

export function undo(s: AppState): AppState {
  if (!s.history.length || !s.active) return s;
  const prev = s.history[s.history.length - 1];
  return { ...s, active: prev, history: s.history.slice(0, -1), future: [s.active, ...s.future], dirty: true };
}

export function redo(s: AppState): AppState {
  if (!s.future.length) return s;
  const [n, ...rest] = s.future;
  return { ...s, active: n, future: rest, history: s.active ? [...s.history, s.active] : s.history, dirty: true };
}
