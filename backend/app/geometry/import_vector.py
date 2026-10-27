from __future__ import annotations

import io
import math
import re
import shutil
import tempfile
from pathlib import Path

import ezdxf
from shapely.geometry import Polygon

CLOSE_TOL_MM = 2.0
RASTER_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
VECTOR_EXTS = {".dxf", ".dwg", ".svg", ".pdf", ".ai", ".eps", ".plt", ".hpgl"}


class UnsupportedFormatError(ValueError):
    pass


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _close_ring(points: list[tuple[float, float]], unit_scale: float) -> list[tuple[float, float]] | None:
    if len(points) < 3:
        return None
    pts = [(x * unit_scale, y * unit_scale) for x, y in points]
    if _dist(pts[0], pts[-1]) <= 1e-9:
        pts = pts[:-1] + [pts[0]]
        return pts if len(pts) >= 4 else None
    if _dist(pts[0], pts[-1]) <= CLOSE_TOL_MM:
        pts = pts + [pts[0]]
        return pts
    return None


def _valid_area(ring: list[tuple[float, float]]) -> bool:
    if ring is None or len(ring) < 4:
        return False
    try:
        return abs(Polygon(ring).area) > 1e-6
    except Exception:
        return False


def import_vector(data: bytes, filename: str, unit_scale: float = 1.0) -> list[list[tuple[float, float]]]:
    ext = Path(filename).suffix.lower()
    if ext in RASTER_EXTS:
        raise UnsupportedFormatError("Raster files are not supported. Use a vector file.")
    if ext == ".dwg":
        return _import_dwg(data, unit_scale)
    if ext == ".dxf":
        return _import_dxf(data, unit_scale)
    if ext == ".svg":
        return _import_svg(data, unit_scale)
    if ext in {".pdf", ".ai", ".eps"}:
        return _import_pdf(data, unit_scale)
    if ext in {".plt", ".hpgl"}:
        return _import_hpgl(data, unit_scale)
    raise UnsupportedFormatError(f"Unsupported file type: {ext or filename}")


def _import_dwg(data: bytes, unit_scale: float) -> list[list[tuple[float, float]]]:
    conv = shutil.which("dwg2dxf")
    if not conv:
        raise UnsupportedFormatError("Convert DWG to DXF and upload that.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.dwg"
        dst = Path(tmp) / "out.dxf"
        src.write_bytes(data)
        import subprocess

        subprocess.run([conv, str(src), str(dst)], check=True, capture_output=True)
        return _import_dxf(dst.read_bytes(), unit_scale)


def _import_dxf(data: bytes, unit_scale: float) -> list[list[tuple[float, float]]]:
    text = data.decode("utf-8", errors="replace")
    doc = ezdxf.read(io.StringIO(text))
    msp = doc.modelspace()
    rings: list[list[tuple[float, float]]] = []
    for e in msp:
        kind = e.dxftype()
        pts: list[tuple[float, float]] = []
        if kind == "LWPOLYLINE":
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            if e.closed and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
        elif kind == "POLYLINE":
            pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices]
            if e.is_closed and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
        elif kind == "CIRCLE":
            c = e.dxf.center
            r = float(e.dxf.radius)
            pts = [
                (c.x + r * math.cos(t), c.y + r * math.sin(t))
                for t in [i * 2 * math.pi / 64 for i in range(65)]
            ]
        elif kind == "LINE":
            continue
        ring = _close_ring(pts, unit_scale) if pts else None
        if ring and _valid_area(ring):
            rings.append(ring)
    return rings


def _import_svg(data: bytes, unit_scale: float) -> list[list[tuple[float, float]]]:
    from svgelements import SVG, Path, Rect, Circle, Ellipse, Polygon as SvgPolygon, Polyline

    # ppi=25.4 keeps 1 SVG-mm == 1 user unit (files are treated as mm).
    svg = SVG.parse(io.BytesIO(data), ppi=25.4)
    rings: list[list[tuple[float, float]]] = []
    for el in svg.elements():
        pts: list[tuple[float, float]] = []
        if isinstance(el, Rect):
            x, y, w, h = float(el.x), float(el.y), float(el.width), float(el.height)
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        elif isinstance(el, (SvgPolygon, Polyline)):
            pts = [(float(p.x), float(p.y)) for p in el.points]
        elif isinstance(el, (Path, Circle, Ellipse)):
            path = Path(el) if not isinstance(el, Path) else el
            try:
                path = path.reify()
            except Exception:
                pass
            segs = list(path.segments())
            for seg in segs:
                if hasattr(seg, "end") and seg.end is not None:
                    pts.append((float(seg.end.x), float(seg.end.y)))
        ring = _close_ring(pts, unit_scale) if pts else None
        if ring and _valid_area(ring):
            rings.append(ring)
    return rings


def _import_pdf(data: bytes, unit_scale: float) -> list[list[tuple[float, float]]]:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    rings: list[list[tuple[float, float]]] = []
    for page in doc:
        for drawing in page.get_drawings():
            pts: list[tuple[float, float]] = []
            for item in drawing.get("items", []):
                op = item[0]
                if op == "l":
                    p1, p2 = item[1], item[2]
                    if not pts:
                        pts.append((p1.x, p1.y))
                    pts.append((p2.x, p2.y))
                elif op == "re":
                    r = item[1]
                    rect_pts = [
                        (r.x0, r.y0),
                        (r.x1, r.y0),
                        (r.x1, r.y1),
                        (r.x0, r.y1),
                        (r.x0, r.y0),
                    ]
                    ring = _close_ring(rect_pts, unit_scale)
                    if ring and _valid_area(ring):
                        rings.append(ring)
                elif op == "c":
                    p = item[-1]
                    pts.append((p.x, p.y))
                elif op == "qu":
                    q = item[1]
                    pts.extend([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)])
            ring = _close_ring(pts, unit_scale) if pts else None
            if ring and _valid_area(ring):
                rings.append(ring)
    return rings


def _import_hpgl(data: bytes, unit_scale: float) -> list[list[tuple[float, float]]]:
    text = data.decode("latin-1", errors="ignore")
    rings: list[list[tuple[float, float]]] = []
    pts: list[tuple[float, float]] = []
    for cmd, args in re.findall(r"([A-Z]{2})([^;]*)", text.upper()):
        nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", args)]
        if cmd == "PA" and len(nums) >= 2:
            pts.append((nums[0], nums[1]))
        elif cmd == "PD" and len(nums) >= 2:
            for i in range(0, len(nums) - 1, 2):
                pts.append((nums[i], nums[i + 1]))
        elif cmd in {"PU", "PG"} and pts:
            ring = _close_ring(pts, unit_scale)
            if ring and _valid_area(ring):
                rings.append(ring)
            pts = []
    ring = _close_ring(pts, unit_scale) if pts else None
    if ring and _valid_area(ring):
        rings.append(ring)
    return rings
