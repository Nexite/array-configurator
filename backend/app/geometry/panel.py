from __future__ import annotations

import math
from collections import deque

from shapely.geometry import Polygon
from shapely.ops import unary_union

from app.models import LayoutParams, Panel


def cell_pitch(params: LayoutParams) -> tuple[float, float]:
    return (params.cell_w_mm + params.cell_gap_mm, params.cell_h_mm + params.cell_gap_mm)


def _rotate(dx: float, dy: float, angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    return (dx * c - dy * s, dx * s + dy * c)


def cell_polygon(panel: Panel, i: int, j: int, params: LayoutParams) -> Polygon:
    px, py = cell_pitch(params)
    ox, oy = panel.origin
    local = (
        (i * px, j * py),
        (i * px + params.cell_w_mm, j * py),
        (i * px + params.cell_w_mm, j * py + params.cell_h_mm),
        (i * px, j * py + params.cell_h_mm),
    )
    world = []
    for lx, ly in local:
        rx, ry = _rotate(lx, ly, panel.angle_deg)
        world.append((ox + rx, oy + ry))
    return Polygon(world)


def panel_footprint(panel: Panel, params: LayoutParams) -> Polygon:
    polys = [cell_polygon(panel, i, j, params) for i, j in panel.occupied]
    if not polys:
        return Polygon()
    return unary_union(polys).buffer(0)


def split_disconnected(panel: Panel) -> list[Panel]:
    remaining = set(panel.occupied)
    parts: list[Panel] = []
    n = 0
    while remaining:
        start = min(remaining)
        q = deque([start])
        remaining.remove(start)
        comp = {start}
        while q:
            i, j = q.popleft()
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if (ni, nj) in remaining:
                    remaining.remove((ni, nj))
                    comp.add((ni, nj))
                    q.append((ni, nj))
        parts.append(
            Panel(
                id=f"{panel.id}_{n}",
                origin=panel.origin,
                angle_deg=panel.angle_deg,
                cells_wide=panel.cells_wide,
                cells_tall=panel.cells_tall,
                occupied=frozenset(comp),
            )
        )
        n += 1
    return parts


def is_rectangular(panel: Panel) -> bool:
    full = {(i, j) for i in range(panel.cells_wide) for j in range(panel.cells_tall)}
    return set(panel.occupied) == full


def is_axis_aligned(panel: Panel) -> bool:
    return panel.angle_deg % 90 == 0
