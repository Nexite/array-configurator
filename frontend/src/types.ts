export type RegionKind = "populate" | "keep_out" | "unused";

export type LayoutParams = {
  cell_w_mm: number;
  cell_h_mm: number;
  active_w_mm: number;
  active_h_mm: number;
  cell_gap_mm: number;
  panel_gap_mm: number;
  edge_inset_mm: number;
  max_wide: number;
  max_tall: number;
  target_area_m2: number;
  unit_scale: number;
};

export type Region = {
  id: string;
  points: [number, number][];
  kind: RegionKind;
  source: "detected" | "drawn";
};

export type Panel = {
  id: string;
  origin: [number, number];
  angle_deg: number;
  cells_wide: number;
  cells_tall: number;
  occupied: [number, number][];
};

export type LayoutScore = {
  cell_count: number;
  panel_count: number;
  active_area_m2: number;
  delta_m2: number;
  meets_target: boolean;
  axis_aligned_area_m2: number;
  rectangular_panel_count: number;
};

export type Layout = {
  id: string;
  params: LayoutParams;
  panels: Panel[];
  score: LayoutScore | null;
  family: string;
};

export type Issue = {
  kind: string;
  message: string;
  panel_ids: string[];
  measured: number | null;
  required: number | null;
};

export const DEFAULT_PARAMS: LayoutParams = {
  cell_w_mm: 125,
  cell_h_mm: 125,
  active_w_mm: 125,
  active_h_mm: 125,
  cell_gap_mm: 2,
  panel_gap_mm: 10,
  edge_inset_mm: 0,
  max_wide: 6,
  max_tall: 10,
  target_area_m2: 6.0,
  unit_scale: 1,
};

export function scoreLayout(panels: Panel[], params: LayoutParams): LayoutScore {
  const cell_count = panels.reduce((n, p) => n + p.occupied.length, 0);
  const active_area_m2 = (cell_count * params.active_w_mm * params.active_h_mm) / 1e6;
  const axis = panels
    .filter((p) => p.angle_deg % 90 === 0)
    .reduce((n, p) => n + p.occupied.length, 0);
  const rectangular_panel_count = panels.filter((p) => p.occupied.length === p.cells_wide * p.cells_tall).length;
  return {
    cell_count,
    panel_count: panels.length,
    active_area_m2,
    delta_m2: active_area_m2 - params.target_area_m2,
    meets_target: active_area_m2 >= params.target_area_m2,
    axis_aligned_area_m2: (axis * params.active_w_mm * params.active_h_mm) / 1e6,
    rectangular_panel_count,
  };
}

export function cycleKind(kind: RegionKind): RegionKind {
  return kind === "populate" ? "keep_out" : kind === "keep_out" ? "unused" : "populate";
}
