from app.geometry.score import rank_key, score_layout
from app.models import DEFAULT_PARAMS, LayoutParams, LayoutScore, Panel


def test_score_two_cells():
    panels = [
        Panel("a", (0.0, 0.0), 0.0, 2, 1, frozenset({(0, 0), (1, 0)})),
    ]
    s = score_layout(panels, DEFAULT_PARAMS)
    assert s.cell_count == 2
    assert abs(s.active_area_m2 - 0.03125) < 1e-12
    assert s.meets_target is False


def test_score_uses_active_not_footprint():
    panels = [Panel("a", (0.0, 0.0), 0.0, 1, 1, frozenset({(0, 0)}))]
    params = LayoutParams(
        cell_w_mm=125,
        cell_h_mm=125,
        active_w_mm=100,
        active_h_mm=80,
        cell_gap_mm=2,
        panel_gap_mm=10,
        max_wide=6,
        max_tall=10,
        target_area_m2=1.0,
    )
    s = score_layout(panels, params)
    assert abs(s.active_area_m2 - 0.008) < 1e-12


def test_rank_prefers_closer_target():
    close = LayoutScore(2, 1, 5.9, -0.1, False, 5.9, 1)
    far = LayoutScore(10, 1, 1.0, -5.0, False, 1.0, 1)
    assert rank_key(close) < rank_key(far)
