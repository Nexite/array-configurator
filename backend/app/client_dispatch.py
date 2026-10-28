"""JSON entry point the browser engine loads inside Pyodide."""

from __future__ import annotations

import base64

from app.geometry.export import export_dxf, export_json, export_svg
from app.geometry.import_vector import import_vector
from app.geometry.pack import pack_layouts
from app.geometry.regions import classify_detected, packable_polygon
from app.geometry.score import score_layout
from app.geometry.validate import validate_layout
from app.models import Layout
from app.serde import (
    bounds_of,
    layout_to_dict,
    panel_from_dict,
    params_from_dict,
    region_from_dict,
    region_to_dict,
    score_to_dict,
)


def handle(op: str, payload: dict) -> dict:
    if op == "import":
        data = base64.b64decode(payload["data_b64"])
        rings = import_vector(data, payload["filename"], float(payload.get("unit_scale", 1)))
        regions = classify_detected(rings)
        return {"regions": [region_to_dict(r) for r in regions], "bounds": bounds_of(regions)}
    if op == "pack":
        regions = [region_from_dict(r) for r in payload["regions"]]
        params = params_from_dict(payload.get("params"))
        layouts = pack_layouts(packable_polygon(regions), params)
        return {"layouts": [layout_to_dict(lay) for lay in layouts]}
    if op == "validate":
        regions = [region_from_dict(r) for r in payload["regions"]]
        params = params_from_dict(payload.get("params"))
        panels = [panel_from_dict(p) for p in payload["panels"]]
        packable = packable_polygon(regions)
        issues = validate_layout(panels, params, packable)
        score = score_layout(panels, params)
        return {"issues": [issue.__dict__ for issue in issues], "score": score_to_dict(score)}
    if op == "export":
        regions = [region_from_dict(r) for r in payload["regions"]]
        params = params_from_dict(payload.get("params"))
        panels = [panel_from_dict(p) for p in payload["panels"]]
        layout = Layout(
            id=payload.get("id", "edit"),
            params=params,
            panels=panels,
            score=score_layout(panels, params),
            family=payload.get("family", "rect90"),
        )
        fmt = payload["fmt"]
        if fmt == "json":
            return export_json(layout, regions)
        if fmt == "svg":
            return {"text": export_svg(layout, regions), "mime": "image/svg+xml"}
        if fmt == "dxf":
            return {"text": export_dxf(layout, regions).decode("utf-8"), "mime": "application/dxf"}
        raise ValueError("fmt must be svg, dxf, or json")
    raise ValueError(f"unknown op {op}")
