"""Panels on the shell axis, each panel on its own grid.

Cells inside one panel share that panel's grid. A panel may align with the
shell's long axis or sit square to it. A leftover pocket is tried at other
angles only when its widest opening can hold one cell. Panels that already
fall on nearly the same grid are merged when the combined panel still passes
the packing rules.
max_tall caps the shell's long side and the cell's longer edge. max_wide caps
the shell's short side and the cell's shorter edge. A panel has to satisfy both.

A non-square cell is packed twice, once with the entered width and height and
once with those sides exchanged. The better of the two is kept and drawn with
the sides the user entered.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
from shapely import covers, maximum_inscribed_circle, polygons
from shapely.geometry import Polygon
from shapely.prepared import prep

from app.geometry.align import long_axis_deg
from app.geometry.panel import cell_polygon, panel_footprint, split_disconnected
from app.geometry.score import rank_key, score_layout
from app.models import Layout, LayoutParams, Panel

_MAX_PANELS = 40


def _to_local(x: float, y: float, angle: float) -> tuple[float, float]:
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    return (x * c + y * s, -x * s + y * c)


def _to_world(lx: float, ly: float, angle: float) -> tuple[float, float]:
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    return (lx * c - ly * s, lx * s + ly * c)


def _as_multi(geom):
    if geom is None or geom.is_empty:
        return Polygon()
    if geom.geom_type == "Polygon":
        return geom
    if geom.geom_type == "MultiPolygon":
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
    if not parts:
        return Polygon()
    from shapely.ops import unary_union

    return unary_union(parts)


def _parallel(angle: float, axis: float) -> bool:
    """True when `angle` runs along `axis`. Both are undirected (period 180°)."""
    delta = abs((angle - axis) % 180.0)
    if delta > 90.0:
        delta = 180.0 - delta
    return delta <= 45.0


def axis_cell_caps(params: LayoutParams, angle: float, long_axis: float) -> tuple[int, int]:
    """Cell caps (along local +x, along local +y).

    max_tall ("long side") limits both the shell's long side and the cell's
    longer edge. max_wide ("short side") limits the shell's short side and the
    cell's shorter edge. A merge has to satisfy both, so the tighter one wins.
    """
    short_cap = max(1, int(params.max_wide))
    long_cap = max(1, int(params.max_tall))
    if _parallel(angle, long_axis):
        shell_w, shell_h = long_cap, short_cap
    else:
        shell_w, shell_h = short_cap, long_cap
    if params.cell_w_mm > params.cell_h_mm + 1e-6:
        cell_w, cell_h = long_cap, short_cap
    elif params.cell_h_mm > params.cell_w_mm + 1e-6:
        cell_w, cell_h = short_cap, long_cap
    else:
        cell_w, cell_h = shell_w, shell_h
    return min(shell_w, cell_w), min(shell_h, cell_h)


def _largest_rect(
    mask: set[tuple[int, int]], params: LayoutParams, cap_w: int, cap_h: int
) -> tuple[int, int, int, int] | None:
    if not mask:
        return None
    i_min = min(i for i, _ in mask)
    i_max = max(i for i, _ in mask)
    j_min = min(j for _, j in mask)
    j_max = max(j for _, j in mask)
    heights = [0] * (i_max - i_min + 1)
    cw, ch, gap = params.cell_w_mm, params.cell_h_mm, params.cell_gap_mm
    best: tuple[tuple[float, float], int, int, int, int] | None = None

    def consider(w: int, h: int, i0: int, j0: int) -> None:
        nonlocal best
        if w <= 0 or h <= 0 or w > cap_w or h > cap_h:
            return
        pw = w * cw + (w - 1) * gap
        ph = h * ch + (h - 1) * gap
        aspect = min(pw, ph) / max(pw, ph)
        key = (float(w * h), aspect)
        if best is None or key > best[0]:
            best = (key, i0, j0, w, h)

    for j in range(j_min, j_max + 1):
        for t, i in enumerate(range(i_min, i_max + 1)):
            heights[t] = heights[t] + 1 if (i, j) in mask else 0
        stack = [-1]
        extended = heights + [0]
        for idx, hgt in enumerate(extended):
            while stack[-1] != -1 and heights[stack[-1]] > hgt:
                sh = heights[stack.pop()]
                width = idx - stack[-1] - 1
                left = i_min + stack[-1] + 1
                consider(width, sh, left, j - sh + 1)
            stack.append(idx)
    if best is None:
        return None
    return best[1], best[2], best[3], best[4]


def _raster(geom, params: LayoutParams, angle: float, phase_u: float, phase_v: float, grown=None):
    if geom.is_empty:
        return set(), (0.0, 0.0)
    if grown is None:
        grown = geom.buffer(1e-4)
    px = params.cell_w_mm + params.cell_gap_mm
    py = params.cell_h_mm + params.cell_gap_mm
    cw, ch = params.cell_w_mm, params.cell_h_mm
    minx, miny, maxx, maxy = geom.bounds
    corners = [_to_local(x, y, angle) for x, y in ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy))]
    u0 = min(p[0] for p in corners) + phase_u * px
    v0 = min(p[1] for p in corners) + phase_v * py
    u1 = max(p[0] for p in corners)
    v1 = max(p[1] for p in corners)
    ni = int((u1 - u0) / px) + 2
    nj = int((v1 - v0) / py) + 2
    if ni <= 0 or nj <= 0:
        return set(), (u0, v0)
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    ii, jj = np.meshgrid(np.arange(ni, dtype=np.float64), np.arange(nj, dtype=np.float64), indexing="ij")
    lx = u0 + ii * px
    ly = v0 + jj * py
    local = ((lx, ly), (lx + cw, ly), (lx + cw, ly + ch), (lx, ly + ch), (lx, ly))
    xs = [clx * c - cly * s for clx, cly in local]
    ys = [clx * s + cly * c for clx, cly in local]
    coords = np.stack((np.stack(xs, axis=-1), np.stack(ys, axis=-1)), axis=-1).reshape(-1, 5, 2)
    hit = np.atleast_1d(covers(grown, polygons(coords)))
    chosen = np.flatnonzero(hit)
    flat_i = ii.ravel()
    flat_j = jj.ravel()
    cells = {(int(flat_i[k]), int(flat_j[k])) for k in chosen}
    return cells, (u0, v0)


def _local_bounds(geom, angle: float) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = geom.bounds
    pts = [_to_local(x, y, angle) for x, y in ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy))]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def _frac(value: float, origin: float, pitch: float) -> float:
    if pitch <= 0:
        return 0.0
    return ((value - origin) / pitch) % 1.0


def _axis_delta(a: float, b: float) -> float:
    delta = abs((a - b) % 180.0)
    return min(delta, 180.0 - delta)


def _grid_tol(params: LayoutParams) -> float:
    """How far a cell may sit from a shared grid and still be a merge candidate."""
    return max(params.panel_gap_mm, params.cell_gap_mm, 1.0) + 2.0


def _grow(mask: set[tuple[int, int]], rect: tuple[int, int, int, int], cap_w: int, cap_h: int) -> set[tuple[int, int]]:
    """Add shell cells that continue this panel without leaving the cap."""
    i0, j0, w, h = rect
    occupied = {(i, j) for i in range(i0, i0 + w) for j in range(j0, j0 + h)}
    occupied &= mask
    if not occupied:
        return occupied
    i_min, i_max = min(i for i, _ in occupied), max(i for i, _ in occupied)
    j_min, j_max = min(j for _, j in occupied), max(j for _, j in occupied)
    frontier = list(occupied)
    while frontier:
        i, j = frontier.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (i + di, j + dj)
            if nxt in occupied or nxt not in mask:
                continue
            ni, nj = nxt
            n_i_min, n_i_max = min(i_min, ni), max(i_max, ni)
            n_j_min, n_j_max = min(j_min, nj), max(j_max, nj)
            if n_i_max - n_i_min + 1 > cap_w or n_j_max - n_j_min + 1 > cap_h:
                continue
            occupied.add(nxt)
            frontier.append(nxt)
            i_min, i_max = n_i_min, n_i_max
            j_min, j_max = n_j_min, n_j_max
    return occupied


def _make_panel(raster_origin: tuple[float, float], angle: float, cells: set[tuple[int, int]], params: LayoutParams, pid: str) -> Panel:
    u0, v0 = raster_origin
    px = params.cell_w_mm + params.cell_gap_mm
    py = params.cell_h_mm + params.cell_gap_mm
    i0 = min(i for i, _ in cells)
    j0 = min(j for _, j in cells)
    i1 = max(i for i, _ in cells)
    j1 = max(j for _, j in cells)
    origin = _to_world(u0 + i0 * px, v0 + j0 * py, angle)
    occupied = frozenset((i - i0, j - j0) for i, j in cells)
    return Panel(pid, origin, angle, i1 - i0 + 1, j1 - j0 + 1, occupied)


def _candidate_phases(remaining, angle: float, params: LayoutParams, panels: list[Panel], fine: bool):
    steps = (0.0, 0.25, 0.5, 0.75) if fine else (0.0, 0.5)
    phases = {(a, b) for a in steps for b in steps}
    if remaining.is_empty:
        return list(phases)
    u0, v0, _, _ = _local_bounds(remaining, angle)
    px = params.cell_w_mm + params.cell_gap_mm
    py = params.cell_h_mm + params.cell_gap_mm
    for panel in panels:
        if _axis_delta(panel.angle_deg, angle) > 1.0:
            continue
        lx, ly = _to_local(panel.origin[0], panel.origin[1], angle)
        phases.add((_frac(lx, u0, px), _frac(ly, v0, py)))
    return list(phases)


def _best_on_angle(remaining, params: LayoutParams, angle: float, long_axis: float, panels: list[Panel], fine: bool):
    cap_w, cap_h = axis_cell_caps(params, angle, long_axis)
    best = None
    grown = remaining.buffer(1e-4)
    for pu, pv in _candidate_phases(remaining, angle, params, panels, fine):
        mask, origin_local = _raster(remaining, params, angle, pu, pv, grown)
        rect = _largest_rect(mask, params, cap_w, cap_h)
        if rect is None:
            continue
        cells = _grow(mask, rect, cap_w, cap_h)
        if not cells:
            continue
        i0 = min(i for i, _ in cells)
        i1 = max(i for i, _ in cells)
        j0 = min(j for _, j in cells)
        j1 = max(j for _, j in cells)
        fill = len(cells) / ((i1 - i0 + 1) * (j1 - j0 + 1))
        # Same panel size: keep the lattice that still has more cells left to place.
        key = (len(cells), len(mask), fill)
        if best is None or key > best[0]:
            best = (key, origin_local, cells)
    return best


def _commit(remaining, panel: Panel, params: LayoutParams):
    hole = panel_footprint(panel, params)
    if hole.is_empty:
        return remaining
    if params.panel_gap_mm > 0:
        hole = hole.buffer(params.panel_gap_mm)
    return _as_multi(remaining.difference(hole))


def _fill(geom, params: LayoutParams, angles: list[float], long_axis: float, panels: list[Panel], fine: bool) -> tuple[list[Panel], object]:
    remaining = geom
    while len(panels) < _MAX_PANELS and not remaining.is_empty:
        best = None
        for angle in angles:
            placed = _best_on_angle(remaining, params, angle, long_axis, panels, fine)
            if placed is None:
                continue
            key, origin_local, cells = placed
            if best is None or key > best[0]:
                best = (key, angle, origin_local, cells)
        if best is None:
            break
        _, angle, origin_local, cells = best
        panel = _make_panel(origin_local, angle, cells, params, f"p{len(panels)}")
        panels.append(panel)
        remaining = _commit(remaining, panel, params)
    return panels, remaining


def _cell_indices(panel: Panel, origin: tuple[float, float], angle: float, params: LayoutParams):
    px = params.cell_w_mm + params.cell_gap_mm
    py = params.cell_h_mm + params.cell_gap_mm
    ox, oy = origin
    worst = 0.0
    indices: list[tuple[int, int]] = []
    for i, j in panel.occupied:
        rx, ry = _to_world(i * px, j * py, panel.angle_deg)
        ul, vl = _to_local(panel.origin[0] + rx - ox, panel.origin[1] + ry - oy, angle)
        iu = int(round(ul / px))
        iv = int(round(vl / py))
        worst = max(worst, math.hypot(ul - iu * px, vl - iv * py))
        indices.append((iu, iv))
    return worst, indices


def _try_merge(keep: Panel, other: Panel, others: list[Panel], params: LayoutParams, packable, long_axis: float) -> Panel | None:
    if _axis_delta(keep.angle_deg, other.angle_deg) > 1.0:
        return None
    worst, extra = _cell_indices(other, keep.origin, keep.angle_deg, params)
    if worst > _grid_tol(params):
        return None
    _, base = _cell_indices(keep, keep.origin, keep.angle_deg, params)
    combined = set(base)
    if any(idx in combined for idx in extra):
        return None
    combined.update(extra)
    i0 = min(i for i, _ in combined)
    j0 = min(j for _, j in combined)
    i1 = max(i for i, _ in combined)
    j1 = max(j for _, j in combined)
    cap_w, cap_h = axis_cell_caps(params, keep.angle_deg, long_axis)
    if i1 - i0 + 1 > cap_w or j1 - j0 + 1 > cap_h:
        return None
    px = params.cell_w_mm + params.cell_gap_mm
    py = params.cell_h_mm + params.cell_gap_mm
    shift = _to_world(i0 * px, j0 * py, keep.angle_deg)
    origin = (keep.origin[0] + shift[0], keep.origin[1] + shift[1])
    occupied = frozenset((i - i0, j - j0) for i, j in combined)
    merged = Panel(keep.id, origin, keep.angle_deg, i1 - i0 + 1, j1 - j0 + 1, occupied)
    if len(split_disconnected(merged)) != 1:
        return None
    prepared = prep(packable.buffer(1e-4))
    for i, j in merged.occupied:
        if not prepared.covers(cell_polygon(merged, i, j, params)):
            return None
    footprint = panel_footprint(merged, params)
    for panel in others:
        other_fp = panel_footprint(panel, params)
        if other_fp.is_empty or footprint.is_empty:
            continue
        if footprint.distance(other_fp) < params.panel_gap_mm - 1e-6:
            return None
        for i, j in merged.occupied:
            cell = cell_polygon(merged, i, j, params)
            for oi, oj in panel.occupied:
                if cell_polygon(panel, oi, oj, params).intersects(cell.buffer(-1e-4)):
                    return None
    return merged


def merge_panels(panels: list[Panel], params: LayoutParams, packable, long_axis: float) -> list[Panel]:
    """Join panels on nearly the same grid when the result still passes the rules."""
    current = list(panels)
    changed = True
    while changed:
        changed = False
        pair = None
        for i, keep in enumerate(current):
            for j in range(i + 1, len(current)):
                other = current[j]
                rest = [p for k, p in enumerate(current) if k != i and k != j]
                # Snap the smaller panel onto the larger one's grid.
                host, guest = (keep, other) if len(keep.occupied) >= len(other.occupied) else (other, keep)
                merged = _try_merge(host, guest, rest, params, packable, long_axis)
                if merged is None:
                    continue
                pair = (i, j, merged)
                break
            if pair is not None:
                break
        if pair is None:
            break
        i, j, merged = pair
        current = [p for k, p in enumerate(current) if k != i and k != j]
        current.append(merged)
        changed = True
    return [
        Panel(f"p{n}", p.origin, p.angle_deg, p.cells_wide, p.cells_tall, p.occupied)
        for n, p in enumerate(current)
    ]


def _primary_angles(long_axis: float) -> list[float]:
    return [long_axis % 360.0, (long_axis + 90.0) % 360.0]


_SECONDARY_STEP_DEG = 5


def _secondary_angles(primary: list[float]) -> list[float]:
    """Angles other than the shell axis, every 5°."""
    out = []
    for angle in range(0, 180, _SECONDARY_STEP_DEG):
        if all(_axis_delta(angle, base) > _SECONDARY_STEP_DEG / 2 for base in primary):
            out.append(float(angle))
    return out


# maximum_inscribed_circle underestimates the radius by at most this much.
_CIRCLE_TOLERANCE_MM = 0.25


def _polygons(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon" and not g.is_empty]


def _cell_can_fit(geom, params: LayoutParams) -> bool:
    """True when some pocket is wide enough that one cell might fit.

    A cell cannot fit at any angle when the pocket's largest inscribed circle
    is narrower than the cell's shorter side. The returned radius is at most
    `_CIRCLE_TOLERANCE_MM` short of the true value, so the comparison uses that
    upper bound and only rejects pockets that are certainly too narrow.
    """
    short = min(params.cell_w_mm, params.cell_h_mm)
    need = params.cell_w_mm * params.cell_h_mm
    for part in _polygons(geom):
        if part.area + 1e-6 < need:
            continue
        radius = maximum_inscribed_circle(part, tolerance=_CIRCLE_TOLERANCE_MM).length
        if 2 * (radius + _CIRCLE_TOLERANCE_MM) + 1e-6 >= short:
            return True
    return False


def _nearly_square(params: LayoutParams) -> bool:
    return abs(params.cell_w_mm - params.cell_h_mm) <= 1e-6


def _swapped_cell(params: LayoutParams) -> LayoutParams:
    """Same cell, with the entered width and height exchanged."""
    return replace(params, cell_w_mm=params.cell_h_mm, cell_h_mm=params.cell_w_mm)


def _reframe_swapped_panel(panel: Panel, user: LayoutParams) -> Panel:
    """Draw a swapped-orientation panel with the user's width and height.

    The swapped pack stores the user's height along local +x. Rotating the
    panel by +90° and reversing the column index puts the user's width along
    local +x. Each cell stays on the same world rectangle.
    """
    span = max(i for i, _ in panel.occupied) + 1
    pitch = user.cell_h_mm + user.cell_gap_mm
    x_shift = (span - 1) * pitch + user.cell_h_mm
    dx, dy = _to_world(x_shift, 0.0, panel.angle_deg)
    ox, oy = panel.origin
    occupied = frozenset((j, span - 1 - i) for i, j in panel.occupied)
    wide = max(i for i, _ in occupied) + 1
    tall = max(j for _, j in occupied) + 1
    return Panel(panel.id, (ox + dx, oy + dy), (panel.angle_deg + 90.0) % 360.0, wide, tall, occupied)


def _pack_oriented(packable, params: LayoutParams) -> list[Panel]:
    long_axis = long_axis_deg(packable)
    primary = _primary_angles(long_axis)
    panels, remaining = _fill(packable, params, primary, long_axis, [], True)
    if _cell_can_fit(remaining, params):
        panels, _remaining = _fill(remaining, params, _secondary_angles(primary), long_axis, panels, False)
    return merge_panels(panels, params, packable, long_axis)


def pack_conventional(packable, params: LayoutParams) -> list[Layout]:
    if packable is None or packable.is_empty:
        return []
    orientations = [params]
    if not _nearly_square(params):
        orientations.append(_swapped_cell(params))
    best_panels: list[Panel] | None = None
    best_key = None
    for packed in orientations:
        panels = _pack_oriented(packable, packed)
        if packed is not params:
            panels = [_reframe_swapped_panel(panel, params) for panel in panels]
        key = rank_key(score_layout(panels, params))
        if best_key is None or key < best_key:
            best_key = key
            best_panels = panels
    panels = best_panels or []
    score = score_layout(panels, params)
    return [Layout(id="aligned", params=params, panels=panels, score=score, family="aligned")]
