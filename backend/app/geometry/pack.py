from __future__ import annotations

from shapely.geometry import MultiPolygon
from shapely.prepared import prep

from app.geometry.panel import cell_pitch, cell_polygon, panel_footprint, split_disconnected
from app.geometry.score import rank_key, score_layout
from app.models import Layout, LayoutParams, Panel

ALLOWED_ANGLES = list(range(0, 180, 15))
MAX_LAYOUTS = 12
INSIDE_EPS = 1e-4
MAX_PANELS = 400


def _full(w: int, h: int) -> frozenset[tuple[int, int]]:
    return frozenset((i, j) for i in range(w) for j in range(h))


def _sizes(params: LayoutParams, swap: bool) -> list[tuple[int, int]]:
    max_w, max_h = (params.max_tall, params.max_wide) if swap else (params.max_wide, params.max_tall)
    return [(w, h) for w in range(max_w, 0, -1) for h in range(max_h, 0, -1)]


def _as_multi(geom) -> MultiPolygon:
    if geom is None or geom.is_empty:
        return MultiPolygon()
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    return MultiPolygon([g for g in geom.geoms if g.geom_type == "Polygon"])


def inset_packable(packable, inset_mm: float) -> MultiPolygon:
    if inset_mm <= 0 or packable.is_empty:
        return _as_multi(packable)
    return _as_multi(packable.buffer(-inset_mm))


def _refresh(geom):
    cleaned = _as_multi(geom.buffer(0) if not geom.is_empty else geom)
    if cleaned.is_empty:
        return cleaned, None
    return cleaned, prep(cleaned.buffer(INSIDE_EPS))


def _contained_prep(prepared, panel: Panel, i: int, j: int, params: LayoutParams) -> bool:
    return prepared.covers(cell_polygon(panel, i, j, params))


def _carve(origin, angle, w, h, params, prepared) -> frozenset[tuple[int, int]]:
    dummy = Panel("t", origin, angle, w, h, _full(w, h))
    kept = {(i, j) for i, j in dummy.occupied if _contained_prep(prepared, dummy, i, j, params)}
    if not kept:
        return frozenset()
    parts = split_disconnected(Panel("t", origin, angle, w, h, frozenset(kept)))
    return max(parts, key=lambda p: len(p.occupied)).occupied


def _best_at(origin, angle, params, prepared, carve: bool) -> Panel | None:
    seed = Panel("s", origin, angle, 1, 1, frozenset({(0, 0)}))
    if not _contained_prep(prepared, seed, 0, 0, params):
        return None
    swaps = [False, True] if angle % 90 == 0 else [False]
    best: Panel | None = None
    for swap in swaps:
        if carve:
            mw, mh = (params.max_tall, params.max_wide) if swap else (params.max_wide, params.max_tall)
            occupied = _carve(origin, angle, mw, mh, params, prepared)
            if occupied and (best is None or len(occupied) > len(best.occupied)):
                best = Panel("t", origin, angle, mw, mh, occupied)
            continue
        for w, h in _sizes(params, swap):
            panel = Panel("t", origin, angle, w, h, _full(w, h))
            fp = panel_footprint(panel, params)
            if fp.is_empty or not prepared.covers(fp):
                continue
            if best is None or len(panel.occupied) > len(best.occupied):
                best = panel
            break
    return best


def _bottom_left_fill(packable, params: LayoutParams, angles: list[float], carve: bool) -> list[Panel]:
    """Bottom-left-fill using inner-fit (covers). Subtract each panel plus panel gap."""
    remaining, prepared = _refresh(packable)
    if prepared is None:
        return []
    px, py = cell_pitch(params)
    placed: list[Panel] = []
    n = 0
    while n < MAX_PANELS and prepared is not None and not remaining.is_empty:
        minx, miny, maxx, maxy = remaining.bounds
        found: Panel | None = None
        y = miny
        while y < maxy - 1e-6 and found is None:
            x = minx
            while x < maxx - 1e-6 and found is None:
                for angle in angles:
                    cand = _best_at((x, y), angle, params, prepared, carve)
                    if cand:
                        found = cand
                        break
                x += px
            y += py
        if found is None:
            break
        found = Panel(f"p{n}", found.origin, found.angle_deg, found.cells_wide, found.cells_tall, found.occupied)
        placed.append(found)
        n += 1
        hole = panel_footprint(found, params)
        if params.panel_gap_mm > 0:
            hole = hole.buffer(params.panel_gap_mm)
        remaining, prepared = _refresh(remaining.difference(hole))
    return placed


def _dedup(layouts: list[Layout]) -> list[Layout]:
    seen = set()
    out = []
    for lay in layouts:
        key = (
            lay.family,
            lay.score.cell_count if lay.score else 0,
            tuple(
                sorted(
                    (round(p.origin[0], 1), round(p.origin[1], 1), round(p.angle_deg, 1), tuple(sorted(p.occupied)))
                    for p in lay.panels
                )
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(lay)
    return out


def pack_layouts(packable: MultiPolygon, params: LayoutParams, edge_angles_deg: list[float] | None = None) -> list[Layout]:
    packable = inset_packable(packable, params.edge_inset_mm)
    if packable.is_empty:
        return []
    extra = [a % 180 for a in (edge_angles_deg or [])]
    diag_angles = sorted(set(ALLOWED_ANGLES + extra) - {0, 90})

    specs = [
        ("rect90", [0.0, 90.0], False),
        ("irregular90", [0.0, 90.0], True),
        ("diagonal", diag_angles or [15.0], True),
    ]
    layouts: list[Layout] = []
    for family, angles, carve in specs:
        panels = _bottom_left_fill(packable, params, angles, carve)
        score = score_layout(panels, params)
        layouts.append(Layout(id=family, params=params, panels=panels, score=score, family=family))

    layouts = _dedup(layouts)
    layouts.sort(key=lambda lay: rank_key(lay.score))
    for i, lay in enumerate(layouts):
        lay.id = f"L{i}"
    return layouts[:MAX_LAYOUTS]
