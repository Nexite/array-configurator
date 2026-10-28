from __future__ import annotations

from shapely.geometry import MultiPolygon
from shapely.prepared import prep

from app.geometry.conventional import pack_conventional
from app.geometry.panel import cell_pitch, cell_polygon, panel_footprint, split_disconnected
from app.geometry.score import rank_key, score_layout
from app.models import Layout, LayoutParams, Panel

ALLOWED_ANGLES = list(range(0, 180, 15))
MAX_LAYOUTS = 12
INSIDE_EPS = 1e-4
MAX_PANELS = 400
_SQUARE_EPS_MM = 1e-6


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


def _scan_steps(params: LayoutParams, angles: list[float]) -> tuple[float, float]:
    """World-axis origin steps. 90° swaps pitch so swapped-aspect fills are not skipped."""
    px, py = cell_pitch(params)
    if len(angles) == 1:
        n = _norm_angle(angles[0])
        if abs(n) < 1e-9 or abs(n - 180.0) < 1e-9:
            return px, py
        if abs(n - 90.0) < 1e-9:
            return py, px
    step = min(px, py)
    return step, step


def _bottom_left_fill(packable, params: LayoutParams, angles: list[float], carve: bool) -> list[Panel]:
    """Bottom-left-fill using inner-fit (covers). Subtract each panel plus panel gap."""
    remaining, prepared = _refresh(packable)
    if prepared is None:
        return []
    sx, sy = _scan_steps(params, angles)
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
                x += sx
            y += sy
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


def circular_angle_delta(a: float, b: float) -> float:
    """Smallest difference between two cell orientations on the 180° circle."""
    d = abs((a - b) % 180.0)
    return min(d, 180.0 - d)


def max_pairwise_spread(angles: list[float]) -> float:
    if len(angles) < 2:
        return 0.0
    return max(circular_angle_delta(a, b) for i, a in enumerate(angles) for b in angles[i + 1 :])


def _norm_angle(angle: float) -> float:
    return float(angle) % 180.0


def _cells_are_square(params: LayoutParams) -> bool:
    return abs(params.cell_w_mm - params.cell_h_mm) <= _SQUARE_EPS_MM


def _rect_bases(params: LayoutParams, extra: list[float]) -> list[float]:
    stop = 90 if _cells_are_square(params) else 180
    bases = [float(a) for a in range(0, stop, 15)]
    for angle in extra:
        n = _norm_angle(angle)
        if n not in bases:
            bases.append(n)
    return bases


def _angles_in_window(start: float, spread: float, extras: list[float] | None = None) -> list[float]:
    """Allowed angles in the forward 180° window [start, start+spread]."""
    pool = [float(a) for a in ALLOWED_ANGLES]
    for angle in extras or []:
        n = _norm_angle(angle)
        if n not in pool:
            pool.append(n)
    pool.sort()
    start_n = _norm_angle(start)
    out: list[float] = []
    for angle in pool:
        if (angle - start_n) % 180.0 <= spread + 1e-9:
            out.append(angle)
    return out


def _rect_family(angle: float) -> str:
    n = _norm_angle(angle)
    if abs(n) < 1e-9 or abs(n - 180.0) < 1e-9:
        return "rect90"
    if abs(n - 90.0) < 1e-9:
        return "rect90-rot"
    return f"rect-{int(round(n))}"


def _irregular_family(angle: float) -> str:
    n = _norm_angle(angle)
    if abs(n) < 1e-9 or abs(n - 180.0) < 1e-9:
        return "irregular90"
    if abs(n - 90.0) < 1e-9:
        return "irregular90-rot"
    return f"irregular-{int(round(n))}"


def _search_specs(params: LayoutParams, edge_angles_deg: list[float] | None) -> list[tuple[str, list[float], bool]]:
    extra = [_norm_angle(a) for a in (edge_angles_deg or [])]
    specs: list[tuple[str, list[float], bool]] = []
    seen: set[tuple[str, tuple[float, ...], bool]] = set()

    def add(family: str, angles: list[float], carve: bool) -> None:
        if not angles:
            return
        key = (family, tuple(angles), carve)
        if key in seen:
            return
        seen.add(key)
        specs.append((family, angles, carve))

    for angle in _rect_bases(params, extra):
        add(_rect_family(angle), [angle], False)

    irregular_bases = [0.0, 90.0, 45.0]
    for angle in extra:
        if angle not in irregular_bases:
            irregular_bases.append(angle)
    for angle in irregular_bases:
        add(_irregular_family(angle), [angle], True)

    spread = max(0.0, float(params.orientation_spread_deg))
    mixed_starts = [0.0]
    if spread > 0:
        mixed_starts.append(15.0)
    for start in mixed_starts:
        window = _angles_in_window(start, spread, extra)
        if len(window) < 2:
            continue
        add(f"mixed-{int(round(_norm_angle(start)))}", window, False)

    return specs


def pack_layouts(packable: MultiPolygon, params: LayoutParams, edge_angles_deg: list[float] | None = None) -> list[Layout]:
    packable = inset_packable(packable, params.edge_inset_mm)
    if packable.is_empty:
        return []

    layouts: list[Layout] = list(pack_conventional(packable, params))
    # The aligned packer is the one we keep. A single axis-aligned rectangular
    # pass and one irregular pass stay so older layouts remain comparable,
    # without the 15° sweep that made Generate stall on a real shell.
    for family, angles, carve in (
        ("rect90", [0.0], False),
        ("irregular90", [0.0], True),
    ):
        panels = _bottom_left_fill(packable, params, angles, carve)
        score = score_layout(panels, params)
        layouts.append(Layout(id=family, params=params, panels=panels, score=score, family=family))

    layouts = _dedup(layouts)
    layouts.sort(key=lambda lay: rank_key(lay.score))
    for i, lay in enumerate(layouts):
        lay.id = f"L{i}"
    return layouts[:MAX_LAYOUTS]
