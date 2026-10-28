from __future__ import annotations

from shapely.geometry import MultiPolygon

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

    for panel in panels:
        if len(split_disconnected(panel)) > 1:
            issues.append(
                Issue(
                    kind="panel_split",
                    message=f"Panel {panel.id} is not 4-connected",
                    panel_ids=[panel.id],
                )
            )
        for i, j in panel.occupied:
            poly = cell_polygon(panel, i, j, params)
            if inward.is_empty or not inward.contains(poly):
                issues.append(
                    Issue(
                        kind="outside",
                        message=f"Cell ({i},{j}) in {panel.id} is outside the populate area",
                        panel_ids=[panel.id],
                    )
                )
            for other in panels:
                if other.id == panel.id:
                    continue
                for oi, oj in other.occupied:
                    if cell_polygon(other, oi, oj, params).intersects(poly.buffer(-INSIDE_EPS)):
                        issues.append(
                            Issue(
                                kind="overlap",
                                message=f"Cells in {panel.id} and {other.id} overlap",
                                panel_ids=sorted([panel.id, other.id]),
                            )
                        )

    for a_i, a in enumerate(panels):
        fa = panel_footprint(a, params)
        for b in panels[a_i + 1 :]:
            fb = panel_footprint(b, params)
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
