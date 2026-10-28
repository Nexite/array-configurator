from __future__ import annotations

from app.models import DEFAULT_PARAMS, Layout, LayoutParams, LayoutScore, Panel, Region, RegionKind


def params_from_dict(d: dict | None) -> LayoutParams:
    src = d or {}
    cell_w = float(src.get("cell_w_mm", DEFAULT_PARAMS.cell_w_mm))
    cell_h = float(src.get("cell_h_mm", DEFAULT_PARAMS.cell_h_mm))
    return LayoutParams(
        cell_w_mm=cell_w,
        cell_h_mm=cell_h,
        active_w_mm=float(src.get("active_w_mm", cell_w)),
        active_h_mm=float(src.get("active_h_mm", cell_h)),
        cell_gap_mm=float(src.get("cell_gap_mm", DEFAULT_PARAMS.cell_gap_mm)),
        panel_gap_mm=float(src.get("panel_gap_mm", DEFAULT_PARAMS.panel_gap_mm)),
        max_wide=int(src.get("max_wide", DEFAULT_PARAMS.max_wide)),
        max_tall=int(src.get("max_tall", DEFAULT_PARAMS.max_tall)),
        target_area_m2=float(src.get("target_area_m2", DEFAULT_PARAMS.target_area_m2)),
        unit_scale=float(src.get("unit_scale", 1.0)),
        edge_inset_mm=float(src.get("edge_inset_mm", DEFAULT_PARAMS.edge_inset_mm)),
        orientation_spread_deg=float(
            src.get("orientation_spread_deg", DEFAULT_PARAMS.orientation_spread_deg)
        ),
        custom_active_area=bool(src.get("custom_active_area", False)),
        active_input="area" if src.get("active_input") == "area" else "dimensions",
        active_mm2=float(src.get("active_mm2", cell_w * cell_h)),
    )


def params_to_dict(p: LayoutParams) -> dict:
    return {
        "cell_w_mm": p.cell_w_mm,
        "cell_h_mm": p.cell_h_mm,
        "active_w_mm": p.active_w_mm,
        "active_h_mm": p.active_h_mm,
        "cell_gap_mm": p.cell_gap_mm,
        "panel_gap_mm": p.panel_gap_mm,
        "edge_inset_mm": p.edge_inset_mm,
        "orientation_spread_deg": p.orientation_spread_deg,
        "custom_active_area": p.custom_active_area,
        "active_input": p.active_input,
        "active_mm2": p.active_mm2,
        "max_wide": p.max_wide,
        "max_tall": p.max_tall,
        "target_area_m2": p.target_area_m2,
        "unit_scale": p.unit_scale,
    }


def region_from_dict(d: dict) -> Region:
    return Region(
        id=d["id"],
        points=[(float(x), float(y)) for x, y in d["points"]],
        kind=RegionKind(d["kind"]),
        source=d.get("source", "detected"),
    )


def region_to_dict(r: Region) -> dict:
    return {"id": r.id, "points": [list(p) for p in r.points], "kind": r.kind.value, "source": r.source}


def panel_from_dict(d: dict) -> Panel:
    return Panel(
        id=d["id"],
        origin=(float(d["origin"][0]), float(d["origin"][1])),
        angle_deg=float(d["angle_deg"]),
        cells_wide=int(d["cells_wide"]),
        cells_tall=int(d["cells_tall"]),
        occupied=frozenset((int(i), int(j)) for i, j in d["occupied"]),
    )


def panel_to_dict(p: Panel) -> dict:
    return {
        "id": p.id,
        "origin": list(p.origin),
        "angle_deg": p.angle_deg,
        "cells_wide": p.cells_wide,
        "cells_tall": p.cells_tall,
        "occupied": [list(c) for c in sorted(p.occupied)],
    }


def score_to_dict(s: LayoutScore) -> dict:
    return {
        "cell_count": s.cell_count,
        "panel_count": s.panel_count,
        "active_area_m2": s.active_area_m2,
        "delta_m2": s.delta_m2,
        "meets_target": s.meets_target,
        "axis_aligned_area_m2": s.axis_aligned_area_m2,
        "rectangular_panel_count": s.rectangular_panel_count,
    }


def layout_to_dict(lay: Layout) -> dict:
    return {
        "id": lay.id,
        "params": params_to_dict(lay.params),
        "panels": [panel_to_dict(p) for p in lay.panels],
        "score": score_to_dict(lay.score) if lay.score else None,
        "family": lay.family,
    }


def bounds_of(regions: list[Region]) -> dict:
    xs = [p[0] for r in regions for p in r.points]
    ys = [p[1] for r in regions for p in r.points]
    if not xs:
        return {"minx": 0, "miny": 0, "maxx": 0, "maxy": 0}
    return {"minx": min(xs), "miny": min(ys), "maxx": max(xs), "maxy": max(ys)}
