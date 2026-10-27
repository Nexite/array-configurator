import { describe, expect, it } from "vitest";
import { confirmReplace, initialState, resizeBound, selectGallery, setLayouts, toggleCell } from "./store";
import { DEFAULT_PARAMS, scoreLayout, type Layout, type Panel } from "../types";

function panel(over: Partial<Panel> = {}): Panel {
  return {
    id: "p",
    origin: [0, 0],
    angle_deg: 0,
    cells_wide: 2,
    cells_tall: 2,
    occupied: [
      [0, 0],
      [1, 0],
      [0, 1],
    ],
    ...over,
  };
}

function layout(id: string, panels: Panel[]): Layout {
  return { id, params: DEFAULT_PARAMS, panels, score: scoreLayout(panels, DEFAULT_PARAMS), family: "rect90" };
}

describe("store", () => {
  it("does not swap gallery while dirty until confirm", () => {
    let s = setLayouts(initialState(), [layout("L0", [panel()]), layout("L1", [panel({ id: "q" })])]);
    s = toggleCell(s, "p", 1, 0);
    expect(s.dirty).toBe(true);
    s = selectGallery(s, "L1");
    expect(s.active?.id).toBe("L0");
    expect(s.pendingGalleryId).toBe("L1");
    s = confirmReplace(s);
    expect(s.active?.id).toBe("L1");
  });

  it("resize bound does not fill a carved hole", () => {
    let s = setLayouts(initialState(), [layout("L0", [panel()])]);
    s = resizeBound(s, "p", 2, 2);
    const occ = s.active!.panels[0].occupied.map(([i, j]) => `${i},${j}`).sort();
    expect(occ).toEqual(["0,0", "0,1", "1,0"]);
  });

  it("status area uses n_cells * active_w * active_h / 1e6", () => {
    const panels = [panel({ occupied: [[0, 0]] })];
    const params = { ...DEFAULT_PARAMS, active_w_mm: 100, active_h_mm: 80 };
    expect(scoreLayout(panels, params).active_area_m2).toBeCloseTo(0.008);
  });
});
