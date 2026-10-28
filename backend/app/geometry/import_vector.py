from __future__ import annotations

import io
import math
import re
import shutil
import tempfile
from pathlib import Path

import ezdxf
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import polygonize, unary_union

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


def _join_paths(paths: list[list[tuple[float, float]]], tol: float) -> list[list[tuple[float, float]]]:
    unused = [p for p in paths if len(p) >= 2]
    joined: list[list[tuple[float, float]]] = []
    while unused:
        cur = unused.pop()
        changed = True
        while changed:
            changed = False
            for i, other in enumerate(unused):
                if _dist(cur[-1], other[0]) <= tol:
                    cur = cur + other[1:]
                    unused.pop(i)
                    changed = True
                    break
                if _dist(cur[-1], other[-1]) <= tol:
                    cur = cur + list(reversed(other[:-1]))
                    unused.pop(i)
                    changed = True
                    break
                if _dist(cur[0], other[-1]) <= tol:
                    cur = other + cur[1:]
                    unused.pop(i)
                    changed = True
                    break
                if _dist(cur[0], other[0]) <= tol:
                    cur = list(reversed(other)) + cur[1:]
                    unused.pop(i)
                    changed = True
                    break
        joined.append(cur)
    return joined


def _weld_endpoints(
    paths: list[list[tuple[float, float]]], tol: float
) -> list[list[tuple[float, float]]]:
    """Move segment endpoints that lie within tol onto one shared point.

    A shell exported as separate splines and lines meets at vertices, often a
    fraction of a millimetre apart. Welding those ends lets the closed faces
    be recovered. Edges longer than tol stay intact.
    """
    ends: list[tuple[float, float]] = []
    for pts in paths:
        ends.append(pts[0])
        ends.append(pts[-1])
    parent = list(range(len(ends)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    cell = tol if tol > 0 else 1.0
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, pt in enumerate(ends):
        buckets.setdefault((math.floor(pt[0] / cell), math.floor(pt[1] / cell)), []).append(i)
    for i, pt in enumerate(ends):
        kx, ky = math.floor(pt[0] / cell), math.floor(pt[1] / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in buckets.get((kx + dx, ky + dy), ()):
                    if j > i and _dist(pt, ends[j]) <= tol:
                        union(i, j)
    groups: dict[int, list[tuple[float, float]]] = {}
    for i, pt in enumerate(ends):
        groups.setdefault(find(i), []).append(pt)
    center = {
        root: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for root, pts in groups.items()
    }
    welded: list[list[tuple[float, float]]] = []
    for i, pts in enumerate(paths):
        nxt = list(pts)
        nxt[0] = center[find(2 * i)]
        nxt[-1] = center[find(2 * i + 1)]
        if _dist(nxt[0], nxt[-1]) > 1e-9:
            welded.append(nxt)
    return welded


def _polygonize_paths(
    paths: list[list[tuple[float, float]]], tol: float
) -> list[list[tuple[float, float]]]:
    """Closed faces formed by a network of curves, including shared edges."""
    usable = [p for p in paths if len(p) >= 2]
    if not usable:
        return []
    lines: list[LineString] = []
    for pts in _weld_endpoints(usable, tol):
        try:
            line = LineString(pts)
        except Exception:
            continue
        if line.is_empty or line.length <= 1e-9:
            continue
        lines.append(line)
    if not lines:
        return []
    try:
        merged = unary_union(MultiLineString(lines))
    except Exception:
        return []
    rings: list[list[tuple[float, float]]] = []
    for poly in polygonize(merged):
        exterior = [(float(x), float(y)) for x, y in poly.exterior.coords]
        # Sub-square-millimetre faces are noding slivers, not shell regions.
        if Polygon(exterior).area > 1.0:
            rings.append(exterior)
        for hole in poly.interiors:
            hole_pts = [(float(x), float(y)) for x, y in hole.coords]
            if Polygon(hole_pts).area > 1.0:
                rings.append(hole_pts)
    return rings


def _import_dxf(data: bytes, unit_scale: float) -> list[list[tuple[float, float]]]:
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    doc = ezdxf.read(io.StringIO(text))
    msp = doc.modelspace()
    open_paths: list[list[tuple[float, float]]] = []
    rings: list[list[tuple[float, float]]] = []
    for e in msp:
        kind = e.dxftype()
        pts: list[tuple[float, float]] = []
        closed = False
        if kind == "LWPOLYLINE":
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            closed = bool(e.closed)
        elif kind == "POLYLINE":
            pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices]
            closed = bool(e.is_closed)
        elif kind == "SPLINE":
            pts = [(float(p.x), float(p.y)) for p in e.flattening(1.0)]
        elif kind == "CIRCLE":
            c = e.dxf.center
            r = float(e.dxf.radius)
            pts = [
                (c.x + r * math.cos(t), c.y + r * math.sin(t))
                for t in [i * 2 * math.pi / 64 for i in range(65)]
            ]
            closed = True
        elif kind == "LINE":
            s, t = e.dxf.start, e.dxf.end
            pts = [(float(s.x), float(s.y)), (float(t.x), float(t.y))]
        elif kind == "ARC":
            pts = [(float(p.x), float(p.y)) for p in e.flattening(1.0)]
        if not pts:
            continue
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        ring = _close_ring(pts, unit_scale)
        if ring and _valid_area(ring):
            rings.append(ring)
        else:
            open_paths.append([(x * unit_scale, y * unit_scale) for x, y in pts])
    faces = _polygonize_paths(open_paths, CLOSE_TOL_MM)
    if faces:
        rings.extend(faces)
    else:
        for path in _join_paths(open_paths, CLOSE_TOL_MM):
            ring = _close_ring([(x, y) for x, y in path], 1.0)
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
