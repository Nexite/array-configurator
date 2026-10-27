from __future__ import annotations

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from app.models import Region, RegionKind

_CYCLE = {
    RegionKind.POPULATE: RegionKind.KEEP_OUT,
    RegionKind.KEEP_OUT: RegionKind.UNUSED,
    RegionKind.UNUSED: RegionKind.POPULATE,
}


def cycle_kind(kind: RegionKind) -> RegionKind:
    return _CYCLE[kind]


def classify_detected(rings: list[list[tuple[float, float]]]) -> list[Region]:
    polys = [(i, Polygon(r)) for i, r in enumerate(rings) if len(r) >= 4]
    if not polys:
        return []
    polys.sort(key=lambda ip: ip[1].area, reverse=True)
    regions: list[Region] = []
    for n, (src_i, poly) in enumerate(polys):
        kind = RegionKind.POPULATE
        if n > 0:
            for prev in regions:
                if prev.kind == RegionKind.POPULATE and Polygon(prev.points).contains(poly.representative_point()):
                    kind = RegionKind.KEEP_OUT
                    break
        regions.append(
            Region(
                id=f"r{n}",
                points=list(poly.exterior.coords),
                kind=kind,
                source="detected",
            )
        )
    return regions


def packable_polygon(regions: list[Region]) -> MultiPolygon:
    def union_of(kind: RegionKind):
        parts = [
            Polygon(r.points).simplify(2.0, preserve_topology=True)
            for r in regions
            if r.kind == kind and len(r.points) >= 4
        ]
        if not parts:
            return Polygon()
        return unary_union(parts)

    geom = union_of(RegionKind.POPULATE) - union_of(RegionKind.KEEP_OUT) - union_of(RegionKind.UNUSED)
    if geom.is_empty:
        return MultiPolygon()
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    return MultiPolygon([g for g in geom.geoms if g.geom_type == "Polygon"])
