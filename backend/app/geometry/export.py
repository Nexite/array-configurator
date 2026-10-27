from __future__ import annotations

import json
from io import StringIO

import ezdxf

from app.geometry.panel import cell_polygon, panel_footprint
from app.models import Layout, Region
from app.serde import layout_to_dict, region_to_dict


def export_json(layout: Layout, regions: list[Region]) -> dict:
    return {"layout": layout_to_dict(layout), "regions": [region_to_dict(r) for r in regions]}


def layout_from_json(data: dict) -> tuple[Layout, list[Region]]:
    from app.serde import panel_from_dict, params_from_dict, region_from_dict
    from app.models import Layout

    raw = data["layout"]
    layout = Layout(
        id=raw["id"],
        params=params_from_dict(raw["params"]),
        panels=[panel_from_dict(p) for p in raw["panels"]],
        score=None,
        family=raw.get("family", "rect90"),
    )
    regions = [region_from_dict(r) for r in data.get("regions", [])]
    return layout, regions


def export_svg(layout: Layout, regions: list[Region]) -> str:
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">']
    xs, ys = [], []
    for r in regions:
        d = " ".join(f"{x},{y}" for x, y in r.points)
        fill = "#1f6feb" if r.kind.value == "populate" else "#e05a4f"
        parts.append(f'<polygon points="{d}" fill="{fill}" fill-opacity="0.25" stroke="#888"/>')
        xs.extend(p[0] for p in r.points)
        ys.extend(p[1] for p in r.points)
    for panel in layout.panels:
        for i, j in panel.occupied:
            poly = cell_polygon(panel, i, j, layout.params)
            pts = " ".join(f"{x},{y}" for x, y in poly.exterior.coords)
            parts.append(f'<polygon points="{pts}" fill="#f0c14b" fill-opacity="0.7" stroke="#222"/>')
            xs.extend(x for x, _ in poly.exterior.coords)
            ys.extend(y for _, y in poly.exterior.coords)
    if xs:
        minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
        parts[0] = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{minx} {miny} {maxx - minx} {maxy - miny}">'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def export_dxf(layout: Layout, regions: list[Region]) -> bytes:
    doc = ezdxf.new()
    for name in ("OUTLINE", "PANELS", "CELLS"):
        if name not in doc.layers:
            doc.layers.add(name)
    msp = doc.modelspace()
    for r in regions:
        msp.add_lwpolyline(r.points, close=True, dxfattribs={"layer": "OUTLINE"})
    for panel in layout.panels:
        fp = panel_footprint(panel, layout.params)
        if not fp.is_empty:
            if fp.geom_type == "Polygon":
                msp.add_lwpolyline(list(fp.exterior.coords), close=True, dxfattribs={"layer": "PANELS"})
        for i, j in panel.occupied:
            poly = cell_polygon(panel, i, j, layout.params)
            msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": "CELLS"})
    buf = StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
