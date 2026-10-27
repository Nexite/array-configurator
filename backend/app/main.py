from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.geometry.export import export_dxf, export_json, export_svg, layout_from_json
from app.geometry.import_vector import UnsupportedFormatError, import_vector
from app.geometry.pack import pack_layouts
from app.geometry.regions import classify_detected, packable_polygon
from app.geometry.score import score_layout
from app.geometry.validate import validate_layout
from app.models import Issue
from app.serde import (
    bounds_of,
    layout_to_dict,
    panel_from_dict,
    params_from_dict,
    region_from_dict,
    region_to_dict,
    score_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "samples" / "TOPSHELL.DXF"
MAX_UPLOAD = 25 * 1024 * 1024
STATIC = Path(__file__).resolve().parent / "static"


class PackBody(BaseModel):
    regions: list[dict]
    params: dict = {}


class ValidateBody(BaseModel):
    regions: list[dict]
    params: dict = {}
    panels: list[dict]


class ExportBody(BaseModel):
    regions: list[dict]
    params: dict = {}
    panels: list[dict]
    family: str = "rect90"
    id: str = "edit"


def create_app() -> FastAPI:
    app = FastAPI(title="Array Configurator")

    def _import_bytes(data: bytes, name: str, unit_scale: float):
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "File too large")
        try:
            rings = import_vector(data, name, unit_scale)
        except UnsupportedFormatError as e:
            raise HTTPException(400, str(e)) from e
        regions = classify_detected(rings)
        return {"regions": [region_to_dict(r) for r in regions], "bounds": bounds_of(regions)}

    @app.post("/api/import")
    async def api_import(file: UploadFile = File(...), unit_scale: float = Form(1.0)):
        data = await file.read()
        return _import_bytes(data, file.filename or "upload.dxf", unit_scale)

    @app.get("/api/sample/topshell")
    def api_sample():
        return _import_bytes(SAMPLE.read_bytes(), "TOPSHELL.DXF", 1.0)

    @app.post("/api/pack")
    def api_pack(body: PackBody):
        regions = [region_from_dict(r) for r in body.regions]
        params = params_from_dict(body.params)
        packable = packable_polygon(regions)
        layouts = pack_layouts(packable, params)
        return {"layouts": [layout_to_dict(l) for l in layouts]}

    @app.post("/api/validate")
    def api_validate(body: ValidateBody):
        regions = [region_from_dict(r) for r in body.regions]
        params = params_from_dict(body.params)
        panels = [panel_from_dict(p) for p in body.panels]
        packable = packable_polygon(regions)
        issues = validate_layout(panels, params, packable)
        score = score_layout(panels, params)
        return {
            "issues": [issue.__dict__ for issue in issues],
            "score": score_to_dict(score),
        }

    @app.post("/api/export/{fmt}")
    def api_export(fmt: str, body: ExportBody):
        regions = [region_from_dict(r) for r in body.regions]
        params = params_from_dict(body.params)
        panels = [panel_from_dict(p) for p in body.panels]
        from app.models import Layout

        layout = Layout(id=body.id, params=params, panels=panels, score=score_layout(panels, params), family=body.family)
        if fmt == "json":
            return export_json(layout, regions)
        if fmt == "svg":
            return Response(export_svg(layout, regions), media_type="image/svg+xml")
        if fmt == "dxf":
            return Response(export_dxf(layout, regions), media_type="application/dxf")
        raise HTTPException(400, "fmt must be svg, dxf, or json")

    if STATIC.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")

    return app


app = create_app()
