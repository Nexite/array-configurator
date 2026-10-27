from __future__ import annotations

from shapely.geometry import MultiPolygon

from app.geometry.panel import cell_pitch, cell_polygon, panel_footprint, split_disconnected
from app.geometry.score import rank_key, score_layout
from app.models import Layout, LayoutParams, Panel

ALLOWED_ANGLES = list(range(0, 180, 15))
MAX_LAYOUTS = 12
INSIDE_EPS = 1e-4


def _full(w: int, h: int) -> frozenset[tuple[int, int]]:
    return frozenset((i, j) for i in range(w) for j in range(h))


def _sizes(params: LayoutParams, swap: bool) -> list[tuple[int, int]]:
    max_w, max_h = (params.max_tall, params.max_wide) if swap else (params.max_wide, params.max_tall)
    return [(w, h) for w in range(max_w, 0, -1) for h in range(max_h, 0, -1)]


def _contained(panel: Panel, i: int, j: int, params: LayoutParams, packable) -> bool:
    poly = cell_polygon(panel, i, j, params)
    return packable.buffer(INSIDE_EPS).covers(poly)


def _fits_cells(panel: Panel, params: LayoutParams, packable) -> bool:
    return bool(panel.occupied) and all(_contained(panel, i, j, params, packable) for i, j in panel.occupied)


def _conflicts(panel: Panel, existing: list[Panel], params: LayoutParams) -> bool:
    fp = panel_footprint(panel, params)
    if fp.is_empty:
        return True
    for other in existing:
        ofp = panel_footprint(other, params)
        if fp.intersects(ofp.buffer(-1e-6)):
            return True
        if params.panel_gap_mm > 0 and fp.distance(ofp) < params.panel_gap_mm - 1e-9:
            return True
    return False


def _carve(origin, angle, w, h, params, packable) -> frozenset[tuple[int, int]]:
    dummy = Panel("t", origin, angle, w, h, _full(w, h))
    kept = {(i, j) for i, j in dummy.occupied if _contained(dummy, i, j, params, packable)}
    if not kept:
        return frozenset()
    parts = split_disconnected(Panel("t", origin, angle, w, h, frozenset(kept)))
    return max(parts, key=lambda p: len(p.occupied)).occupied


def _try_panel(origin, angle, w, h, occupied, params, packable, existing, pid) -> Panel | None:
    panel = Panel(pid, origin, angle, w, h, occupied)
    if not _fits_cells(panel, params, packable):
        return None
    if _conflicts(panel, existing, params):
        return None
    return panel


def _origins(packable, params) -> list[tuple[float, float]]:
    minx, miny, _, _ = packable.bounds
    px, py = cell_pitch(params)
    return [(minx + fx * px, miny + fy * py) for fx in (0.0, 0.5) for fy in (0.0, 0.5)]


def _greedy(packable, params, angles: list[float], carve: bool) -> list[Panel]:
    placed: list[Panel] = []
    n = 0
    for origin in _origins(packable, params):
        for angle in angles:
            swaps = [False, True] if angle % 90 == 0 else [False]
            for swap in swaps:
                for w, h in _sizes(params, swap):
                    occupied = _carve(origin, angle, w, h, params, packable) if carve else _full(w, h)
                    panel = _try_panel(origin, angle, w, h, occupied, params, packable, placed, f"p{n}")
                    if panel:
                        placed.append(panel)
                        n += 1
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
        panels = _greedy(packable, params, angles, carve)
        score = score_layout(panels, params)
        layouts.append(Layout(id=family, params=params, panels=panels, score=score, family=family))

    layouts = _dedup(layouts)
    layouts.sort(key=lambda lay: rank_key(lay.score))
    for i, lay in enumerate(layouts):
        lay.id = f"L{i}"
    return layouts[:MAX_LAYOUTS]
