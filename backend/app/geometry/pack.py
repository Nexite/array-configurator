from __future__ import annotations

from shapely.geometry import MultiPolygon

from app.geometry.conventional import pack_conventional
from app.models import Layout, LayoutParams


def _as_multi(geom) -> MultiPolygon:
    if geom is None or geom.is_empty:
        return MultiPolygon()
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    return MultiPolygon([g for g in geom.geoms if g.geom_type == "Polygon"])


def inset_packable(packable, inset_mm: float) -> MultiPolygon:
    if inset_mm <= 0 or packable.is_empty:
        return _as_multi(packable)
    return _as_multi(packable.buffer(-inset_mm))


def pack_layouts(packable: MultiPolygon, params: LayoutParams) -> list[Layout]:
    packable = inset_packable(packable, params.edge_inset_mm)
    if packable.is_empty:
        return []
    layouts = list(pack_conventional(packable, params))
    for i, lay in enumerate(layouts):
        lay.id = f"L{i}"
    return layouts
