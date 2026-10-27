# Array Configurator — Design

## Intent

A dockerized web app that takes a 2D vector outline of a solar-array region (starting with the solar-car topshell) and a handful of cell/panel numbers, then shows possible ways to tile that outline with solar panels. Panels are groups of cells on a local grid — solid rectangles when those fit, and irregular (notched, L, following a taper) when a rectangle would waste the outline.

The point is to see, quickly, which panel sizes and placements get close to a target cell area without hanging off the shell or landing in regions the user left empty — then to nudge that first layout by hand while the app keeps a live list of what is still wrong.

## Why

Laying cells on a pointed topshell by hand is slow. The useful question is not “what is the theoretical max?” but “given these cells, this gap, this max panel size, and this target area, which layouts are actually worth building?”

## Goals

- Upload a 2D outline in common vector formats. Detect closed regions, then let the user **choose which areas to populate**. Regions can be marked populate, keep-out, or unused. The user can also draw extra include/exclude polygons so only part of a single shell is filled (left side, rear, skip a walkway). Auto-pack and live issues only use the selected populate area.
- Accept these parameters:
  - solar cell **footprint** width and height (mm) — the physical rectangle used for packing, gaps, and collisions
  - solar cell **usable / active** width and height (mm) — the PV area that counts toward target surface area. These may be smaller than the footprint (tabs, rounded corners, masked busbars). Defaults equal the footprint.
  - solar cell spacing / gap (mm), applied between cells inside a panel in both directions
  - panel spacing / gap (mm), applied between adjacent panels (and between a panel and another panel only — not inside a panel)
  - max panel size as cells-wide × cells-tall
  - **target surface area (m²)** — the desired total *usable* cell area (`active_w × active_h × cell count`; footprint and gaps do not count)
- Generate multiple distinct layouts and display them as overlays on the outline. Auto-generation produces the first working config the user then owns.
- For each layout, show cell count, panel count, panel size mix, active area, and how far it is from the target (absolute and percent).
- Rank layouts by closeness to the target, then by fewer panels (simpler module count), then by more axis-aligned (90°) area, then by simpler panel shapes (solid rectangles over carved ones), then by higher coverage.
- After the first config is on the canvas, the user can **manually edit** it: move cells, move panels, change a panel’s bounding cells-wide × cells-tall, toggle cells on or off inside a panel (carve / grow a weirder footprint), add/delete a panel or cell, and rotate a panel among the allowed angles (90° and the discrete diagonal set).
- While editing, show a live **issues** list and live **surface-area count** (current vs target). Issues include panel-spacing violations, cell-spacing violations inside a panel, overlaps, and cells outside the outline or in a hole. The canvas highlights the offending cells/panels.
- Manual edits are not thrown away if the user tweaks parameters or regenerates — ask first.
- Ship as a single `docker compose up` web app.

## Non-goals

- 3D unfolding or wrapping cells onto curved mold surfaces.
- Electrical stringing, bypass diodes, or MPPT grouping.
- Structural / adhesive / walkway rules beyond “cells stay fully inside the outline.”
- Automatic guessing of CAD layer names. The user picks populate vs keep-out on the canvas.
- Auth, multi-user accounts, or cloud save. Export of the current layout as SVG, DXF (cell and panel outlines), and a JSON snapshot is in v1.

## Anti-goals

- A layout that looks full but has cells crossing the outline, sitting in a keep-out, or sitting in a region the user did not mark to populate.
- A single “best” answer with no alternatives, and no way to fix it by hand.
- Treating target area or spacing as unused decoration — they must change ranking, and they must stay visible as live counts/issues while the user edits.
- Regenerating and silently wiping a layout the user has been dragging around.

## Constraints

