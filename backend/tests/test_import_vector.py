from pathlib import Path

import ezdxf
import pytest
from shapely.geometry import Polygon

from app.geometry.import_vector import UnsupportedFormatError, import_vector

ROOT = Path(__file__).resolve().parents[2]
RECT_SVG = ROOT / "samples" / "rectangle.svg"


def test_rectangle_svg_area():
    rings = import_vector(RECT_SVG.read_bytes(), "rectangle.svg")
    assert len(rings) == 1
    assert abs(Polygon(rings[0]).area - 500_000) < 1.0


def test_dxf_lwpolyline_closed():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50)], close=True)
    from io import StringIO

    buf = StringIO()
    doc.write(buf)
    rings = import_vector(buf.getvalue().encode("utf-8"), "box.dxf")
    assert len(rings) == 1
    assert abs(Polygon(rings[0]).area - 5000) < 1e-3


def _dxf_open_polyline(gap: float) -> bytes:
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50), (0, gap)], close=False)
    from io import StringIO

    buf = StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_almost_closed_gap_2mm_closes():
    rings = import_vector(_dxf_open_polyline(2.0), "almost.dxf")
    assert len(rings) == 1


def test_gap_3mm_ignored():
    rings = import_vector(_dxf_open_polyline(3.0), "open.dxf")
    assert rings == []


def test_png_rejected():
    with pytest.raises(UnsupportedFormatError, match="Raster files are not supported"):
        import_vector(b"x", "x.png")
