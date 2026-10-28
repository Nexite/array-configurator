from shapely.geometry import box

from app.geometry.panel import (
    cell_pitch,
    cell_polygon,
    is_axis_aligned,
    is_rectangular,
    split_disconnected,
)
from app.models import DEFAULT_PARAMS, LayoutParams, Panel, usable_cell_area_m2


def _panel(**kwargs) -> Panel:
    defaults = dict(
        id="p",
        origin=(0.0, 0.0),
        angle_deg=0.0,
        cells_wide=2,
        cells_tall=2,
        occupied=frozenset({(0, 0)}),
    )
    defaults.update(kwargs)
    return Panel(**defaults)


def test_default_params():
    p = DEFAULT_PARAMS
    assert p.cell_w_mm == 125
    assert p.cell_h_mm == 125
    assert p.active_w_mm == 125
    assert p.active_h_mm == 125
    assert p.cell_gap_mm == 2
    assert p.panel_gap_mm == 2
    assert p.edge_inset_mm == 5.0
    assert p.orientation_spread_deg == 90.0
    assert p.custom_active_area is False
    assert p.active_input == "dimensions"
    assert p.max_wide == 24
    assert p.max_tall == 6
    assert p.target_area_m2 == 6.0
    assert p.unit_scale == 1.0


def test_cell_pitch_adds_gap():
    assert cell_pitch(DEFAULT_PARAMS) == (127.0, 127.0)


def test_cell_00_at_origin_unrotated():
    panel = _panel()
    poly = cell_polygon(panel, 0, 0, DEFAULT_PARAMS)
    assert poly.bounds == (0.0, 0.0, 125.0, 125.0)


def test_cell_10_uses_cell_gap():
    panel = _panel(occupied=frozenset({(1, 0)}))
    poly = cell_polygon(panel, 1, 0, DEFAULT_PARAMS)
    minx, miny, maxx, maxy = poly.bounds
    assert minx == 127.0
    assert miny == 0.0
    assert maxx == 252.0
    assert maxy == 125.0


def test_rotated_90_swaps_axes():
    panel = _panel(angle_deg=90.0)
    poly = cell_polygon(panel, 0, 0, DEFAULT_PARAMS)
    assert abs(poly.area - 15625.0) < 1e-6
    c = poly.centroid
    assert abs(c.x - (-62.5)) < 1e-6
    assert abs(c.y - 62.5) < 1e-6


def test_split_l_shape_stays_one_panel():
    panel = _panel(
        cells_wide=2,
        cells_tall=2,
        occupied=frozenset({(0, 0), (1, 0), (0, 1)}),
    )
    parts = split_disconnected(panel)
    assert len(parts) == 1
    assert parts[0].occupied == panel.occupied
    assert parts[0].id == "p_0"


def test_split_two_islands():
    panel = _panel(
        cells_wide=3,
        cells_tall=1,
        occupied=frozenset({(0, 0), (2, 0)}),
    )
    parts = split_disconnected(panel)
    assert len(parts) == 2
    ids = {part.id for part in parts}
    assert ids == {"p_0", "p_1"}
    occupied = {part.occupied for part in parts}
    assert occupied == {frozenset({(0, 0)}), frozenset({(2, 0)})}


def test_is_rectangular_and_axis_aligned():
    full = _panel(occupied=frozenset({(0, 0), (1, 0), (0, 1), (1, 1)}))
    carved = _panel(occupied=frozenset({(0, 0), (1, 0), (0, 1)}))
    assert is_rectangular(full)
    assert not is_rectangular(carved)
    assert is_axis_aligned(full)
    assert not is_axis_aligned(_panel(angle_deg=15.0))


def test_zero_gap_pitch_equals_cell():
    params = LayoutParams(
        cell_w_mm=100,
        cell_h_mm=50,
        active_w_mm=90,
        active_h_mm=45,
        custom_active_area=True,
        cell_gap_mm=0,
        panel_gap_mm=0,
        max_wide=2,
        max_tall=2,
        target_area_m2=1.0,
    )
    assert cell_pitch(params) == (100.0, 50.0)
    assert abs(usable_cell_area_m2(params) - (90 * 45 / 1e6)) < 1e-12
    poly = cell_polygon(_panel(origin=(10.0, 20.0)), 0, 0, params)
    assert poly.equals(box(10.0, 20.0, 110.0, 70.0))
