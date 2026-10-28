from __future__ import annotations

import math

from shapely.geometry.base import BaseGeometry


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
