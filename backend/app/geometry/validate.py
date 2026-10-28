from __future__ import annotations

from shapely.geometry import MultiPolygon
from shapely.prepared import prep

from app.geometry.pack import inset_packable
from app.geometry.panel import cell_polygon, panel_footprint, split_disconnected
from app.models import Issue, LayoutParams, Panel, usable_cell_area_m2
from app.geometry.score import score_layout

INSIDE_EPS = 1e-4


def validate_layout(
    panels: list[Panel],
    params: LayoutParams,
    packable: MultiPolygon,
) -> list[Issue]:
    issues: list[Issue] = []
    clipped = inset_packable(packable, params.edge_inset_mm)
    inward = clipped.buffer(-INSIDE_EPS) if not clipped.is_empty else clipped
    inside = prep(inward) if not inward.is_empty else None
    footprints = [panel_footprint(panel, params) for panel in panels]
    # Cell polygons are only compared for panel pairs whose outlines meet.
    # A gap between outlines means no cell of one can intersect a cell of the other.
    close: dict[int, list[tuple[int, dict[tuple[int, int], object]]]] = {i: [] for i in range(len(panels))}
    other_cells: dict[int, dict[tuple[int, int], object]] = {}

    def cells_of(index: int) -> dict[tuple[int, int], object]:
        cached = other_cells.get(index)
        if cached is None:
            panel = panels[index]
            cached = {(i, j): cell_polygon(panel, i, j, params) for i, j in panel.occupied}
            other_cells[index] = cached
        return cached

    for a_i, footprint in enumerate(footprints):
        if footprint.is_empty:
            continue
        for b_i in range(len(panels)):
            if a_i == b_i or footprints[b_i].is_empty or footprint.disjoint(footprints[b_i]):
                continue
            close[a_i].append((b_i, cells_of(b_i)))

    for index, panel in enumerate(panels):
        if len(split_disconnected(panel)) > 1:
            issues.append(
                Issue(
                    kind="panel_split",
                    message=f"Panel {panel.id} is not 4-connected",
                    panel_ids=[panel.id],
                )
            )
        neighbors = close[index]
        for i, j in panel.occupied:
            poly = cell_polygon(panel, i, j, params)
            if inside is None or not inside.contains(poly):
                issues.append(
                    Issue(
                        kind="outside",
                        message=f"Cell ({i},{j}) in {panel.id} is outside the populate area",
                        panel_ids=[panel.id],
                    )
                )
            if not neighbors:
                continue
            shrunk = poly.buffer(-INSIDE_EPS)
            for other_index, other_polys in neighbors:
                other = panels[other_index]
                for other_poly in other_polys.values():
                    if other_poly.intersects(shrunk):
                        issues.append(
                            Issue(
                                kind="overlap",
                                message=f"Cells in {panel.id} and {other.id} overlap",
                                panel_ids=sorted([panel.id, other.id]),
                            )
                        )

    for a_i, a in enumerate(panels):
        fa = footprints[a_i]
        for b_i, b in enumerate(panels[a_i + 1 :], start=a_i + 1):
            fb = footprints[b_i]
            d = fa.distance(fb)
            if d < params.panel_gap_mm - 1e-9:
                issues.append(
                    Issue(
                        kind="panel_spacing",
                        message=(
                            f"Panels {a.id} and {b.id} are {d:.1f} mm apart; "
                            f"need {params.panel_gap_mm:.1f} mm"
                        ),
                        panel_ids=[a.id, b.id],
                        measured=d,
                        required=params.panel_gap_mm,
                    )
                )

    score = score_layout(panels, params)
    one = usable_cell_area_m2(params)
    if score.delta_m2 < -one:
        issues.append(
            Issue(
                kind="area_target",
                message=f"Usable area {score.active_area_m2:.4f} m² is short of target {params.target_area_m2:.4f} m²",
                panel_ids=[],
                measured=score.active_area_m2,
                required=params.target_area_m2,
            )
        )
    return issues
