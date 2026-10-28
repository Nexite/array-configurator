from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class RegionKind(str, Enum):
    POPULATE = "populate"
    KEEP_OUT = "keep_out"
    UNUSED = "unused"


@dataclass(frozen=True)
class LayoutParams:
    cell_w_mm: float
    cell_h_mm: float
    active_w_mm: float
    active_h_mm: float
    cell_gap_mm: float
    panel_gap_mm: float
    max_wide: int
    max_tall: int
    target_area_m2: float
    unit_scale: float = 1.0
    edge_inset_mm: float = 0.0


DEFAULT_PARAMS = LayoutParams(
    cell_w_mm=125,
    cell_h_mm=125,
    active_w_mm=125,
    active_h_mm=125,
    cell_gap_mm=2,
    panel_gap_mm=10,
    max_wide=6,
    max_tall=10,
    target_area_m2=6.0,
    unit_scale=1.0,
    edge_inset_mm=0.0,
)


def usable_cell_area_m2(params: LayoutParams) -> float:
    return params.active_w_mm * params.active_h_mm / 1e6


@dataclass
class Region:
    id: str
    points: list[tuple[float, float]]
    kind: RegionKind
    source: Literal["detected", "drawn"]


@dataclass(frozen=True)
class Panel:
    id: str
    origin: tuple[float, float]
    angle_deg: float
    cells_wide: int
    cells_tall: int
    occupied: frozenset[tuple[int, int]]


@dataclass
class Issue:
    kind: str
    message: str
    panel_ids: list[str] = field(default_factory=list)
    measured: float | None = None
    required: float | None = None


@dataclass
class LayoutScore:
    cell_count: int
    panel_count: int
    active_area_m2: float
    delta_m2: float
    meets_target: bool
    axis_aligned_area_m2: float
    rectangular_panel_count: int


@dataclass
class Layout:
    id: str
    params: LayoutParams
    panels: list[Panel]
    score: LayoutScore | None
    family: str
