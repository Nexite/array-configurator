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
        custom_active_area=True,
        cell_gap_mm=2,
        panel_gap_mm=10,
        max_wide=6,
        max_tall=10,
        target_area_m2=1.0,
    )
    s = score_layout(panels, params)
    assert abs(s.active_area_m2 - 0.008) < 1e-12


def test_default_usable_tracks_footprint():
    params = LayoutParams(
        cell_w_mm=120,
        cell_h_mm=60,
        active_w_mm=10,
        active_h_mm=10,
        cell_gap_mm=0,
        panel_gap_mm=0,
        max_wide=2,
        max_tall=2,
        target_area_m2=1.0,
    )
    from app.models import usable_cell_area_m2

    assert abs(usable_cell_area_m2(params) - (120 * 60 / 1e6)) < 1e-12


def test_custom_usable_area_mm2():
    from app.models import usable_cell_area_m2

    params = LayoutParams(
        cell_w_mm=125,
        cell_h_mm=125,
        active_w_mm=125,
        active_h_mm=125,
        cell_gap_mm=2,
        panel_gap_mm=10,
        max_wide=6,
        max_tall=10,
        target_area_m2=1.0,
        custom_active_area=True,
        active_input="area",
        active_mm2=8000,
    )
    assert abs(usable_cell_area_m2(params) - 0.008) < 1e-12


def test_rank_prefers_closer_target():
    close = LayoutScore(2, 1, 5.9, -0.1, False, 5.9, 1)
    far = LayoutScore(10, 1, 1.0, -5.0, False, 1.0, 1)
    assert rank_key(close) < rank_key(far)


def test_overpack_beats_a_shortfall():
    over = LayoutScore(400, 6, 6.4, 0.4, True, 6.4, 6)
    under = LayoutScore(340, 3, 5.7, -0.3, False, 5.7, 3)
    assert rank_key(over) < rank_key(under)
