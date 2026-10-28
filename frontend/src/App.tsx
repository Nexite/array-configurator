import { useEffect, useMemo, useRef, useState } from "react";
import { exportFile, importFile, loadSample, pack, validate } from "./api";
import { preloadGeometry } from "./engine/client";
import {
  addDrawnRegion,
  confirmReplace,
  cycleRegion,
  deletePanel,
  initialState,
  loadRegions,
  movePanel,
  redo,
  resizeBound,
  selectGallery,
  setLayouts,
  toggleCell,
  undo,
  type AppState,
} from "./state/store";
import { panelOutlineEdges } from "./panelOutline";
import { shellAreaM2 } from "./shellArea";
import { type Issue, type LayoutParams, type Panel } from "./types";
import { fitView, panView, screenToWorld, zoomView, type Size, type View } from "./view";

function num(v: string, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function cellPoly(p: Panel, i: number, j: number, params: LayoutParams) {
  const px = params.cell_w_mm + params.cell_gap_mm;
  const py = params.cell_h_mm + params.cell_gap_mm;
  const rad = (p.angle_deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const corners: [number, number][] = [
    [i * px, j * py],
    [i * px + params.cell_w_mm, j * py],
    [i * px + params.cell_w_mm, j * py + params.cell_h_mm],
    [i * px, j * py + params.cell_h_mm],
  ];
  return corners.map(([x, y]) => [p.origin[0] + x * c - y * s, p.origin[1] + x * s + y * c] as [number, number]);
}

export function App() {
  const [s, setS] = useState<AppState>(initialState);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [engineReady, setEngineReady] = useState(false);
  const [drawMode, setDrawMode] = useState(false);
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [viewport, setViewport] = useState<Size>({ w: 0, h: 0 });
  const [view, setView] = useState<View | null>(null);
  const [panning, setPanning] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const userView = useRef(false);
  const panRef = useRef<{ x: number; y: number; moved: boolean; regionId?: string } | null>(null);

  const params = s.params;
  const bounds = useMemo(() => {
    const pts = s.regions.flatMap((r) => r.points);
    if (!pts.length) return { minx: 0, miny: 0, w: 100, h: 100 };
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const minx = Math.min(...xs);
    const miny = Math.min(...ys);
    return { minx, miny, w: Math.max(...xs) - minx || 1, h: Math.max(...ys) - miny || 1 };
  }, [s.regions]);

  const cam = view ?? { x: bounds.minx, y: bounds.miny, w: bounds.w, h: bounds.h };
  const stroke = Math.max(cam.w, cam.h);

  function applyFit(vp = viewport) {
    if (vp.w < 8 || vp.h < 8) return;
    userView.current = false;
    setView(fitView(bounds, vp));
  }

  useEffect(() => {
    preloadGeometry()
      .then(() => setEngineReady(true))
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (!box) return;
      setViewport({ w: box.width, h: box.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const prevVp = useRef(viewport);
  const boundsKey = `${bounds.minx},${bounds.miny},${bounds.w},${bounds.h}`;
  useEffect(() => {
    userView.current = false;
  }, [boundsKey]);

  useEffect(() => {
    if (viewport.w < 8 || viewport.h < 8) return;
    const prev = prevVp.current;
    prevVp.current = viewport;
    if (!userView.current) {
      setView(fitView(bounds, viewport));
      return;
    }
    setView((cur) => {
      if (!cur || !prev.w) return fitView(bounds, viewport);
      const cx = cur.x + cur.w / 2;
      const cy = cur.y + cur.h / 2;
      const spp = cur.w / prev.w;
      const w = spp * viewport.w;
      const h = spp * viewport.h;
      return { x: cx - w / 2, y: cy - h / 2, w, h };
    });
  }, [bounds, viewport]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (ev: WheelEvent) => ev.preventDefault();
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  function worldFromEvent(ev: { clientX: number; clientY: number }, svg = svgRef.current) {
    if (!svg || !viewport.w) return { x: 0, y: 0 };
    const r = svg.getBoundingClientRect();
    return screenToWorld(cam, viewport, ev.clientX - r.left, ev.clientY - r.top);
  }

  async function refreshIssues(state: AppState) {
    if (!state.active) return setIssues([]);
    try {
      const r = await validate(state.regions, state.params, state.active.panels);
      setIssues(r.issues);
    } catch {
      setIssues([]);
    }
  }

  function setParam<K extends keyof LayoutParams>(k: K, v: LayoutParams[K]) {
    setS((prev) => {
      const params = { ...prev.params, [k]: v };
      if (!params.custom_active_area) {
        params.active_w_mm = params.cell_w_mm;
        params.active_h_mm = params.cell_h_mm;
        params.active_mm2 = params.cell_w_mm * params.cell_h_mm;
      }
      return { ...prev, params };
    });
  }

  function setActiveMode(mode: LayoutParams["active_input"]) {
    setS((prev) => {
      const params = { ...prev.params, active_input: mode };
      if (mode === "area") {
        params.active_mm2 = params.active_w_mm * params.active_h_mm;
      }
      return { ...prev, params };
    });
  }

  function enableCustomActive(on: boolean) {
    setS((prev) => ({
      ...prev,
      params: {
        ...prev.params,
        custom_active_area: on,
        active_w_mm: prev.params.cell_w_mm,
        active_h_mm: prev.params.cell_h_mm,
        active_mm2: prev.params.cell_w_mm * prev.params.cell_h_mm,
      },
    }));
  }

  async function onSample() {
    setErr("");
    const r = await loadSample();
    setS((prev) => loadRegions(prev, r.regions));
  }

  async function onUpload(f: File) {
    setErr("");
    try {
      const r = await importFile(f, params.unit_scale);
      setS((prev) => loadRegions(prev, r.regions));
    } catch (e) {
      setErr(String(e));
    }
  }

  async function onGenerate() {
    setBusy(true);
    setErr("");
    try {
      if (s.dirty && !confirm("Replace the edited layout?")) return;
      const r = await pack(s.regions, s.params);
      const next = setLayouts(s, r.layouts);
      setS(next);
      await refreshIssues(next);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onExport(fmt: "svg" | "dxf" | "json") {
    if (!s.active) return;
    const blob = await exportFile(fmt, s.regions, s.params, s.active.panels);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `layout.${fmt}`;
    a.click();
  }

  const score = s.active?.score;
  const shellM2 = useMemo(() => shellAreaM2(s.regions), [s.regions]);

  return (
    <div className="app">
      <aside>
        <h1>Array Configurator</h1>
        <button onClick={onSample}>Load TOPSHELL sample</button>
        <label>
          Upload
          <input type="file" accept=".dxf,.svg,.plt,.hpgl" onChange={(e) => e.target.files && onUpload(e.target.files[0])} />
        </label>
        <label>
          Unit scale
          <input type="number" step="0.01" value={params.unit_scale} onChange={(e) => setParam("unit_scale", num(e.target.value, 1))} />
        </label>
        <h2>Cell footprint (pack)</h2>
        <label>
          Width mm
          <input type="number" value={params.cell_w_mm} onChange={(e) => setParam("cell_w_mm", num(e.target.value, 182))} />
        </label>
        <label>
          Height mm
          <input type="number" value={params.cell_h_mm} onChange={(e) => setParam("cell_h_mm", num(e.target.value, 96))} />
        </label>
        <details className="fold">
          <summary>Usable / active area</summary>
          <p className="hint">Optional. Off by default, usable area tracks the cell footprint.</p>
          <label className="check">
            Custom usable area
            <input
              type="checkbox"
              checked={params.custom_active_area}
              onChange={(e) => enableCustomActive(e.target.checked)}
            />
          </label>
          <div className="mode" aria-label="Usable area input">
            <button
              type="button"
              className={params.active_input === "dimensions" ? "active" : ""}
              disabled={!params.custom_active_area}
              onClick={() => setActiveMode("dimensions")}
            >
              Dimensions
            </button>
            <button
              type="button"
              className={params.active_input === "area" ? "active" : ""}
              disabled={!params.custom_active_area}
              onClick={() => setActiveMode("area")}
            >
              mm²
            </button>
          </div>
          {params.active_input === "area" ? (
            <label>
              Active mm²
              <input
                type="number"
                disabled={!params.custom_active_area}
                value={params.custom_active_area ? params.active_mm2 : params.cell_w_mm * params.cell_h_mm}
                onChange={(e) => setParam("active_mm2", num(e.target.value, params.cell_w_mm * params.cell_h_mm))}
              />
            </label>
          ) : (
            <>
              <label>
                Active W mm
                <input
                  type="number"
                  disabled={!params.custom_active_area}
                  value={params.custom_active_area ? params.active_w_mm : params.cell_w_mm}
                  onChange={(e) => setParam("active_w_mm", num(e.target.value, params.cell_w_mm))}
                />
              </label>
              <label>
                Active H mm
                <input
                  type="number"
                  disabled={!params.custom_active_area}
                  value={params.custom_active_area ? params.active_h_mm : params.cell_h_mm}
                  onChange={(e) => setParam("active_h_mm", num(e.target.value, params.cell_h_mm))}
                />
              </label>
            </>
          )}
        </details>
        <h2>Gaps and panels</h2>
        <label>
          Cell gap mm
          <input type="number" value={params.cell_gap_mm} onChange={(e) => setParam("cell_gap_mm", num(e.target.value, 2))} />
        </label>
        <label>
          Panel gap mm
          <input type="number" value={params.panel_gap_mm} onChange={(e) => setParam("panel_gap_mm", num(e.target.value, 10))} />
        </label>
        <label>
          Edge inset mm
          <input type="number" value={params.edge_inset_mm} onChange={(e) => setParam("edge_inset_mm", num(e.target.value, 0))} />
        </label>
        <label>
          Orientation spread °
          <input
            type="number"
            value={params.orientation_spread_deg}
            onChange={(e) => setParam("orientation_spread_deg", num(e.target.value, 90))}
          />
        </label>
        <label>
          Max cells, short side
          <input type="number" value={params.max_wide} onChange={(e) => setParam("max_wide", num(e.target.value, 24))} />
        </label>
        <label>
          Max cells, long side
          <input type="number" value={params.max_tall} onChange={(e) => setParam("max_tall", num(e.target.value, 6))} />
        </label>
        <label>
          Target m²
          <input type="number" step="0.01" value={params.target_area_m2} onChange={(e) => setParam("target_area_m2", num(e.target.value, 6))} />
        </label>
        <button className="primary" disabled={busy || !s.regions.length} onClick={onGenerate}>
          {busy ? "Packing…" : "Generate"}
        </button>
        <p className="hint">
          Scroll to zoom, drag empty space to pan, double-click to fit. Click a region to cycle populate / keep-out / unused.
          {drawMode ? " Click the canvas to draw an exclude polygon." : ""}
        </p>
        <button onClick={() => setDrawMode((d) => !d)}>{drawMode ? "Finish drawing" : "Draw exclude"}</button>
        {drawMode && draft.length > 2 && (
          <button
            onClick={() => {
              setS((prev) => addDrawnRegion(prev, draft, "keep_out"));
              setDraft([]);
              setDrawMode(false);
            }}
          >
            Add keep-out
          </button>
        )}
        {err && <p className="issue">{err}</p>}
        <h2>Selected panel</h2>
        {s.selectedPanelId && s.active && (
          <>
            <label>
              Wide
              <input
                type="number"
                onChange={(e) => setS((prev) => resizeBound(prev, s.selectedPanelId!, num(e.target.value, 1), prev.active?.panels.find((p) => p.id === s.selectedPanelId)?.cells_tall ?? 1))}
              />
            </label>
            <button className="danger" onClick={() => setS((prev) => deletePanel(prev, s.selectedPanelId!))}>
              Delete panel
            </button>
          </>
        )}
        <button onClick={() => setS((prev) => undo(prev))}>Undo</button>
        <button onClick={() => setS((prev) => redo(prev))}>Redo</button>
        <h2>Export</h2>
        <button onClick={() => onExport("svg")}>SVG</button>
        <button onClick={() => onExport("dxf")}>DXF</button>
        <button onClick={() => onExport("json")}>JSON</button>
      </aside>
      <div className="canvas-wrap">
        <div className="status">
          {!engineReady && <span>Loading geometry…</span>}
          <span>Cells {score?.cell_count ?? 0}</span>
          <span>Panels {score?.panel_count ?? 0}</span>
          <span>Shell {shellM2 == null ? "—" : `${shellM2.toFixed(3)} m²`}</span>
          <span>Usable {score?.active_area_m2.toFixed(4) ?? "0"} m²</span>
          <span>Target {params.target_area_m2.toFixed(3)} m²</span>
          <span className={score?.meets_target ? "ok" : "off"}>Δ {score?.delta_m2.toFixed(4) ?? "0"} m²</span>
          {s.pendingGalleryId && (
            <button
              onClick={() => {
                const next = confirmReplace(s);
                setS(next);
                refreshIssues(next);
              }}
            >
              Confirm replace
            </button>
          )}
          <button onClick={() => applyFit()}>Fit</button>
        </div>
        <svg
          ref={svgRef}
          className={`board${panning ? " panning" : ""}`}
          viewBox={`${cam.x} ${cam.y} ${cam.w} ${cam.h}`}
          preserveAspectRatio="none"
          onWheel={(ev) => {
            ev.preventDefault();
            if (!viewport.w) return;
            const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
            const world = worldFromEvent(ev);
            userView.current = true;
            setView((cur) => {
              const base = cur ?? cam;
              const next = zoomView(base, factor, world.x, world.y);
              const minW = bounds.w / 50;
              const maxW = Math.max(bounds.w, 1) * 12;
              if (next.w < minW || next.w > maxW) return base;
              return next;
            });
          }}
          onPointerDown={(ev) => {
            if (drawMode) return;
            const t = ev.target as Element;
            if (t.closest(".cell")) return;
            const regionId = t instanceof SVGPolygonElement && t.dataset.regionId ? t.dataset.regionId : undefined;
            panRef.current = { x: ev.clientX, y: ev.clientY, moved: false, regionId };
            ev.currentTarget.setPointerCapture(ev.pointerId);
          }}
          onPointerMove={(ev) => {
            const pan = panRef.current;
            if (!pan || !viewport.w) return;
            const dx = ev.clientX - pan.x;
            const dy = ev.clientY - pan.y;
            if (!pan.moved && dx * dx + dy * dy < 16) return;
            pan.moved = true;
            setPanning(true);
            userView.current = true;
            const wx = (dx * cam.w) / viewport.w;
            const wy = (dy * cam.h) / viewport.h;
            pan.x = ev.clientX;
            pan.y = ev.clientY;
            setView((cur) => panView(cur ?? cam, wx, wy));
          }}
          onPointerUp={() => {
            const pan = panRef.current;
            panRef.current = null;
            setPanning(false);
            if (pan && !pan.moved && pan.regionId && !drawMode) {
              setS((prev) => cycleRegion(prev, pan.regionId!));
            }
          }}
          onDoubleClick={() => applyFit()}
          onClick={(ev) => {
            if (!drawMode) return;
            const loc = worldFromEvent(ev);
            setDraft((d) => [...d, [loc.x, loc.y]]);
          }}
        >
          {s.regions.map((r) => (
            <polygon
              key={r.id}
              data-region-id={r.id}
              points={r.points.map((p) => p.join(",")).join(" ")}
              fill={r.kind === "populate" ? "#1f6feb" : r.kind === "keep_out" ? "#e05a4f" : "#555"}
              fillOpacity={r.kind === "populate" ? 0.25 : 0.2}
              stroke={r.kind === "populate" ? "#3d8ef0" : "#888"}
              strokeWidth={stroke / 400}
            />
          ))}
          {s.active?.panels.map((p) =>
            p.occupied.map(([i, j]) => {
              const pts = cellPoly(p, i, j, params);
              const bad = issues.some((iss) => iss.panel_ids.includes(p.id));
              return (
                <polygon
                  key={`${p.id}-${i}-${j}`}
                  className="cell"
                  points={pts.map((q) => q.join(",")).join(" ")}
                  fill={bad ? "#e05a4f" : "#f0c14b"}
                  fillOpacity={0.75}
                  stroke="#111"
                  strokeWidth={stroke / 1200}
                  onPointerDown={(ev) => {
                    ev.stopPropagation();
                    ev.preventDefault();
                    setS((prev) => ({ ...prev, selectedPanelId: p.id }));
                    const start = { x: ev.clientX, y: ev.clientY, ox: p.origin[0], oy: p.origin[1] };
                    const move = (e: PointerEvent) => {
                      const scaleX = cam.w / (viewport.w || 1);
                      const scaleY = cam.h / (viewport.h || 1);
                      const nx = Math.round(start.ox + (e.clientX - start.x) * scaleX);
                      const ny = Math.round(start.oy + (e.clientY - start.y) * scaleY);
                      setS((prev) => movePanel(prev, p.id, [nx, ny]));
                    };
                    const up = () => {
                      window.removeEventListener("pointermove", move);
                      window.removeEventListener("pointerup", up);
                      setS((prev) => {
                        refreshIssues(prev);
                        return prev;
                      });
                    };
                    window.addEventListener("pointermove", move);
                    window.addEventListener("pointerup", up);
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (e.shiftKey) setS((prev) => toggleCell(prev, p.id, i, j));
                  }}
                />
              );
            }),
          )}
          {s.active?.panels.map((p) =>
            panelOutlineEdges(p.occupied).map((e, k) => {
              const pts = cellPoly(p, e.i, e.j, params);
              const a = pts[e.from];
              const b = pts[e.to];
              return (
                <line
                  key={`${p.id}-outline-${k}`}
                  x1={a[0]}
                  y1={a[1]}
                  x2={b[0]}
                  y2={b[1]}
                  stroke="#050505"
                  strokeWidth={stroke / 250}
                  strokeLinecap="square"
                  pointerEvents="none"
                />
              );
            }),
          )}
          {draft.length > 1 && <polyline points={draft.map((p) => p.join(",")).join(" ")} fill="none" stroke="#e05a4f" />}
        </svg>
      </div>
      <div className="gallery">
        <h2>Layouts</h2>
        {s.layouts.map((l) => (
          <div
            key={l.id}
            className={`card ${s.active?.id === l.id ? "active" : ""}`}
            onClick={() => setS((prev) => selectGallery(prev, l.id))}
          >
            <strong>{l.family}</strong>
            <div>{l.score?.cell_count} cells · {l.score?.active_area_m2.toFixed(3)} m²</div>
          </div>
        ))}
        <h2>Issues</h2>
        {!issues.length && <p className="hint">No issues.</p>}
        {issues.map((iss, i) => (
          <div key={i} className="issue">
            {iss.message}
          </div>
        ))}
      </div>
    </div>
  );
}
