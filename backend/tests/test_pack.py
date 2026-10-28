from shapely.geometry import box

from app.geometry.pack import pack_layouts
from app.geometry.panel import cell_polygon
from app.models import LayoutParams


def _params(**kwargs):
    base = dict(
        cell_w_mm=125,
        cell_h_mm=125,
        active_w_mm=125,
        active_h_mm=125,
        cell_gap_mm=2,
        panel_gap_mm=0,
        max_wide=2,
        max_tall=1,
        target_area_m2=6.0,
    )
    base.update(kwargs)
    return LayoutParams(**base)


def test_rect_box_fits_exact_2x1():
    packable = box(0, 0, 252, 125)
    layouts = pack_layouts(packable, _params())
    assert layouts
    best = max(layouts, key=lambda l: l.score.cell_count)
    assert best.score.cell_count == 2
    assert best.family == "aligned"


def test_never_places_outside():
    packable = box(0, 0, 252, 125)
    params = _params()
    for lay in pack_layouts(packable, params):
        for panel in lay.panels:
            for i, j in panel.occupied:
                assert packable.buffer(1e-3).contains(cell_polygon(panel, i, j, params))


def test_only_aligned_layout_is_calculated():
    packable = box(0, 0, 252, 125)
    families = {l.family for l in pack_layouts(packable, _params())}
    assert families == {"aligned"}


def test_target_does_not_stop_early():
    packable = box(0, 0, 252, 125)
    layouts = pack_layouts(packable, _params(target_area_m2=0.001))
    assert max(l.score.cell_count for l in layouts) == 2


def test_fills_large_rectangle_with_multiple_panels():
    packable = box(0, 0, 800, 400)
    layouts = pack_layouts(packable, _params(max_wide=2, max_tall=1, panel_gap_mm=10))
    best = max(layouts, key=lambda l: l.score.cell_count)
    assert best.score.panel_count > 1
    assert best.score.cell_count > 2


def test_picks_better_cell_rotation_for_rectangles():
    packable = box(0, 0, 310, 130)
    params = _params(
        cell_w_mm=120,
        cell_h_mm=60,
        active_w_mm=120,
        active_h_mm=60,
        cell_gap_mm=0,
        panel_gap_mm=0,
        max_wide=6,
        max_tall=6,
    )
    layouts = pack_layouts(packable, params)
    assert max(l.score.cell_count for l in layouts) >= 5


def test_edge_inset_keeps_cells_off_boundary():
    packable = box(0, 0, 500, 300)
    params = _params(
        cell_w_mm=100,
        cell_h_mm=100,
        active_w_mm=100,
        active_h_mm=100,
        cell_gap_mm=0,
        panel_gap_mm=0,
        max_wide=2,
        max_tall=1,
        edge_inset_mm=20,
    )
    layouts = pack_layouts(packable, params)
    best = max(layouts, key=lambda l: l.score.cell_count)
    assert best.score.cell_count >= 2
    inset = packable.buffer(-20 + 1e-3)
    for panel in best.panels:
        for i, j in panel.occupied:
            assert inset.covers(cell_polygon(panel, i, j, params))