- Default sample outline is `TOPSHELL.DXF` (solar-car topshell, CAD units = mm). The canopy is already removed from this file; do not invent a second “flatten” step.
- Outline units default to millimeters. The UI exposes a unit scale if a file is inches or unitless.
- Every cell rectangle must lie fully inside the **user-selected populate region** (no partial cells). Keep-outs and unused regions are empty.
- A panel is a **connected** set of cells on **one shared local grid** (edge-adjacent, no diagonal-only joins), with **cell spacing** between occupied neighbors. **Every cell in a panel has the same orientation** and sits on that same grid — same origin, same pitch, same rotation. No cell in a panel may be rotated, offset, or sheared relative to the others. The occupied mask can be an irregular polyomino (L, T, notches); the grid itself stays regular. The panel’s bounding box is at most `max_wide × max_tall` cells. A fully enclosed empty cell is fine if the occupied cells remain 4-connected.
- Auto-pack must try **more than solid rectangles**. First it tries filled rectangles (simpler to build). Then it tries carved / irregular masks: drop cells that would leave the outline, or grow a connected blob of cells up to the max bounding box so a panel can follow a taper. Both families appear in the gallery. A layout may mix rectangular and irregular panels.
- Orientation policy: **try 90° first**. The first packing pass uses only axis-aligned panels (0° and 90°, so a 6×4 max also allows 4×6 bounds). After that pass, leftover pockets may be filled with **diagonal** panels — the same local-grid cell groups, **rotated as a whole**. Different panels may have different angles. Cells inside one panel may not. A live issue is raised if an edit would put two cells of the same panel on different angles or off the same grid.
- Allowed diagonal angles are a discrete set the builder chooses (for example 15° steps, plus angles taken from long outline edges). Continuous free rotation of every panel is out of scope.
- Panels do not overlap. Adjacent panels are separated by **panel spacing** on all sides that face another panel, measured as a Minkowski/buffer gap so it still holds when one panel is diagonal. Panel spacing is a distinct input from cell spacing; either may be zero. A panel's cells still must stay fully inside the outline (panel spacing does not create an extra keep-out from the outline edge unless the builder needs a tiny numeric epsilon).
- Common vector inputs, parsed to 2D paths: DXF, DWG (best-effort), SVG, PDF, AI, EPS, PDF-based Illustrator, HPGL/PLT. Raster files are rejected with a clear error.
- First version is local / single-user. No login.
- Editing may produce a layout the auto-packer would not have chosen. That is allowed. The app does not auto-correct the user’s moves; it reports issues. Growing a panel’s bounding box still respects the current max cells-wide × cells-tall (raise the max parameter to grow further). Changing the bound does not flatten an irregular mask back into a rectangle; it adds or drops cells at the edges.
- Dragging a whole panel keeps its occupancy mask, orientation, and grid. Dragging a single cell *along* the panel grid (integer steps) stays in the panel. Dragging it off that grid detaches it as a 1×1 panel with its own orientation. You cannot rotate or skew one cell while it still belongs to a multi-cell panel. Toggling a cell off (and leaving at least one cell) carves the panel; toggling the last cell deletes it. Dropping a 1×1 onto a panel does not auto-merge unless the builder later adds a snap-to-grid merge — v1 can skip merge. If a carve splits a panel into two disconnected groups, the app splits it into two panels and flags that it did so.

## How it works

### Outline and region pick

The uploaded file is converted to polygons. Closed paths become candidate regions. Open strokes are ignored unless they nearly close (builder chooses a small snap tolerance). Nested loops are offered as separate clickable regions (outer shell vs inner island vs hole).

On import, the largest region starts as **populate** and inner loops inside it start as **keep-out**, so a single-shell file like TOPSHELL is ready to generate. The user can then:

- Click a detected region to cycle **populate → keep-out → unused**
- Draw extra polygons (click-to-add vertices, or a box) and mark each include or exclude
- Populate several disjoint regions at once (e.g. left and right, skip the middle)

The packable geometry is the union of populate regions minus keep-outs and unused. Changing the selection after a layout exists asks before regenerating, same as other destructive actions.

### Candidates

The app enumerates panel recipes up to the max bounding box and a small set of grid origins / offsets along the outline bounding box. A recipe is a connected occupancy mask, not only a filled `w × h` rectangle.

1. **90° rectangles.** Pack axis-aligned solid rectangles. This is the default family of layouts.
2. **90° irregular.** On the same pass (and as extra gallery cards), pack carved / polyomino panels whose cells stay on the 90° grid but whose outline is not a rectangle — used where a solid rectangle would miss the taper or leave a one-cell notch unused.
3. **Diagonal fill.** On leftover area that could not take another 90° panel, try rotated (diagonal) panels of the same cell pitch, again allowing both solid and carved masks. Also generate a few extra candidate layouts that use diagonal panels earlier if that is the only way to approach the target — but never skip the 90°-first pass.

