from dataclasses import replace

from shapely.affinity import rotate
from shapely.geometry import box
from shapely.ops import unary_union

from app.geometry.align import dominant_axis_deg, long_axis_deg
from app.geometry.conventional import (
    _cell_can_fit,
    _pack_oriented,
    _reframe_swapped_panel,
    _secondary_angles,
    axis_cell_caps,
    merge_panels,
    pack_conventional,
)
from app.geometry.pack import circular_angle_delta, pack_layouts
from app.geometry.panel import cell_polygon, is_rectangular
from app.models import LayoutParams, Panel

def _params(**kwargs):
    base = dict(
        cell_w_mm=182,
        cell_h_mm=96,
        active_w_mm=182,
        active_h_mm=96,
        cell_gap_mm=2,
        panel_gap_mm=10,
        max_wide=24,
        max_tall=6,
        target_area_m2=6.0,
    )
    base.update(kwargs)
    return LayoutParams(**base)


def _axis_delta(axis: float, angle: float) -> float:
    return min(
        circular_angle_delta(axis, angle),
        circular_angle_delta(axis + 90.0, angle),
    )


def _spans(panel, params, long_axis: float) -> tuple[int, int]:
    """Cells along the long-capped edge and the short-capped edge."""
    cap_w, cap_h = axis_cell_caps(params, panel.angle_deg, long_axis)
    along_w = panel.cells_wide
    along_h = panel.cells_tall
    if cap_w == params.max_tall and cap_h == params.max_wide:
        return along_w, along_h
    if cap_h == params.max_tall and cap_w == params.max_wide:
        return along_h, along_w
    return max(along_w, along_h), min(along_w, along_h)


def test_dominant_axis_follows_rotated_rectangle():
    geom = rotate(box(0, 0, 2000, 800), 17, origin=(0, 0), use_radians=False)
    assert _axis_delta(17, dominant_axis_deg(geom)) < 2.0


def test_long_axis_is_the_longer_side():
    tall = long_axis_deg(box(0, 0, 400, 2000))
    wide = long_axis_deg(box(0, 0, 2000, 400))
    assert abs(tall - 90.0) < 1.0
    assert min(wide, 180.0 - wide) < 1.0


def test_cap_is_24_across_the_short_side_and_6_along_the_long_side():
    geom = box(0, 0, 800, 3000)
    params = _params(
        cell_w_mm=100,
        cell_h_mm=100,
        active_w_mm=100,
        active_h_mm=100,
        cell_gap_mm=0,
        panel_gap_mm=0,
    )
    long_axis = long_axis_deg(geom)
    layouts = pack_conventional(geom, params)
    assert layouts
    for lay in layouts:
        assert lay.score.cell_count == 240
        for panel in lay.panels:
            along_long, along_short = _spans(panel, params, long_axis)
            assert along_long <= 6
            assert along_short <= 24
            assert is_rectangular(panel)


def test_overpack_fills_past_a_tiny_target():
    layouts = pack_conventional(box(0, 0, 500, 200), _params(cell_w_mm=100, cell_h_mm=100, active_w_mm=100, active_h_mm=100, cell_gap_mm=0, panel_gap_mm=0, target_area_m2=0.01))
    best = max(layouts, key=lambda lay: lay.score.active_area_m2)
    assert best.score.cell_count == 10
    assert best.score.active_area_m2 > 0.01
    assert all(is_rectangular(p) for p in best.panels)


def test_row_extension_stays_on_the_same_panel():
    notch = box(0, 0, 500, 200).difference(box(400, 100, 500, 200))
    params = _params(
        cell_w_mm=100,
        cell_h_mm=100,
        active_w_mm=100,
        active_h_mm=100,
        cell_gap_mm=0,
        panel_gap_mm=10,
    )
    lay = pack_conventional(notch, params)[0]
    assert lay.score.cell_count == 9
    assert len(lay.panels) == 1
    assert not is_rectangular(lay.panels[0])


def _solid(pid: str, origin, angle: float, w: int, h: int) -> Panel:
    return Panel(pid, origin, angle, w, h, frozenset((i, j) for i in range(w) for j in range(h)))


