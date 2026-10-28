from app.geometry.regions import classify_detected, packable_polygon
from app.models import Region, RegionKind


def _square(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def test_classify_shell_and_hole():
    regions = classify_detected([_square(0, 0, 100, 100), _square(40, 40, 60, 60)])
    kinds = {r.id: r.kind for r in regions}
    assert RegionKind.POPULATE in kinds.values()
    assert RegionKind.KEEP_OUT in kinds.values()
    outer = next(r for r in regions if r.kind == RegionKind.POPULATE)
    inner = next(r for r in regions if r.kind == RegionKind.KEEP_OUT)
    assert packable_polygon([outer, inner]).area == 9600


def test_packable_subtracts_keepout():
    regions = [
        Region("r0", _square(0, 0, 100, 100), RegionKind.POPULATE, "detected"),
        Region("r1", _square(40, 40, 60, 60), RegionKind.KEEP_OUT, "detected"),
    ]
    assert abs(packable_polygon(regions).area - 9600) < 1e-6


def test_unused_also_empty():
    regions = [
        Region("r0", _square(0, 0, 100, 100), RegionKind.POPULATE, "detected"),
        Region("r1", _square(40, 40, 60, 60), RegionKind.UNUSED, "detected"),
    ]
    assert abs(packable_polygon(regions).area - 9600) < 1e-6


def test_disjoint_second_island_starts_populate():
    regions = classify_detected([_square(0, 0, 10, 10), _square(20, 0, 30, 10)])
    assert all(r.kind == RegionKind.POPULATE for r in regions)