Mixed sizes and mixed shapes in one layout are allowed; every panel still respects the max bound. When two layouts are similarly close to the target, prefer the one with more area in 90° panels, then the one with more rectangular (uncarved) panels.

Packing strategy is left to the builder as long as it is deterministic, finishes in a few seconds on a ~1.5 m × 5 m topshell, and never places a cell outside the selected populate region.

### Target surface area

Active area `A = n_cells × active_w × active_h` (converted to m²). Packing still uses the footprint `cell_w × cell_h`.

- Layouts are scored by `|A − target|`.
- Layouts that meet or exceed the target are marked as meeting it.
- If many layouts meet the target, prefer the one closest to the target (do not overshoot for its own sake), then fewer panels, then simpler size mix.
- If none meet the target, still show the closest several and say how short they are.
- Target does not clip packing; the engine still packs the outline, then ranks. (A later “stop at target” mode is out of scope.)

### Display and edit

One page: file upload, the parameter form (including both spacings and target area), generate, a gallery of auto layouts, and a large canvas for the **active** layout.

Flow:

1. User uploads (or loads the TOPSHELL sample), reviews/clicks which areas to populate, sets parameters, and generates. The top-ranked layout becomes the active config on the canvas immediately.
2. Other auto layouts stay in a side list; picking one replaces the canvas **only after confirm** if the active layout has manual edits.
3. The canvas is the editor. Click a panel to select it. Drag to move. Handles or a small inspector change the bounding cells-wide / cells-tall without wiping a carved mask. Click a cell in the selected panel to toggle it on/off. Rotate among allowed angles. Delete. Add a new panel or a single cell at a click.
4. A **status strip** always shows: cell count, active area (m²), target (m²), delta, panel count. Area that meets target is marked met; short or over is called out.
5. An **issues** panel updates on every edit (client-side, using the already-loaded outline). Each issue names the rule, the amount (e.g. “panels A and B are 6.2 mm apart; need 10 mm”), and focuses the canvas on the offenders when clicked. Clear when the layout is clean.
6. Export the current overlay as SVG, DXF (cells and panel outlines in the same units as the input), and a JSON snapshot so the edit session can be restored.

Issue checks (live):

- Cell not fully inside the selected populate area, or inside a keep-out
- Two cells overlap
- Two panels closer than **panel spacing**
- Two cells in the same panel off the required **cell spacing** / shared grid, or not the same orientation
- Surface area vs target (always shown; listed as an issue when `|A − target|` is more than one cell’s area)

The gallery and canvas share the same drawing: outline, panels, individual cells. Diagonal panels draw in their rotated frame. Violations get a distinct stroke so they are obvious without opening the issues list.

## Builder calls (not user decisions)

- Stack: Python FastAPI + Shapely packing on the server; Vite + React on the client; nginx or the API serving the built UI; Docker Compose with one app service (and a multi-stage image).
- Geometry libraries: `ezdxf` for DXF, `svgelements`/`svgpathtools` for SVG, pypdf/pymupdf for PDF/AI, `pillow` only for preview rasters. DWG via a converter if one is available in the image; otherwise a clear “convert to DXF” error.
- Default numbers in the form can be typical solar-car cells (e.g. 125 × 125 mm footprint, 125 × 125 mm usable, 2 mm cell gap, 10 mm panel gap, max 6 × 10, target 6.0 m²) — builder may tune these to the sample file.
- Visual style: dark technical UI, outline + cell grid, no marketing fluff.
- Live validation and dragging run in the browser against the parsed outline; the server is for import + auto-pack only. Undo/redo for edits is required (builder picks the stack).

## Left to the builder

- Exact packing heuristic (shelf, skyline, greedy max-rect, connected-blob grow, which polyominoes to enumerate). Do not enumerate every polyomino up to the max if that blows the time budget; grow/carve from the outline is enough as long as non-rectangular panels actually appear.
- How many layouts to return (around 8–16 distinct ones is enough).
- Deduping near-identical layouts.
- File-size limits and timeout.
- Test fixtures: a simple rectangle plus the topshell sample.
- Snap increment while dragging (e.g. 1 mm) and whether a dragged cell can rotate independently (v1: no — only panels rotate).
