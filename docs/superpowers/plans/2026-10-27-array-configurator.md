# Array Configurator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dockerized web app that imports a vector outline, lets the user pick populate regions, auto-packs solar panels (90° first, then irregular and diagonal), then edits the layout by hand with live spacing and area issues.

**Architecture:** Python FastAPI owns import, region compose, packing, and file export. The React canvas owns region picking, drag-edit, undo, and live validation (TypeScript ports of `cell_polygon` / `validate_layout` / `score_layout` against the same JSON fixtures). One multi-stage image serves the built UI from the API.

**Tech Stack:** Python 3.12, FastAPI, Shapely, ezdxf, svgelements, pymupdf, pytest; Vite + React + TypeScript; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-27-array-configurator-design.md`

## Global Constraints

- Default sample is `samples/TOPSHELL.DXF` (mm). Canopy is already removed; do not flatten again.
- Default form values: cell 125×125 mm, cell gap 2 mm, panel gap 10 mm, max 6×10 cells, target 6.0 m², unit scale 1.0.
- Active area `A = n_cells × cell_w_mm × cell_h_mm / 1e6` m². Gaps do not count.
- Allowed panel angles: `0, 15, …, 165` degrees, plus long-edge angles from the populate outline at pack time. 90° pass uses only `0` and `90`.
- Snap while dragging: 1 mm. Close-path snap on import: 2 mm. Containment epsilon: `1e-4` mm (float only; cells still must be fully inside).
- Upload cap 25 MiB. Pack timeout 20 s. Return at most 12 distinct layouts.
- Raster uploads (`png`, `jpg`, `jpeg`, `gif`, `webp`, `tif`, `bmp`) raise `UnsupportedFormatError` with message `Raster files are not supported. Use a vector file.`
- DWG without a converter raises `UnsupportedFormatError` with message `Convert DWG to DXF and upload that.`
- No auth. One Compose service. Dark technical UI.

## File map

- `backend/app/models.py` — `LayoutParams`, `Region`, `Panel`, `Layout`, `Issue`, `LayoutScore`
- `backend/app/geometry/import_vector.py` — bytes → closed polygons
- `backend/app/geometry/regions.py` — kinds + packable multipolygon
- `backend/app/geometry/panel.py` — local grid, world cell polygons, split-on-carve
- `backend/app/geometry/validate.py` — live issue list
- `backend/app/geometry/score.py` — area / rank keys
- `backend/app/geometry/pack.py` — 90° rect, 90° irregular, diagonal fill, rank
- `backend/app/geometry/export.py` — SVG, DXF, JSON
- `backend/app/main.py` — FastAPI + static UI
- `backend/tests/fixtures/validate_cases.json` — shared Python/TS cases
- `frontend/src/types.ts`, `frontend/src/geom/{panel,validate,score}.ts` — editor math
- `frontend/src/state/store.ts` — layout, dirty flag, undo
- `frontend/src/ui/*` — page, canvas, inspector, issues, gallery
- `samples/TOPSHELL.DXF`, `samples/rectangle.svg`
- `Dockerfile`, `docker-compose.yml`

## Review Focus

- Almost-closed DXF polylines (gap ≤ 2 mm) become a region; a 3 mm gap stays open and is ignored.
- Two diagonal panels whose AABB gap is > 10 mm but true gap is 6 mm still raise `panel_spacing`.
- Regenerating or switching a gallery card while `dirty === true` does not replace the layout without confirm.
- Toggling a cell that splits a panel yields two panels (4-connected components) and an `panel_split` issue once.
- A `.png` upload returns HTTP 400 with the raster error string, never an empty region list.

---

### Task 1: Domain model and cell world geometry

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/geometry/panel.py`
- Create: `backend/app/geometry/__init__.py`
- Create: `backend/app/__init__.py`
- Create: `backend/requirements.txt` (`fastapi`, `uvicorn`, `shapely`, `ezdxf`, `svgelements`, `pymupdf`, `pydantic`, `pytest`)
- Create: `backend/tests/test_panel.py`
- Create: `samples/rectangle.svg` (1000×500 mm rectangle, units mm)
- Copy: `samples/TOPSHELL.DXF` from `/Users/nikhil/Documents/Solar Car Blender Projects/array_extract/TOPSHELL.DXF`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `LayoutParams(cell_w_mm, cell_h_mm, cell_gap_mm, panel_gap_mm, max_wide, max_tall, target_area_m2, unit_scale=1.0)`
  - `DEFAULT_PARAMS` with the Global Constraints defaults
  - `RegionKind`: `"populate" | "keep_out" | "unused"`
  - `Region(id: str, points: list[tuple[float,float]], kind: RegionKind, source: Literal["detected","drawn"])`
  - `Panel(id: str, origin: tuple[float,float], angle_deg: float, cells_wide: int, cells_tall: int, occupied: frozenset[tuple[int,int]])`
  - `cell_pitch(params) -> tuple[float,float]` → `(cell_w+cell_gap, cell_h+cell_gap)`
  - `cell_polygon(panel, i, j, params) -> shapely.Polygon` — min-corner of cell `(0,0)` is `origin`, +x along `angle_deg`, size `cell_w × cell_h` (gap is between cells, not inside the cell)
  - `panel_footprint(panel, params) -> shapely.Polygon` — union of occupied cell polygons, buffered by `0`
  - `split_disconnected(panel) -> list[Panel]` — one panel per 4-connected component; ids `f"{panel.id}_{n}"`
  - `is_rectangular(panel) -> bool` — occupied == full `cells_wide × cells_tall` rectangle
  - `is_axis_aligned(panel) -> bool` — `angle_deg % 90 == 0`

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_panel.py`

```python
def test_cell_00_at_origin_unrotated():
    # 125×125 cell at (0,0), angle 0 → bounds (0,0)-(125,125)
def test_cell_10_uses_cell_gap():
    # occupied (1,0) min-corner at x=127 (125+2)
def test_rotated_90_swaps_axes():
    # angle 90, cell (0,0) occupies (0,0) to (-125, 125) in world? use origin (0,0) and assert area 15625 and centroid
def test_split_l_shape_stays_one_panel():
    # occupied {(0,0),(1,0),(0,1)} → one panel
def test_split_two_islands():
    # occupied {(0,0),(2,0)} → two panels
```

- [ ] **Step 2: Run** `cd backend && pytest tests/test_panel.py -v`  
  Expected: FAIL, import error

- [ ] **Step 3: Implement the signatures above.** Local cell `(i,j)` min-corner in panel space is `(i*pitch_x, j*pitch_y)`. Rotate by `angle_deg` about `origin`, then translate by `origin`.

- [ ] **Step 4: Run** `pytest tests/test_panel.py -v`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: add panel grid and world cell polygons`

---

### Task 2: Vector import

**Files:**
- Create: `backend/app/geometry/import_vector.py`
- Create: `backend/tests/test_import_vector.py`
- Create: `backend/tests/fixtures/open_gap.dxf` (write in the test via ezdxf)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class UnsupportedFormatError(ValueError)`
  - `import_vector(data: bytes, filename: str, unit_scale: float = 1.0) -> list[list[tuple[float,float]]]`
  - Returns closed rings (first point == last optional). Empty list if no closed geometry.
  - Extensions: `.dxf` (ezdxf), `.svg` (svgelements), `.pdf`/`.ai`/`.eps` (pymupdf vector paths), `.plt`/`.hpgl` (simple PA/PD parser). `.dwg` → `UnsupportedFormatError` with the Global Constraints message unless `shutil.which("dwg2dxf")` exists, then convert to a temp DXF.

- [ ] **Step 1: Write tests** in `backend/tests/test_import_vector.py`

```python
def test_rectangle_svg_area():
    # samples/rectangle.svg → one ring, shapely area == 500_000 (1000×500)
def test_dxf_lwpolyline_closed():
    # build a 100×50 closed LWPOLYLINE in-memory → area 5000
def test_almost_closed_gap_2mm_closes():
    # open polyline, endpoints 2.0 mm apart → one ring
def test_gap_3mm_ignored():
    # endpoints 3.0 mm apart → []
def test_png_rejected():
    # filename "x.png", data=b"x" → UnsupportedFormatError, raster message
```

- [ ] **Step 2: Run** `pytest tests/test_import_vector.py -v`  
  Expected: FAIL

- [ ] **Step 3: Implement `import_vector`.** Apply `unit_scale` to all coordinates. Close rings when endpoint distance ≤ 2.0 mm.

- [ ] **Step 4: Run** `pytest tests/test_import_vector.py -v`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: import common vector outlines to closed rings`

---

### Task 3: Region kinds and packable polygon

**Files:**
- Create: `backend/app/geometry/regions.py`
- Create: `backend/tests/test_regions.py`

**Interfaces:**
- Consumes: `Region`, `RegionKind`
- Produces:
  - `classify_detected(rings) -> list[Region]` — largest-area ring `populate`; any ring whose representative point is inside it `keep_out`; remaining rings `populate` (disjoint islands). Ids `r0`, `r1`, …
  - `packable_polygon(regions: list[Region]) -> shapely.MultiPolygon` — `union(populate) - union(keep_out) - union(unused)`
  - `cycle_kind(kind) -> RegionKind` — populate → keep_out → unused → populate

- [ ] **Step 1: Write tests**

```python
def test_classify_shell_and_hole():
    # outer 0..100 square, inner 40..60 square → kinds populate, keep_out
def test_packable_subtracts_keepout():
    # area 10000 - 400 = 9600
def test_unused_also_empty():
    # mark inner unused; area still 9600
def test_disjoint_second_island_starts_populate():
def test_cycle_kind_order():
```

- [ ] **Step 2: Run** `pytest tests/test_regions.py -v`  
  Expected: FAIL

- [ ] **Step 3: Implement the three functions.**

- [ ] **Step 4: Run** `pytest tests/test_regions.py -v`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: compose packable region from user kinds`

---

### Task 4: Validate and score

**Files:**
- Create: `backend/app/geometry/validate.py`
- Create: `backend/app/geometry/score.py`
- Create: `backend/tests/test_validate.py`
- Create: `backend/tests/test_score.py`
- Create: `backend/tests/fixtures/validate_cases.json`

**Interfaces:**
- Consumes: `Panel`, `LayoutParams`, `packable_polygon`, `cell_polygon`, `panel_footprint`, `split_disconnected`
- Produces:
  - `Issue(kind: str, message: str, panel_ids: list[str], measured: float | None, required: float | None)`
  - `validate_layout(panels, params, packable) -> list[Issue]`
    - kinds: `outside`, `overlap`, `panel_spacing`, `cell_grid`, `area_target`, `panel_split`
    - `panel_spacing`: shapely `distance` between `panel_footprint`s < `panel_gap_mm` (strict). Message: `Panels {a} and {b} are {measured:.1f} mm apart; need {required:.1f} mm`
    - `area_target` only when `|A - target| > cell_w_mm * cell_h_mm / 1e6`
  - `score_layout(panels, params) -> LayoutScore` with `cell_count`, `panel_count`, `active_area_m2`, `delta_m2` (`A - target`), `meets_target` (`A >= target`), `axis_aligned_area_m2`, `rectangular_panel_count`
  - `rank_key(score) -> tuple` — `(abs(delta_m2), panel_count, -axis_aligned_area_m2, -rectangular_panel_count, -active_area_m2)`

- [ ] **Step 1: Write tests** including Review Focus cases

```python
def test_cell_outside_square_is_outside_issue():
def test_overlapping_cells_issue():
def test_panel_gap_10_with_6mm_separation_issues():
def test_diagonal_panels_true_gap_not_aabb():
    # two 125×125 cells, angles 45 and -45, placed so AABB gap > 10 but shapely distance == 6
def test_area_issue_when_more_than_one_cell_off():
    # 1 cell, target 6.0 → issue; 1 cell, target 0.015625 → no area issue
def test_score_two_cells():
    # A == 2 * 125 * 125 / 1e6 == 0.03125
def test_rank_prefers_closer_target():
```

Write the diagonal-gap and outside cases into `validate_cases.json` as `{panels, params, packable_wkt, expect_kinds}` so Task 11 can reuse them.

- [ ] **Step 2: Run** `pytest tests/test_validate.py tests/test_score.py -v`  
  Expected: FAIL

- [ ] **Step 3: Implement `validate_layout` and `score_layout`.** Use footprint buffers only for distance, not for outline keep-out.

- [ ] **Step 4: Run** `pytest tests/test_validate.py tests/test_score.py -v`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: validate spacing and score target area`

---

### Task 5: Auto-pack and rank

**Files:**
- Create: `backend/app/geometry/pack.py`
- Create: `backend/tests/test_pack.py`

**Interfaces:**
- Consumes: `LayoutParams`, `cell_polygon`, `score_layout`, `rank_key`, `is_rectangular`, `is_axis_aligned`
- Produces:
  - `pack_layouts(packable, params, edge_angles_deg: list[float] | None = None) -> list[Layout]`
  - `Layout(id: str, params, panels: list[Panel], score: LayoutScore, family: Literal["rect90","irregular90","diagonal"])`
  - Always runs the 90° rectangle family first. Then 90° irregular (carve cells that would leave `packable`). Then diagonal fill of leftovers (and 1–2 extra full diagonal candidates). Never skip the 90° pass.
  - At most 12 layouts, unique by rounded cell-count + sorted occupied hashes. Sorted by `rank_key`.
  - Heuristic (locked): sliding origin offsets `(0, 0.25, 0.5, 0.75) × pitch` on both axes; for each origin try bound sizes from `max_wide×max_tall` down to `1×1` (and the 90° swap). Place a panel if every occupied cell is inside `packable` by `contains` with `1e-4` buffer inward. Greedy: place largest remaining, then fill leftovers. Irregular: start from the full bound and drop cells whose polygon is not contained; keep the largest 4-connected remainder. Diagonal: same at each allowed angle including `edge_angles_deg`. Deterministic; no RNG.

- [ ] **Step 1: Write tests**

```python
def test_rect_box_fits_exact_2x1():
    # packable = box(0,0,252,125); 125 cell, gap 2, max 2×1 → one 2×1 panel, 2 cells
def test_never_places_outside():
    # every cell_polygon contained in packable
def test_irregular_fills_l_better_than_rect_only():
    # L made of 100×100 boxes: (0,0)-(200,100) U (0,100)-(100,200); cell 100, gap 0, max 2×2
    # rect-only family ≤ 2 cells; irregular family has a 3-cell L panel
def test_90_pass_present_even_if_diagonal_wins():
    # result families include "rect90"
def test_caps_at_12():
def test_target_does_not_stop_early():
    # tiny target 0.001 still packs the full 2-cell box
```

- [ ] **Step 2: Run** `pytest tests/test_pack.py -v`  
  Expected: FAIL

- [ ] **Step 3: Implement `pack_layouts`** with the heuristic above.

- [ ] **Step 4: Run** `pytest tests/test_pack.py -v`  
  Expected: PASS. Also `pytest tests/ -v` still green.

- [ ] **Step 5: Commit** `feat: pack 90-degree, irregular, and diagonal layouts`

---

### Task 6: Export and FastAPI

**Files:**
- Create: `backend/app/geometry/export.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_export.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: all prior geometry
- Produces:
  - `export_svg(layout, regions) -> str`
  - `export_dxf(layout, regions) -> bytes` — layers `OUTLINE`, `PANELS`, `CELLS`, units = input mm
  - `export_json(layout, regions) -> dict` — round-trips through `layout_from_json`
  - App routes:
    - `POST /api/import` multipart `file` + form `unit_scale` → `{regions, bounds}`
    - `GET /api/sample/topshell` → same as import of `samples/TOPSHELL.DXF`
    - `POST /api/pack` JSON `{regions, params}` → `{layouts}` (timeout 20 s → 504)
    - `POST /api/validate` JSON `{regions, params, panels}` → `{issues, score}`
    - `POST /api/export/{fmt}` `fmt in svg|dxf|json` → file
    - reject > 25 MiB with 413
    - `UnsupportedFormatError` → 400 `{detail: str}`

- [ ] **Step 1: Write tests** (`TestClient`)

```python
def test_import_rectangle_svg():
def test_import_png_400():
def test_sample_topshell_has_populate_region():
def test_pack_then_validate_roundtrip():
def test_export_json_roundtrip_same_cell_count():
def test_export_dxf_has_cells_layer():
```

- [ ] **Step 2: Run** `pytest tests/test_export.py tests/test_api.py -v`  
  Expected: FAIL

- [ ] **Step 3: Implement export + `create_app()`. Serve `backend/app/static/` if present (empty until Task 10). CORS not required in Compose.

- [ ] **Step 4: Run** `pytest tests/test_export.py tests/test_api.py -v`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: add import, pack, validate, and export API`

---

### Task 7: Frontend geometry port and app shell

**Files:**
- Create: `frontend/package.json` (vite, react, react-dom, typescript)
- Create: `frontend/src/types.ts` — mirror `LayoutParams`, `Region`, `Panel`, `Issue`, `LayoutScore`
- Create: `frontend/src/geom/panel.ts` — `cellPolygon`, `splitDisconnected`, `isRectangular`
- Create: `frontend/src/geom/validate.ts` — `validateLayout`
- Create: `frontend/src/geom/score.ts` — `scoreLayout`
- Create: `frontend/src/geom/validate.test.ts`
- Create: `frontend/src/api.ts` — `importFile`, `loadSample`, `pack`, `exportFile`
- Create: `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/index.html`
- Create: `frontend/src/styles.css` — dark technical (bg `#121418`, accent `#3d8ef0`, danger `#e05a4f`)

**Interfaces:**
- Consumes: `backend/tests/fixtures/validate_cases.json`
- Produces: TS functions with the same results as Python on those fixtures (kinds set match; measured within 0.05 mm)

- [ ] **Step 1: Write** `validate.test.ts` that loads `validate_cases.json` and asserts `expect(issues.map(i => i.kind).sort()).toEqual(expect_kinds.sort())`.

- [ ] **Step 2: Run** `cd frontend && npx vitest run src/geom/validate.test.ts`  
  Expected: FAIL

- [ ] **Step 3: Port the math.** Use a small polygon library (`polygon-clipping` or hand-rolled SAT for rects + shapely-equivalent via `polygon-clipping`). Containment and distance must match the fixture kinds, not pixel heuristics.

- [ ] **Step 4: Run** `npx vitest run`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: port validation to the editor client`

---

### Task 8: Canvas — regions, generate, gallery, editor

**Files:**
- Create: `frontend/src/state/store.ts`
- Create: `frontend/src/ui/Canvas.tsx`
- Create: `frontend/src/ui/ParamsForm.tsx`
- Create: `frontend/src/ui/Gallery.tsx`
- Create: `frontend/src/ui/IssuesList.tsx`
- Create: `frontend/src/ui/StatusStrip.tsx`
- Create: `frontend/src/ui/Inspector.tsx`
- Create: `frontend/src/App.tsx` (wire)
- Create: `frontend/src/state/store.test.ts`

**Interfaces:**
- Consumes: Task 7 types + API
- Produces store API:
  - `loadRegions(regions)`, `cycleRegion(id)`, `addDrawnRegion(points, kind)`
  - `generate()` → POST `/api/pack`, set `layouts`, `active = layouts[0]`, `dirty = false`
  - `selectGallery(id)` — if `dirty`, set `pendingGalleryId` and do not swap until `confirmReplace()`
  - `movePanel(id, origin)`, `rotatePanel(id, angle)`, `resizeBound(id, w, h)` (grow adds cells on the new fringe; shrink drops occupied outside the bound; never refill a carve into a rectangle)
  - `toggleCell(panelId, i, j)` — off last cell deletes panel; if disconnected, replace with `splitDisconnected` and push issue notice `panel_split`
  - `nudgeCell(panelId, i, j, di, dj)` — stays in panel if integer step; world drag that leaves the 0.5-pitch neighborhood of any grid slot detaches as new 1×1 panel
  - `addPanelAt(world, angle=0)`, `deletePanel(id)`
  - `undo()`, `redo()` — snapshot stack
  - derived: `issues = validateLayout(...)`, `score = scoreLayout(...)`
  - `StatusStrip` always shows cell count, `active_area_m2`, target, delta, panel count, met/short/over

- [ ] **Step 1: Write** `store.test.ts`

```ts
it("does not swap gallery while dirty until confirm", ...)
it("split on carve of disconnected cells", ...)
it("resize bound does not fill a carved hole", ...)
it("status area uses n_cells * cell_w * cell_h / 1e6", ...)
```

- [ ] **Step 2: Run** `npx vitest run src/state/store.test.ts`  
  Expected: FAIL

- [ ] **Step 3: Implement store + UI.** Canvas is an SVG: outline, populate fill, keep-out hatch, cells, panel stroke. Violations use the danger color. Inspector edits `cells_wide` / `cells_tall` / angle select (allowed angles). Upload control + “Load TOPSHELL sample”. Generate button.

- [ ] **Step 4: Run** `npx vitest run`  
  Expected: PASS

- [ ] **Step 5: Commit** `feat: add region pick, generate, and manual editor`

---

### Task 9: Docker one-service app

**Files:**
- Create: `Dockerfile` (stage `ui`: node 22, `npm ci && npm run build`; stage `app`: python 3.12-slim, copy backend + `frontend/dist` → `backend/app/static`, `uvicorn app.main:app --host 0.0.0.0 --port 8080`)
- Create: `docker-compose.yml` (`app` service, `8080:8080`, volume-less)
- Create: `.dockerignore`
- Create: `README.md` — `docker compose up --build` then open `http://localhost:8080`
- Modify: `backend/app/main.py` — `StaticFiles` + SPA fallback to `index.html`
- Create: `backend/tests/test_static.py` — client `GET /` returns 200 when a stub `index.html` is present

**Interfaces:**
- Consumes: Task 6 app, Task 8 build
- Produces: one Compose service

- [ ] **Step 1: Write** `test_static.py` that writes a tiny `static/index.html` and expects `b"Array Configurator"` in `GET /`.

- [ ] **Step 2: Run** `pytest tests/test_static.py -v`  
  Expected: FAIL until mount exists

- [ ] **Step 3: Implement static mount and Docker files.** `frontend/index.html` title is `Array Configurator`.

- [ ] **Step 4: Run** `pytest tests/ -v` and `cd frontend && npx vitest run`  
  Expected: PASS. Then `docker compose build` succeeds.

- [ ] **Step 5: Commit** `feat: dockerize the array configurator`

---

## Self-review notes

- Spec coverage: import formats, region pick, both gaps, target area, 90° then irregular then diagonal, same grid/orientation per panel, manual edit + live issues, confirm-before-wipe, SVG/DXF/JSON export, TOPSHELL sample, Compose — each maps to a task above.
- Review Focus items are tests in Tasks 2, 4, 6, and 8.
- Types named here (`LayoutParams`, `Panel.occupied`, `validate_layout`, `pack_layouts`, `dirty`/`confirmReplace`) are the names later tasks must use.