def test_merge_snaps_a_near_grid_neighbor_when_rules_hold():
    packable = box(-5, -5, 500, 250)
    params = _params(cell_w_mm=100, cell_h_mm=100, active_w_mm=100, active_h_mm=100, cell_gap_mm=0, panel_gap_mm=10)
    host = _solid("a", (0.0, 0.0), 0.0, 2, 2)
    guest = _solid("b", (208.0, 0.0), 0.0, 1, 2)
    merged = merge_panels([host, guest], params, packable, 0.0)
    assert len(merged) == 1
    assert len(merged[0].occupied) == 6
    assert is_rectangular(merged[0])


def test_long_cell_edge_is_capped_even_across_the_shell():
    params = _params(cell_gap_mm=2, panel_gap_mm=2)
    lay = pack_conventional(box(0, 0, 2200, 700), params)[0]
    assert lay.score.cell_count > 0
    for panel in lay.panels:
        assert panel.cells_wide <= params.max_tall
        assert panel.cells_tall <= params.max_wide


def test_merge_rejects_extra_cells_along_the_long_edge():
    packable = box(-5, -5, 2500, 400)
    params = _params(cell_gap_mm=2, panel_gap_mm=2)
    host = _solid("a", (0.0, 0.0), 0.0, 6, 2)
    guest = _solid("b", (6 * 184.0 + 2.0, 0.0), 0.0, 3, 2)
    merged = merge_panels([host, guest], params, packable, 0.0)
    assert len(merged) == 2
    assert all(panel.cells_wide <= 6 for panel in merged)


def test_merge_leaves_panels_that_would_break_the_long_side_cap():
    packable = box(-20, -20, 200, 1400)
    params = _params(cell_w_mm=100, cell_h_mm=100, active_w_mm=100, active_h_mm=100, cell_gap_mm=0, panel_gap_mm=10, max_wide=24, max_tall=6)
    host = _solid("a", (0.0, 0.0), 90.0, 6, 1)
    guest = _solid("b", (0.0, 608.0), 90.0, 6, 1)
    merged = merge_panels([host, guest], params, packable, 90.0)
    assert len(merged) == 2


def test_secondary_angles_step_by_five_degrees():
    angles = _secondary_angles([0.0, 90.0])
    assert 0.0 not in angles and 90.0 not in angles
    assert 5.0 in angles and 10.0 in angles and 45.0 in angles
    assert all(abs(b - a) >= 5 - 1e-9 for a, b in zip(angles, angles[1:]))


def test_narrow_pocket_cannot_hold_a_cell():
    assert not _cell_can_fit(box(0, 0, 800, 20), _params())
    assert _cell_can_fit(box(0, 0, 400, 200), _params())


def test_swapped_panel_draws_the_same_cells_in_the_user_frame():
    user = _params(cell_gap_mm=2, panel_gap_mm=2)
    swapped = replace(user, cell_w_mm=user.cell_h_mm, cell_h_mm=user.cell_w_mm)
    panel = _solid("p", (10.0, 20.0), 15.0, 3, 2)
    framed = _reframe_swapped_panel(panel, user)
    before = unary_union([cell_polygon(panel, i, j, swapped) for i, j in panel.occupied])
    after = unary_union([cell_polygon(framed, i, j, user) for i, j in framed.occupied])
    assert before.symmetric_difference(after).area < 1e-4
    assert framed.cells_wide == 2 and framed.cells_tall == 3


def test_either_width_order_keeps_the_fuller_pack():
    geom = box(0, 0, 1600, 420).difference(box(900, 0, 1600, 200))
    wide = _params(cell_gap_mm=2, panel_gap_mm=2)
    tall = replace(wide, cell_w_mm=wide.cell_h_mm, cell_h_mm=wide.cell_w_mm, active_w_mm=wide.cell_h_mm, active_h_mm=wide.cell_w_mm)
    entered = sum(len(panel.occupied) for panel in _pack_oriented(geom, wide))
    exchanged = sum(len(panel.occupied) for panel in _pack_oriented(geom, tall))
    fuller = max(entered, exchanged)
    assert entered != exchanged
    for params in (wide, tall):
        lay = pack_conventional(geom, params)[0]
        assert lay.score.cell_count == fuller
        assert lay.params.cell_w_mm == params.cell_w_mm
        assert lay.params.cell_h_mm == params.cell_h_mm


def test_pack_layouts_includes_aligned_family():
    families = {lay.family for lay in pack_layouts(box(0, 0, 400, 200), _params(cell_w_mm=100, cell_h_mm=100, active_w_mm=100, active_h_mm=100, max_wide=2, max_tall=2))}
    assert "aligned" in families
