from shapely.geometry import box
from shapely.ops import unary_union

from app.geometry.validate import validate_layout
from app.models import DEFAULT_PARAMS, LayoutParams, Panel


def _p(pid, origin, occupied, angle=0.0, w=2, h=2):
    return Panel(pid, origin, angle, w, h, frozenset(occupied))


def test_cell_outside_square_is_outside_issue():
    packable = box(0, 0, 100, 100)
    panel = _p("a", (200.0, 0.0), {(0, 0)}, w=1, h=1)
    kinds = {i.kind for i in validate_layout([panel], DEFAULT_PARAMS, packable)}
    assert "outside" in kinds


def test_overlapping_cells_issue():
    packable = box(-10, -10, 400, 400)
    a = _p("a", (0.0, 0.0), {(0, 0)}, w=1, h=1)
    b = _p("b", (10.0, 0.0), {(0, 0)}, w=1, h=1)
    kinds = {i.kind for i in validate_layout([a, b], DEFAULT_PARAMS, packable)}
    assert "overlap" in kinds


def test_panel_gap_10_with_6mm_separation_issues():
    packable = box(-10, -10, 800, 400)
    a = _p("a", (0.0, 0.0), {(0, 0)}, w=1, h=1)
    b = _p("b", (131.0, 0.0), {(0, 0)}, w=1, h=1)  # 125 wide + 6 mm gap
    issues = [i for i in validate_layout([a, b], DEFAULT_PARAMS, packable) if i.kind == "panel_spacing"]
    assert issues
    assert abs(issues[0].measured - 6.0) < 0.2
    assert issues[0].required == 10.0


def test_diagonal_panels_true_gap_not_aabb():
    packable = box(-500, -500, 500, 500)
    a = _p("a", (0.0, 0.0), {(0, 0)}, angle=45.0, w=1, h=1)
    # place second cell so AABB is far but shapely distance is ~6
    b = _p("b", (125 + 6, 0.0), {(0, 0)}, angle=45.0, w=1, h=1)
    issues = validate_layout([a, b], DEFAULT_PARAMS, packable)
    # 45° squares: distance along x between origins 131; true gap may still be < 10
    assert any(i.kind == "panel_spacing" for i in issues)


def test_area_issue_when_more_than_one_cell_off():
    packable = box(-10, -10, 400, 400)
    panel = _p("a", (0.0, 0.0), {(0, 0)}, w=1, h=1)
    kinds = {i.kind for i in validate_layout([panel], DEFAULT_PARAMS, packable)}
    assert "area_target" in kinds
    params = LayoutParams(
        cell_w_mm=125,
        cell_h_mm=125,
        active_w_mm=125,
        active_h_mm=125,
        cell_gap_mm=2,
        panel_gap_mm=10,
        max_wide=6,
        max_tall=10,
        target_area_m2=0.015625,
    )
    kinds2 = {i.kind for i in validate_layout([panel], params, packable)}
    assert "area_target" not in kinds2


def test_smaller_active_area_changes_score_threshold():
    packable = box(-10, -10, 400, 400)
    panel = _p("a", (0.0, 0.0), {(0, 0)}, w=1, h=1)
    params = LayoutParams(
        cell_w_mm=125,
        cell_h_mm=125,
        active_w_mm=100,
        active_h_mm=100,
        cell_gap_mm=2,
        panel_gap_mm=10,
        max_wide=6,
        max_tall=10,
        target_area_m2=0.012,
    )
    # one 100×100 cell = 0.01 m²; |0.01-0.012| = 0.002 < one cell (0.01) → no area issue
    kinds = {i.kind for i in validate_layout([panel], params, packable)}
    assert "area_target" not in kinds
