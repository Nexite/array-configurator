export type RegionKind = "populate" | "keep_out" | "unused";

export type LayoutParams = {
  cell_w_mm: number;
  cell_h_mm: number;
  active_w_mm: number;
  active_h_mm: number;
  cell_gap_mm: number;
  panel_gap_mm: number;
  edge_inset_mm: number;
  custom_active_area: boolean;
  active_input: "dimensions" | "area";
  active_mm2: number;
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
  panel_gap_mm: 2,
  edge_inset_mm: 5,
  custom_active_area: false,
  active_input: "dimensions",
  active_mm2: 15625,
  max_wide: 24,
  max_tall: 6,
  target_area_m2: 6.0,
  unit_scale: 1,
};

function usableCellAreaM2(params: LayoutParams): number {
  if (!params.custom_active_area) return (params.cell_w_mm * params.cell_h_mm) / 1e6;
  if (params.active_input === "area") return params.active_mm2 / 1e6;
  return (params.active_w_mm * params.active_h_mm) / 1e6;
}

export function scoreLayout(panels: Panel[], params: LayoutParams): LayoutScore {
  const cell_count = panels.reduce((n, p) => n + p.occupied.length, 0);
  const one = usableCellAreaM2(params);
  const active_area_m2 = cell_count * one;
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
    axis_aligned_area_m2: axis * one,
    rectangular_panel_count,
  };
}

export function cycleKind(kind: RegionKind): RegionKind {
  return kind === "populate" ? "keep_out" : kind === "keep_out" ? "unused" : "populate";
}
