import base64
from pathlib import Path

from app.client_dispatch import handle

ROOT = Path(__file__).resolve().parents[2]


def test_dispatch_imports_svg_and_packs_locally():
    svg = (ROOT / "samples" / "rectangle.svg").read_bytes()
    imported = handle(
        "import",
        {"filename": "rectangle.svg", "data_b64": base64.b64encode(svg).decode(), "unit_scale": 1},
    )
    assert imported["regions"]
    assert any(r["kind"] == "populate" for r in imported["regions"])

    packed = handle(
        "pack",
        {
            "regions": imported["regions"],
            "params": {
                "cell_w_mm": 100,
                "cell_h_mm": 100,
                "cell_gap_mm": 0,
                "panel_gap_mm": 0,
                "max_wide": 2,
                "max_tall": 2,
                "target_area_m2": 0.01,
            },
        },
    )
    layouts = packed["layouts"]
    assert layouts
    assert max(lay["score"]["cell_count"] for lay in layouts) > 0

    top = layouts[0]
    checked = handle(
        "validate",
        {"regions": imported["regions"], "params": top["params"], "panels": top["panels"]},
    )
    assert checked["score"]["cell_count"] == top["score"]["cell_count"]

    svg_out = handle(
        "export",
        {
            "fmt": "svg",
            "regions": imported["regions"],
            "params": top["params"],
            "panels": top["panels"],
            "id": top["id"],
            "family": top["family"],
        },
    )
    assert "<svg" in svg_out["text"]
    dxf_out = handle(
        "export",
        {
            "fmt": "dxf",
            "regions": imported["regions"],
            "params": top["params"],
            "panels": top["panels"],
            "id": top["id"],
            "family": top["family"],
        },
    )
    assert "CELLS" in dxf_out["text"]
    json_out = handle(
        "export",
        {
            "fmt": "json",
            "regions": imported["regions"],
            "params": top["params"],
            "panels": top["panels"],
            "id": top["id"],
            "family": top["family"],
        },
    )
    assert json_out["layout"]["score"]["cell_count"] == top["score"]["cell_count"]
