from __future__ import annotations

import math

from shapely.geometry.base import BaseGeometry


def _fold_axis(angle_deg: float) -> float:
    """Undirected axis in [0, 90). 0° and 90° are the same rectangle orientation."""
    ang = angle_deg % 180.0
    if ang >= 90.0:
        ang -= 90.0
    return ang


def _rings(geom: BaseGeometry):
    if geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        yield geom
    elif geom.geom_type == "MultiPolygon":
        yield from geom.geoms
    elif geom.geom_type == "GeometryCollection":
        for part in geom.geoms:
            yield from _rings(part)


def _segments(poly) -> list[tuple[float, float]]:
    coords = list(poly.exterior.coords)
    out = []
    for a, b in zip(coords, coords[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1.0:
            continue
        ang = _fold_axis(math.degrees(math.atan2(dy, dx)))
        out.append((length, ang))
    return out


def long_axis_deg(geom: BaseGeometry) -> float:
    """Direction of the shell's longer side, in [0, 180).

    0° runs to the right and 90° runs up. This is the side that should take
    the smaller cell count: a 24×6 cap is 24 cells across the short side.
    """
    best_area = -1.0
    best_angle = 0.0
    for poly in _rings(geom):
        hull = poly.convex_hull
        if hull.is_empty or hull.geom_type != "Polygon":
            continue
        rect = hull.minimum_rotated_rectangle
        if rect.is_empty or rect.geom_type != "Polygon":
            continue
        coords = list(rect.exterior.coords)
        longest = 0.0
        angle = 0.0
        for a, b in zip(coords, coords[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length > longest:
                longest = length
                angle = math.degrees(math.atan2(dy, dx)) % 180.0
        if poly.area > best_area:
            best_area = poly.area
            best_angle = angle
    return best_angle


def dominant_axis_deg(geom: BaseGeometry) -> float:
    """Alignment angle for a vaguely rectangular aeroshell, in [0, 90).

    Long edges of the convex hull and of a simplified outline are clustered.
    Spline outlines become real lines after simplification; the hull recovers
    the outer rectangle when the shell has notches.
    """
    weighted: dict[int, float] = {}
    longest = 0.0
    pieces: list[tuple[float, float]] = []
    for poly in _rings(geom):
        span = max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1], 1.0)
        sources = [poly.convex_hull]
        simplified = poly.simplify(max(span * 0.01, 20.0), preserve_topology=True)
        if not simplified.is_empty and simplified.geom_type == "Polygon":
            sources.append(simplified)
        hull = poly.convex_hull
        if not hull.is_empty and hull.geom_type == "Polygon":
            rect = hull.minimum_rotated_rectangle
            if rect.geom_type == "Polygon":
                sources.append(rect)
        for src in sources:
            if src.geom_type != "Polygon":
                continue
            for length, ang in _segments(src):
                pieces.append((length, ang))
                longest = max(longest, length)
    if not pieces:
        return 0.0
    for length, ang in pieces:
        if length < 0.12 * longest:
            continue
        key = int(round(ang / 2.0) * 2) % 90
        weighted[key] = weighted.get(key, 0.0) + length
    if not weighted:
        return pieces[0][1]
    return float(max(weighted, key=weighted.get))
