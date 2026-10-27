from io import StringIO

import ezdxf
from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_import_rectangle_svg():
    svg = b"""<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg' width='1000mm' height='500mm' viewBox='0 0 1000 500'><rect x='0' y='0' width='1000' height='500'/></svg>"""
    r = client.post("/api/import", files={"file": ("rectangle.svg", svg, "image/svg+xml")})
    assert r.status_code == 200
    assert r.json()["regions"]


def test_import_png_400():
    r = client.post("/api/import", files={"file": ("x.png", b"x", "image/png")})
    assert r.status_code == 400
    assert "Raster" in r.json()["detail"]


def test_sample_topshell_has_populate_region():
    r = client.get("/api/sample/topshell")
    assert r.status_code == 200
    kinds = {reg["kind"] for reg in r.json()["regions"]}
    assert "populate" in kinds


def test_pack_then_validate_roundtrip():
    imported = client.get("/api/sample/topshell").json()
    pack = client.post("/api/pack", json={"regions": imported["regions"], "params": {"max_wide": 2, "max_tall": 2, "target_area_m2": 0.05}})
    assert pack.status_code == 200
    layouts = pack.json()["layouts"]
    assert layouts
    body = {
        "regions": imported["regions"],
        "params": layouts[0]["params"],
        "panels": layouts[0]["panels"],
    }
    val = client.post("/api/validate", json=body)
    assert val.status_code == 200
    assert "score" in val.json()


def test_export_json_roundtrip_same_cell_count():
    imported = client.get("/api/sample/topshell").json()
    pack = client.post("/api/pack", json={"regions": imported["regions"], "params": {"max_wide": 2, "max_tall": 1}})
    lay = pack.json()["layouts"][0]
    exp = client.post(
        "/api/export/json",
        json={"regions": imported["regions"], "params": lay["params"], "panels": lay["panels"], "id": lay["id"], "family": lay["family"]},
    )
    assert exp.status_code == 200
    assert exp.json()["layout"]["score"]["cell_count"] == lay["score"]["cell_count"]


def test_export_dxf_has_cells_layer():
    imported = client.get("/api/sample/topshell").json()
    pack = client.post("/api/pack", json={"regions": imported["regions"], "params": {"max_wide": 2, "max_tall": 1}})
    lay = pack.json()["layouts"][0]
    exp = client.post(
        "/api/export/dxf",
        json={"regions": imported["regions"], "params": lay["params"], "panels": lay["panels"]},
    )
    assert exp.status_code == 200
    doc = ezdxf.read(StringIO(exp.content.decode("utf-8")))
    layers = {layer.dxf.name for layer in doc.layers}
    assert "CELLS" in layers
