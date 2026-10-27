from __future__ import annotations

from app.geometry.panel import is_axis_aligned, is_rectangular
from app.models import LayoutParams, LayoutScore, Panel, usable_cell_area_m2


def score_layout(panels: list[Panel], params: LayoutParams) -> LayoutScore:
    cell_count = sum(len(p.occupied) for p in panels)
    a = cell_count * usable_cell_area_m2(params)
    aa_cells = sum(len(p.occupied) for p in panels if is_axis_aligned(p))
    rect_count = sum(1 for p in panels if is_rectangular(p))
    return LayoutScore(
        cell_count=cell_count,
        panel_count=len(panels),
        active_area_m2=a,
        delta_m2=a - params.target_area_m2,
        meets_target=a >= params.target_area_m2,
        axis_aligned_area_m2=aa_cells * usable_cell_area_m2(params),
        rectangular_panel_count=rect_count,
    )


def rank_key(score: LayoutScore) -> tuple:
    return (
        abs(score.delta_m2),
        score.panel_count,
        -score.axis_aligned_area_m2,
        -score.rectangular_panel_count,
        -score.active_area_m2,
    )
